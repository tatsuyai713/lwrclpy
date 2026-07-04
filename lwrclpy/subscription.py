# lwrclpy/subscription.py
# DDS DataReader wrapper that enqueues received samples for executor-driven callbacks.
# Implements copy according to fastddsgen-generated getter/setter conventions.
# Supports zero-copy with Fast DDS data sharing where compatible.

from __future__ import annotations
from typing import Optional, List, Tuple, Any, Iterator
import inspect
import fastdds  # type: ignore
import os
import logging
import threading
import time
from ._async import run_coroutine
from .qos import QoSProfile
from .message_utils import expose_callable_fields, _buffer_view, _get_value
from .utils import (
    _matched_handle_count,
    _matched_status_count,
    _pubsub_type_is_plain,
    _pubsub_type_supports_data_sharing,
    _retcode_is_ok,
    env_int,
)


_logger = logging.getLogger(__name__)


_MAX_CALLBACKS_PER_DRAIN = env_int("LWRCLPY_MAX_CALLBACKS_PER_DRAIN", 16, minimum=1)
_SKIP_SAMPLE = object()


def _content_filter_parts(content_filter_options):
    if content_filter_options is None:
        return None, ()
    expression = getattr(content_filter_options, "filter_expression", None)
    if expression is None:
        expression = getattr(content_filter_options, "expression", None)
    params = getattr(content_filter_options, "expression_parameters", None)
    if expression is None and isinstance(content_filter_options, (tuple, list)) and content_filter_options:
        expression = content_filter_options[0]
        if len(content_filter_options) > 1:
            params = content_filter_options[1]
    if expression is None:
        expression = str(content_filter_options)
    if params is None:
        params = ()
    return str(expression).strip(), tuple(params)


def _content_filter_value(token: str, params):
    token = token.strip()
    if token.startswith("%") and token[1:].isdigit():
        index = int(token[1:])
        if 0 <= index < len(params):
            return _content_filter_value(str(params[index]), ())
    if (len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}):
        return token[1:-1]
    lowered = token.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(token)
    except Exception:
        pass
    try:
        return float(token)
    except Exception:
        return token


def _make_content_filter_predicate(content_filter_options):
    expression, params = _content_filter_parts(content_filter_options)
    if not expression:
        return None
    clauses = [part.strip() for part in expression.replace(" AND ", " and ").split(" and ") if part.strip()]
    tests = []
    operators = (">=", "<=", "!=", "=", ">", "<")
    for clause in clauses:
        for op in operators:
            if op in clause:
                field, rhs = clause.split(op, 1)
                field = field.strip()
                expected = _content_filter_value(rhs, params)
                if field:
                    tests.append((field, op, expected))
                break
    if not tests:
        _logger.warning("Unsupported content_filter_options expression %r; filter will be ignored", expression)
        return None

    def predicate(msg):
        for field, op, expected in tests:
            actual = _get_value(msg, field)
            try:
                if op == "=":
                    ok = actual == expected
                elif op == "!=":
                    ok = actual != expected
                elif op == ">":
                    ok = actual > expected
                elif op == "<":
                    ok = actual < expected
                elif op == ">=":
                    ok = actual >= expected
                elif op == "<=":
                    ok = actual <= expected
                else:
                    ok = True
            except Exception:
                ok = False
            if not ok:
                return False
        return True

    return predicate


def _field_payload_nbytes(msg, field: str) -> int | None:
    """Return the current byte length of a message sequence field, if cheap."""
    helper = getattr(msg, f"_lwrclpy_{field}_nbytes", None)
    if callable(helper):
        try:
            return int(helper())
        except Exception:
            pass
    try:
        value = getattr(msg, field)
    except Exception:
        return None
    if callable(value):
        try:
            value = value()
        except Exception:
            return None
    if value is None:
        return None
    view = _buffer_view(value)
    if view is not None:
        return view.nbytes
    try:
        size = value.size() if callable(getattr(value, "size", None)) else len(value)
        return int(size)
    except Exception:
        return None


def _side_channel_matches_payload(msg, field: str, metadata_nbytes: int) -> bool:
    """Guard against attaching stale side-channel metadata to a message.

    Metadata and payload travel on separate DDS topics with no per-sample
    correlation, so the only safe cases are: the payload field was cleared by
    the publisher (signal message), or the payload has exactly the announced
    byte length (dual publish).  A differing size means the metadata belongs
    to another sample and must not shadow the real data.
    """
    payload_nbytes = _field_payload_nbytes(msg, field)
    if payload_nbytes is None:
        return False
    if payload_nbytes == 0:
        return True
    return payload_nbytes == int(metadata_nbytes)


def _sample_info_attr(sample_info, name, default=None):
    try:
        value = getattr(sample_info, name)
    except Exception:
        return default
    if not callable(value):
        return value
    try:
        return value()
    except Exception:
        return default


def _sample_info_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _copy_swig_struct(value):
    """Copy a SWIG proxy via its generated copy constructor when possible."""
    if value is None:
        return None
    try:
        return type(value)(value)
    except Exception:
        return value


def _force_data_sharing_on_reader(rq: "fastdds.DataReaderQos") -> bool:
    """Prefer/force data sharing on the reader QoS when the API exists."""
    if os.environ.get("LWRCLPY_NO_DATASHARING") == "1":
        return False
    try:
        if hasattr(rq, "data_sharing"):
            ds = rq.data_sharing()
            shared_dir = os.environ.get("LWRCLPY_DATASHARING_DIR", "")
            if hasattr(ds, "on"):
                try:
                    ds.on(shared_dir)
                except TypeError:
                    ds.on()
                return True
            if hasattr(ds, "automatic"):
                ds.automatic()
                return False
    except Exception:
        pass
    return False


def _disable_data_sharing_on_reader(rq: "fastdds.DataReaderQos") -> None:
    try:
        if hasattr(rq, "data_sharing"):
            ds = rq.data_sharing()
            if hasattr(ds, "automatic"):
                ds.automatic()
            elif hasattr(ds, "off"):
                ds.off()
    except Exception:
        pass


def _resolve_loaned_samples_cls(msg_module, msg_ctor):
    module = msg_module
    if module is None and msg_ctor is not None:
        module = __import__(msg_ctor.__module__, fromlist=[msg_ctor.__name__])
    if module is None or msg_ctor is None:
        return None
    return getattr(module, f"Lwrclpy_{msg_ctor.__name__}_LoanedSamples", None)


def _attach_loan_to_sample(sample, loaned: "_LoanedSamples") -> bool:
    """Keep a reader loan alive for as long as the callback message is alive."""
    for setter in (setattr, object.__setattr__):
        try:
            setter(sample, "_lwrclpy_loaned_samples", loaned)
            return True
        except Exception:
            continue
    return False


class MessageInfo:
    """Information about a received message (similar to rclpy.MessageInfo)."""
    __slots__ = (
        "_sample_info", "_source_timestamp", "_received_timestamp",
        "_publication_sequence_number", "_reception_sequence_number",
        "_publisher_gid", "_from_intra_process", "_publisher_handle",
        "_sample_identity", "_is_valid",
    )
    
    def __init__(self, sample_info=None):
        self._sample_info = sample_info
        self._source_timestamp = None
        self._received_timestamp = 0
        self._publication_sequence_number = None
        self._reception_sequence_number = None
        self._publisher_gid = None
        self._from_intra_process = None
        self._publisher_handle = None
        self._sample_identity = None
        self._is_valid = None

    @property
    def is_valid(self):
        if self._is_valid is None:
            self._is_valid = bool(_sample_info_attr(self._sample_info, "valid_data", True))
        return self._is_valid

    @is_valid.setter
    def is_valid(self, value):
        self._is_valid = bool(value)

    @property
    def sample_identity(self):
        if self._sample_identity is None:
            self._sample_identity = _sample_info_attr(self._sample_info, "sample_identity")
        return self._sample_identity

    @sample_identity.setter
    def sample_identity(self, value):
        self._sample_identity = value

    @property
    def source_timestamp(self):
        if self._source_timestamp is None:
            ts = _sample_info_attr(self._sample_info, "source_timestamp")
            if ts is not None:
                sec = _sample_info_int(_sample_info_attr(ts, "seconds", 0), 0)
                nsec = _sample_info_int(_sample_info_attr(ts, "nanosec", 0), 0)
                self._source_timestamp = sec * 1_000_000_000 + nsec
            else:
                self._source_timestamp = 0
        return self._source_timestamp

    @source_timestamp.setter
    def source_timestamp(self, value):
        self._source_timestamp = int(value)

    @property
    def received_timestamp(self):
        return self._received_timestamp

    @received_timestamp.setter
    def received_timestamp(self, value):
        self._received_timestamp = int(value)

    @property
    def publication_sequence_number(self):
        if self._publication_sequence_number is None:
            if hasattr(self._sample_info, "publication_sequence_number"):
                self._publication_sequence_number = _sample_info_int(
                    _sample_info_attr(self._sample_info, "publication_sequence_number", 0),
                    0,
                )
            else:
                self._publication_sequence_number = 0
        return self._publication_sequence_number

    @publication_sequence_number.setter
    def publication_sequence_number(self, value):
        self._publication_sequence_number = int(value)

    @property
    def reception_sequence_number(self):
        if self._reception_sequence_number is None:
            if hasattr(self._sample_info, "reception_sequence_number"):
                self._reception_sequence_number = _sample_info_int(
                    _sample_info_attr(self._sample_info, "reception_sequence_number", 0),
                    0,
                )
            else:
                self._reception_sequence_number = 0
        return self._reception_sequence_number

    @reception_sequence_number.setter
    def reception_sequence_number(self, value):
        self._reception_sequence_number = int(value)

    @property
    def publisher_gid(self):
        if self._publisher_gid is None:
            if hasattr(self._sample_info, "publisher_gid"):
                self._publisher_gid = _sample_info_attr(self._sample_info, "publisher_gid")
            if self._publisher_gid is None and self.sample_identity is not None and hasattr(self.sample_identity, "writer_guid"):
                self._publisher_gid = _sample_info_attr(self.sample_identity, "writer_guid")
        return self._publisher_gid

    @publisher_gid.setter
    def publisher_gid(self, value):
        self._publisher_gid = value

    @property
    def publisher_handle(self):
        if self._publisher_handle is None and hasattr(self._sample_info, "publication_handle"):
            self._publisher_handle = _sample_info_attr(self._sample_info, "publication_handle")
        return self._publisher_handle

    @publisher_handle.setter
    def publisher_handle(self, value):
        self._publisher_handle = value

    @property
    def from_intra_process(self):
        if self._from_intra_process is None:
            if hasattr(self._sample_info, "from_intra_process"):
                self._from_intra_process = bool(_sample_info_attr(self._sample_info, "from_intra_process", False))
            else:
                self._from_intra_process = False
        return self._from_intra_process

    @from_intra_process.setter
    def from_intra_process(self, value):
        self._from_intra_process = bool(value)

    def _eager_populate(self):
        if self._sample_info is not None:
            try:
                _ = self.is_valid
                _ = self.source_timestamp
                _ = self.publication_sequence_number
                _ = self.reception_sequence_number
                _ = self.from_intra_process
                # These are SWIG proxies pointing into the native SampleInfo;
                # copy them so they survive the sample info's storage.
                self._sample_identity = _copy_swig_struct(self.sample_identity)
                self._publisher_gid = _copy_swig_struct(self.publisher_gid)
                self._publisher_handle = _copy_swig_struct(self.publisher_handle)
            except Exception:
                pass

    @property
    def publisher_guid(self):
        return self.publisher_gid

    @property
    def sequence_number(self):
        return self.publication_sequence_number


class _LoanedSamples:
    """Container for DataReader-loaned samples.

    Samples are valid until ``return_loan()`` is called.  Use it as a context
    manager when possible so Fast DDS reader resources are returned promptly.
    """

    __slots__ = ("_native", "_expose_fn", "_returned", "_release_cb")

    def __init__(self, native, *, raw_mode: bool = False, expose_fields: bool = True, release_cb=None):
        self._native = native
        self._expose_fn = expose_callable_fields if (expose_fields and not raw_mode) else None
        self._returned = False
        self._release_cb = release_cb

    def __len__(self) -> int:
        if self._returned:
            return 0
        try:
            return int(self._native.length())
        except Exception:
            return 0

    def __iter__(self) -> Iterator[Any]:
        for index in range(len(self)):
            item = self[index]
            if item is not None:
                yield item

    def __getitem__(self, index: int):
        if self._returned:
            raise RuntimeError("LoanedSamples has already returned its DDS loan")
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError(index)
        try:
            if hasattr(self._native, "valid_data") and not self._native.valid_data(index):
                return None
            sample = self._native.sample(index)
        except Exception as exc:
            raise RuntimeError("Failed to access loaned DDS sample") from exc
        expose_fn = self._expose_fn
        if expose_fn is not None and sample is not None:
            try:
                expose_fn(sample)
            except Exception:
                pass
        return sample

    def info(self, index: int) -> MessageInfo:
        if self._returned:
            raise RuntimeError("LoanedSamples has already returned its DDS loan")
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError(index)
        try:
            info = self._native.info(index)
        except Exception as exc:
            raise RuntimeError("Failed to access loaned DDS sample info") from exc
        message_info = MessageInfo(info)
        # The native SampleInfo lives inside the reader loan; cache all fields
        # now and drop the reference so the MessageInfo stays valid after
        # return_loan() (e.g. when the user stores it beyond the callback).
        message_info._eager_populate()
        message_info._sample_info = None
        return message_info

    def items(self) -> Iterator[Tuple[Any, MessageInfo]]:
        for index in range(len(self)):
            sample = self[index]
            if sample is not None:
                yield sample, self.info(index)

    @property
    def returned(self) -> bool:
        return self._returned

    def return_loan(self) -> bool:
        if self._returned:
            return True
        returned = False
        try:
            rc = self._native.return_loan()
            ok = True if rc is None else bool(rc)
            returned = ok
        except Exception:
            ok = False
        if returned:
            self._returned = True
            release_cb = self._release_cb
            if release_cb is not None:
                self._release_cb = None
                try:
                    release_cb()
                except Exception:
                    pass
        return ok

    def __enter__(self) -> "_LoanedSamples":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.return_loan()
        return False

    def __del__(self):
        try:
            self.return_loan()
        except Exception:
            pass


class _ReaderListener(fastdds.DataReaderListener):
    """Listener that enqueues callbacks to the executor queue."""

    def __init__(
        self,
        enqueue_cb,
        user_cb,
        msg_ctor,
        raw_mode: bool = False,
        reader_lock=None,
        loaned_samples_cls=None,
        auto_loan_receive: bool = False,
        loan_activate_fn=None,
        cuda_attach_fn=None,
        expose_fields: bool = True,
        batch_callback: bool = False,
        batch_size: int | None = None,
        content_filter_predicate=None,
    ):
        super().__init__()
        self._enqueue_cb = enqueue_cb
        self._user_cb = user_cb
        self._msg_ctor = msg_ctor
        self._raw_mode = raw_mode
        self._reader_lock = reader_lock
        self._loaned_samples_cls = loaned_samples_cls
        self._auto_loan_receive = bool(auto_loan_receive and loaned_samples_cls is not None)
        self._loan_activate_fn = loan_activate_fn
        self._auto_loan_receive_count = 0
        self._pending_lock = threading.Lock()
        self._callback_pending = False
        self._reschedule_requested = False
        # Cache the import once at construction time instead of every callback
        self._expose_fn = expose_callable_fields if (expose_fields and not raw_mode) else None
        self._has_callback = callable(user_cb)
        self._with_message_info = self._has_callback and _callback_accepts_message_info(user_cb)
        self._cuda_attach_fn = cuda_attach_fn
        self._closed = False
        self._dropped_reschedules = 0
        self._expose_fields = bool(expose_fields)
        self._enqueued_callback_count = 0
        self._batch_callback = bool(batch_callback)
        self._batch_size = max(1, int(batch_size or _MAX_CALLBACKS_PER_DRAIN))
        self._content_filter_predicate = content_filter_predicate

    def close(self) -> None:
        with self._pending_lock:
            self._closed = True
            self._has_callback = False
            self._callback_pending = False
            self._reschedule_requested = False

    def _is_closed(self) -> bool:
        with self._pending_lock:
            return self._closed

    def set_cuda_attach_fn(self, fn) -> None:
        self._cuda_attach_fn = fn

    def _attach_cuda_ipc(self, data) -> None:
        fn = self._cuda_attach_fn
        if fn is None or data is None:
            return
        try:
            fn(data)
        except Exception:
            pass

    def set_auto_loan_receive(self, enabled: bool) -> None:
        self._auto_loan_receive = bool(enabled and self._loaned_samples_cls is not None)

    @property
    def auto_loan_receive_count(self) -> int:
        return self._auto_loan_receive_count

    @property
    def dropped_reschedules(self) -> int:
        return self._dropped_reschedules

    @property
    def enqueued_callback_count(self) -> int:
        return self._enqueued_callback_count

    def on_subscription_matched(self, reader, info):
        """Called when subscription matches/unmatches with a publisher."""
        pass

    def _read_or_take_one_from_reader(self, reader, *, include_message_info: bool):
        info = fastdds.SampleInfo()
        data = self._msg_ctor()
        method = getattr(reader, "take_next_sample", None)
        if method is None:
            return None

        try:
            rc = method(data, info)
        except TypeError:
            rc = method(info, data)
        except Exception:
            return None

        if not _retcode_is_ok(rc, none_is_ok=True):
            return None
        if not bool(_sample_info_attr(info, "valid_data", True)):
            return _SKIP_SAMPLE

        expose_fn = self._expose_fn
        if expose_fn is not None:
            try:
                expose_fn(data)
            except Exception:
                pass
        self._attach_cuda_ipc(data)
        msg_info = MessageInfo(info) if include_message_info else None
        return data, msg_info

    def _read_many_from_reader(self, reader, max_count: int):
        results = []
        for _ in range(max_count):
            result = self._read_one_from_reader(reader)
            if result is None:
                break
            if result is _SKIP_SAMPLE:
                continue
            results.append(result)
        return results

    def _take_one_from_reader(self, reader):
        return self._read_or_take_one_from_reader(reader, include_message_info=True)

    def _read_one_from_reader(self, reader):
        return self._read_or_take_one_from_reader(reader, include_message_info=self._with_message_info)

    def _loaned_take_one_from_reader(self, reader):
        loan_cls = self._loaned_samples_cls
        if loan_cls is None:
            return None
        loaned = _LoanedSamples(loan_cls(), raw_mode=self._raw_mode, expose_fields=self._expose_fields)
        try:
            with self._reader_lock if self._reader_lock is not None else _NullContext():
                ok = loaned._native.take(reader, 1)
                if not ok or len(loaned) <= 0:
                    loaned.return_loan()
                    return None
                sample = loaned[0]
                if sample is None:
                    loaned.return_loan()
                    return _SKIP_SAMPLE
                activate = self._loan_activate_fn
                if activate is not None:
                    try:
                        loaned = activate(loaned)
                    except Exception:
                        loaned.return_loan()
                        return None
            self._attach_cuda_ipc(sample)
            msg_info = loaned.info(0) if self._with_message_info else None
            callback_owned_loan = None if _attach_loan_to_sample(sample, loaned) else loaned
            self._auto_loan_receive_count += 1
            return sample, msg_info, callback_owned_loan
        except Exception:
            loaned.return_loan()
            return None

    def _loaned_take_many_from_reader(self, reader, max_count: int):
        loan_cls = self._loaned_samples_cls
        if loan_cls is None:
            return []
        loaned = _LoanedSamples(loan_cls(), raw_mode=self._raw_mode, expose_fields=self._expose_fields)
        try:
            with self._reader_lock if self._reader_lock is not None else _NullContext():
                ok = loaned._native.take(reader, max_count)
                if not ok or len(loaned) <= 0:
                    loaned.return_loan()
                    return []
                results = []
                for index in range(len(loaned)):
                    sample = loaned[index]
                    if sample is None:
                        continue
                    msg_info = loaned.info(index) if self._with_message_info else None
                    self._auto_loan_receive_count += 1
                    results.append((sample, msg_info, loaned))
                if not results:
                    loaned.return_loan()
                else:
                    activate = self._loan_activate_fn
                    if activate is not None:
                        try:
                            loaned = activate(loaned)
                        except Exception:
                            loaned.return_loan()
                            return []
                        results = [(sample, msg_info, loaned) for sample, msg_info, _old in results]
            for sample, _msg_info, _loaned in results:
                self._attach_cuda_ipc(sample)
            return results
        except Exception:
            loaned.return_loan()
            return []

    def _invoke_user_callback(self, data, msg_info):
        if self._with_message_info:
            result = self._user_cb(data, msg_info)
        else:
            result = self._user_cb(data)
        if inspect.iscoroutine(result):
            run_coroutine(result)

    def _enqueue_user_callback(self, data, msg_info, loaned: Optional[_LoanedSamples] = None):
        predicate = self._content_filter_predicate
        if predicate is not None:
            try:
                if not predicate(data):
                    if loaned is not None:
                        loaned.return_loan()
                    return
            except Exception:
                if loaned is not None:
                    loaned.return_loan()
                return
        if loaned is not None:
            if self._with_message_info:
                def callback_with_loan(_msg=None, listener=self, user_cb=self._user_cb, sample=data, info=msg_info, samples=loaned):
                    try:
                        if not listener._is_closed():
                            result = user_cb(sample, info)
                            if inspect.iscoroutine(result):
                                run_coroutine(result)
                    finally:
                        samples.return_loan()
            else:
                def callback_with_loan(_msg=None, listener=self, user_cb=self._user_cb, sample=data, samples=loaned):
                    try:
                        if not listener._is_closed():
                            result = user_cb(sample)
                            if inspect.iscoroutine(result):
                                run_coroutine(result)
                    finally:
                        samples.return_loan()

            # Release the reader loan if a bounded node queue drops this
            # callback before it runs; otherwise the loan leaks forever.
            callback_with_loan._lwrclpy_on_dropped = loaned.return_loan
            try:
                self._enqueue_cb(callback_with_loan, None)
                self._enqueued_callback_count += 1
            except Exception:
                loaned.return_loan()
            return

        if self._with_message_info:
            def callback_with_info(_msg=None, listener=self, user_cb=self._user_cb, sample=data, info=msg_info):
                if listener._is_closed():
                    return
                result = user_cb(sample, info)
                if inspect.iscoroutine(result):
                    run_coroutine(result)

            callback = callback_with_info
        else:
            def callback(_msg=None, listener=self, user_cb=self._user_cb, sample=data):
                if listener._is_closed():
                    return
                result = user_cb(sample)
                if inspect.iscoroutine(result):
                    run_coroutine(result)

        self._enqueue_cb(callback, None)
        self._enqueued_callback_count += 1

    def _enqueue_user_batch_callback(self, items):
        if not items:
            return
        predicate = self._content_filter_predicate
        if predicate is not None:
            filtered = []
            rejected_loans = []
            for item in items:
                try:
                    if predicate(item[0]):
                        filtered.append(item)
                    elif len(item) == 3 and item[2] is not None and item[2] not in rejected_loans:
                        rejected_loans.append(item[2])
                except Exception:
                    if len(item) == 3 and item[2] is not None and item[2] not in rejected_loans:
                        rejected_loans.append(item[2])
            for samples in rejected_loans:
                samples.return_loan()
            items = filtered
            if not items:
                return
        loans = []
        if self._with_message_info:
            messages = []
            infos = []
            for item in items:
                data, msg_info = item[:2]
                messages.append(data)
                infos.append(msg_info)
                if len(item) == 3 and item[2] is not None and item[2] not in loans:
                    loans.append(item[2])

            def callback_batch(_msg=None, listener=self, user_cb=self._user_cb, payload=messages, info_payload=infos, loaned=tuple(loans)):
                try:
                    if not listener._is_closed():
                        result = user_cb(payload, info_payload)
                        if inspect.iscoroutine(result):
                            run_coroutine(result)
                finally:
                    for samples in loaned:
                        samples.return_loan()
        else:
            batch = []
            for item in items:
                batch.append(item[0])
                if len(item) == 3 and item[2] is not None and item[2] not in loans:
                    loans.append(item[2])

            def callback_batch(_msg=None, listener=self, user_cb=self._user_cb, payload=batch, loaned=tuple(loans)):
                try:
                    if not listener._is_closed():
                        result = user_cb(payload)
                        if inspect.iscoroutine(result):
                            run_coroutine(result)
                finally:
                    for samples in loaned:
                        samples.return_loan()

        def _release_dropped_batch(loaned=tuple(loans)):
            for samples in loaned:
                samples.return_loan()

        callback_batch._lwrclpy_on_dropped = _release_dropped_batch
        try:
            self._enqueue_cb(callback_batch, None)
            self._enqueued_callback_count += 1
        except Exception:
            for samples in loans:
                samples.return_loan()

    def _drain_reader_callbacks(self, reader):
        if self._is_closed():
            return
        hit_drain_limit = False
        try:
            if self._batch_callback:
                limit = min(_MAX_CALLBACKS_PER_DRAIN, self._batch_size)
                if self._auto_loan_receive:
                    items = self._loaned_take_many_from_reader(reader, limit)
                elif self._reader_lock is not None:
                    with self._reader_lock:
                        items = self._read_many_from_reader(reader, limit)
                else:
                    items = self._read_many_from_reader(reader, limit)
                self._enqueue_user_batch_callback(items)
                hit_drain_limit = len(items) >= limit
            else:
                if self._auto_loan_receive:
                    count = 0
                    for _ in range(_MAX_CALLBACKS_PER_DRAIN):
                        result = self._loaned_take_one_from_reader(reader)
                        if result is None:
                            break
                        if result is _SKIP_SAMPLE:
                            continue
                        data, msg_info, loaned = result
                        self._enqueue_user_callback(data, msg_info, loaned)
                        count += 1
                    hit_drain_limit = count >= _MAX_CALLBACKS_PER_DRAIN
                else:
                    if self._reader_lock is not None:
                        with self._reader_lock:
                            items = self._read_many_from_reader(reader, _MAX_CALLBACKS_PER_DRAIN)
                    else:
                        items = self._read_many_from_reader(reader, _MAX_CALLBACKS_PER_DRAIN)
                    for data, msg_info in items:
                        self._enqueue_user_callback(data, msg_info, None)
                    hit_drain_limit = len(items) >= _MAX_CALLBACKS_PER_DRAIN
        finally:
            schedule_again = False
            with self._pending_lock:
                if self._closed:
                    self._reschedule_requested = False
                    self._callback_pending = False
                elif hit_drain_limit or self._reschedule_requested:
                    self._reschedule_requested = False
                    schedule_again = True
                else:
                    self._callback_pending = False
            if schedule_again:
                self._enqueue_drain(reader)

    def _enqueue_drain(self, reader):
        def drain_task(_msg=None, listener=self, reader=reader):
            listener._drain_reader_callbacks(reader)

        def _on_drain_dropped(listener=self):
            with listener._pending_lock:
                listener._callback_pending = False
                listener._reschedule_requested = False

        drain_task._lwrclpy_on_dropped = _on_drain_dropped

        if self._is_closed():
            return
        try:
            self._enqueue_cb(drain_task, None)
        except Exception:
            with self._pending_lock:
                self._callback_pending = False
                self._reschedule_requested = False
    
    def on_data_available(self, reader):
        with self._pending_lock:
            if self._closed or not self._has_callback:
                return
            if self._callback_pending:
                self._reschedule_requested = True
                self._dropped_reschedules += 1
                return
            self._callback_pending = True
        self._enqueue_drain(reader)


def _callback_accepts_message_info(callback) -> bool:
    try:
        sig = inspect.signature(callback)
    except Exception:
        return False
    params = list(sig.parameters.values())
    if any(param.kind == param.VAR_POSITIONAL for param in params):
        return True
    positional = [
        param for param in params
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 2


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class Subscription:
    """Subscription managing Subscriber/DataReader with zero-copy friendly QoS.
    コールバックは DDS リスナーで受信し、Executor にキューイングする。"""

    def __init__(self, participant, topic, qos: QoSProfile, callback, msg_ctor, enqueue_cb, 
                 *, raw: bool = False, event_callbacks=None, pubsub_cls=None, msg_module=None,
                 expose_fields: bool = True, batch_callback: bool = False,
                 batch_size: int | None = None, qos_overriding_options=None,
                 content_filter_options=None):
        self._participant = participant
        self._topic = topic
        self._qos_profile = qos
        self._callback = callback
        self._msg_ctor = msg_ctor
        self._msg_module = msg_module
        self._destroyed = False
        self._raw_mode = raw
        self._expose_fields = bool(expose_fields)
        self._event_callbacks = event_callbacks
        self._qos_overriding_options = qos_overriding_options
        self._content_filter_options = content_filter_options
        self._content_filter_predicate = _make_content_filter_predicate(content_filter_options)
        self._message_count = 0
        self._take_count = 0
        self._stats_started_at = time.monotonic()
        self._reader_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._no_active_loans = threading.Condition(self._state_lock)
        self._active_loans = 0
        self._destroy_loan_timeout = float(os.environ.get("LWRCLPY_DESTROY_LOAN_TIMEOUT", "1.0"))

        # Create Subscriber
        sub_qos = fastdds.SubscriberQos()
        participant.get_default_subscriber_qos(sub_qos)
        self._subscriber = participant.create_subscriber(sub_qos)
        if self._subscriber is None:
            raise RuntimeError("Failed to create Subscriber")

        # Prepare Reader QoS (map from high-level QoSProfile first)
        rq = fastdds.DataReaderQos()
        self._subscriber.get_default_datareader_qos(rq)
        qos.apply_to_reader(rq)

        self._data_sharing_enabled = (
            _pubsub_type_supports_data_sharing(pubsub_cls)
            and _force_data_sharing_on_reader(rq)
        )
        self._is_fixed_size_type = _pubsub_type_is_plain(pubsub_cls)
        self._loaned_samples_cls_value = _resolve_loaned_samples_cls(msg_module, msg_ctor)

        # Listener enqueue to executor queue
        self._listener = _ReaderListener(
            enqueue_cb,
            callback,
            msg_ctor,
            raw_mode=raw,
            reader_lock=self._reader_lock,
            loaned_samples_cls=self._loaned_samples_cls_value,
            auto_loan_receive=False,
            loan_activate_fn=self._activate_loaned_samples,
            expose_fields=expose_fields,
            batch_callback=batch_callback,
            batch_size=batch_size,
            content_filter_predicate=self._content_filter_predicate,
        )

        # Create DataReader with listener
        reader = None
        try:
            reader = self._subscriber.create_datareader(self._topic, rq, self._listener)
        except TypeError:
            reader = self._subscriber.create_datareader(self._topic, rq)
            try:
                reader.set_listener(self._listener)
            except AttributeError:
                pass
        if reader is None and self._data_sharing_enabled:
            _disable_data_sharing_on_reader(rq)
            self._data_sharing_enabled = False
            try:
                reader = self._subscriber.create_datareader(self._topic, rq, self._listener)
            except TypeError:
                reader = self._subscriber.create_datareader(self._topic, rq)
                try:
                    reader.set_listener(self._listener)
                except AttributeError:
                    pass

        if reader is None:
            raise RuntimeError("Failed to create DataReader")
        self._reader = reader
        self._listener.set_auto_loan_receive(self._automatic_loaned_receive_enabled)
        self._cuda_ipc_topic_name = ""
        self._cuda_ipc_latest_by_field = {}
        self._shm_topic_name = ""
        self._shm_latest_by_field = {}
        self._shm_local_registration = None
        self._shm_auto_fields = tuple(
            field.strip()
            for field in os.environ.get("LWRCLPY_AUTO_SHM_FIELDS", "data").split(",")
            if field.strip()
        )
        self._max_callbacks_per_drain = _MAX_CALLBACKS_PER_DRAIN

    def _register_loan(self) -> None:
        with self._state_lock:
            if self._destroyed:
                raise RuntimeError("Cannot loan messages from a destroyed Subscription")
            self._active_loans += 1

    def _release_loan(self) -> None:
        with self._state_lock:
            if self._active_loans > 0:
                self._active_loans -= 1
            if self._active_loans == 0:
                self._no_active_loans.notify_all()

    def _activate_loaned_samples(self, loaned: _LoanedSamples) -> _LoanedSamples:
        self._register_loan()
        loaned._release_cb = self._release_loan
        return loaned

    def _set_cuda_ipc_topic(self, topic_name: str) -> None:
        self._cuda_ipc_topic_name = topic_name
        self._listener.set_cuda_attach_fn(self._attach_latest_cuda_ipc)

    def _set_shared_memory_topic(self, topic_name: str) -> None:
        self._shm_topic_name = topic_name
        self._listener.set_cuda_attach_fn(self._attach_latest_side_channels)
        try:
            from .shared_memory import register_local_shared_memory_subscriber
            self._shm_local_registration = register_local_shared_memory_subscriber(topic_name)
        except Exception:
            self._shm_local_registration = None

    def _update_cuda_ipc_metadata(self, metadata_text: str) -> None:
        try:
            from .cuda_ipc import CudaIpcMetadata
            metadata = CudaIpcMetadata.from_json(metadata_text)
        except Exception:
            return
        if self._cuda_ipc_topic_name and metadata.topic != self._cuda_ipc_topic_name:
            return
        self._cuda_ipc_latest_by_field[metadata.field] = metadata

    def _attach_latest_cuda_ipc(self, msg) -> None:
        if not self._cuda_ipc_latest_by_field:
            return
        try:
            from .cuda_ipc import attach_cuda_buffer
            for metadata in tuple(self._cuda_ipc_latest_by_field.values()):
                if not _side_channel_matches_payload(msg, metadata.field, metadata.nbytes):
                    continue
                attach_cuda_buffer(msg, metadata)
        except Exception:
            pass

    def _update_shared_memory_metadata(self, metadata_text: str) -> None:
        try:
            from .shared_memory import SharedMemoryMetadata, local_host_id
            metadata = SharedMemoryMetadata.from_json(metadata_text)
        except Exception:
            return
        if self._shm_topic_name and metadata.topic != self._shm_topic_name:
            return
        if metadata.host_id and metadata.host_id != local_host_id():
            return
        self._shm_latest_by_field[metadata.field] = metadata

    def _attach_latest_shared_memory(self, msg) -> None:
        if not self._shm_latest_by_field and not self._shm_topic_name:
            return
        try:
            from .shared_memory import attach_shared_memory_buffer
            metadata_items = dict(self._shm_latest_by_field)
            if self._shm_topic_name:
                from .shared_memory import read_latest_metadata
                for field in self._shm_auto_fields:
                    if field not in metadata_items:
                        metadata = read_latest_metadata(self._shm_topic_name, field)
                        if metadata is not None:
                            metadata_items[field] = metadata
                            self._shm_latest_by_field[field] = metadata
            for metadata in tuple(metadata_items.values()):
                if not _side_channel_matches_payload(msg, metadata.field, metadata.nbytes):
                    continue
                attach_shared_memory_buffer(msg, metadata)
        except Exception:
            pass

    def _attach_latest_side_channels(self, msg) -> None:
        self._attach_latest_cuda_ipc(msg)
        self._attach_latest_shared_memory(msg)

    def take(self, max_count: int = 1) -> List[Tuple[Any, MessageInfo]]:
        """Take messages directly from the DataReader (polling mode).
        
        Returns a list of (message, message_info) tuples.
        Callback delivery and manual polling both consume samples directly from
        the reader cache instead of copying them through a Python-side queue.
        """
        if max_count <= 0:
            return []
        results = []
        with self._reader_lock:
            if self._destroyed or self._reader is None:
                return []
            for _ in range(max_count):
                result = self._listener._take_one_from_reader(self._reader)
                if result is None:
                    break
                if result is _SKIP_SAMPLE:
                    continue
                results.append(result)
        self._message_count += len(results)
        self._take_count += len(results)
        
        return results

    def take_one(self) -> Optional[Tuple[Any, MessageInfo]]:
        """Take a single message. Returns (message, info) or None."""
        results = self.take(1)
        return results[0] if results else None

    @property
    def _loaned_samples_cls(self):
        return self._loaned_samples_cls_value

    @property
    def _can_loan_received_messages(self) -> bool:
        return self._loaned_samples_cls is not None

    def _loaned_take(self, max_count: int = 1, *, read: bool = False) -> _LoanedSamples:
        loan_cls = self._loaned_samples_cls
        if loan_cls is None:
            raise RuntimeError(
                "Cannot loan received messages: generated bindings do not "
                "include lwrclpy DataReader loan helpers"
            )
        if max_count <= 0:
            max_count = 0

        native = loan_cls()
        with self._reader_lock:
            if self._destroyed or self._reader is None:
                try:
                    native.return_loan()
                except Exception:
                    pass
                return _LoanedSamples(native, raw_mode=self._raw_mode, expose_fields=self._expose_fields)
            ok = native.read(self._reader, max_count) if read else native.take(self._reader, max_count)
            if not ok:
                try:
                    native.return_loan()
                except Exception:
                    pass
                return _LoanedSamples(native, raw_mode=self._raw_mode, expose_fields=self._expose_fields)
            loaned = _LoanedSamples(native, raw_mode=self._raw_mode, expose_fields=self._expose_fields)
            try:
                return self._activate_loaned_samples(loaned)
            except Exception:
                loaned.return_loan()
                raise

    def _loaned_read(self, max_count: int = 1) -> _LoanedSamples:
        return self._loaned_take(max_count, read=True)

    def get_publisher_count(self) -> int:
        """Return the number of publishers matched to this subscription."""
        with self._reader_lock:
            if self._destroyed or self._reader is None:
                return 0
            reader = self._reader
            status_method = getattr(reader, "get_subscription_matched_status", None)
            if status_method is not None:
                count = _matched_status_count(status_method, getattr(fastdds, "SubscriptionMatchedStatus", None))
                if count is not None:
                    return count
            handles_method = getattr(reader, "get_matched_publications", None)
            if handles_method is not None:
                count = _matched_handle_count(handles_method, getattr(fastdds, "InstanceHandleVector", None))
                if count is not None:
                    return count
            return 0

    @property
    def _automatic_loaned_receive_enabled(self) -> bool:
        return (
            self._data_sharing_enabled
            and self._is_fixed_size_type
            and self._loaned_samples_cls_value is not None
        )

    @property
    def _auto_loan_receive_count(self) -> int:
        return self._listener.auto_loan_receive_count

    @property
    def performance_stats(self) -> dict[str, object]:
        elapsed = max(1e-9, time.monotonic() - self._stats_started_at)
        delivered = self._take_count + self._listener.enqueued_callback_count
        return {
            "message_count": self._message_count,
            "take_count": self._take_count,
            "enqueued_callback_count": self._listener.enqueued_callback_count,
            "delivered_rate_hz": delivered / elapsed,
            "data_sharing_enabled": self._data_sharing_enabled,
            "can_loan_received_messages": self._can_loan_received_messages,
            "automatic_loaned_receive_enabled": self._automatic_loaned_receive_enabled,
            "auto_loan_receive_count": self._auto_loan_receive_count,
            "max_callbacks_per_drain": self._max_callbacks_per_drain,
            "batch_callback": self._listener._batch_callback,
            "batch_size": self._listener._batch_size,
            "reschedule_requests_while_pending": self._listener.dropped_reschedules,
        }

    def reset_performance_stats(self) -> None:
        self._message_count = 0
        self._take_count = 0
        self._stats_started_at = time.monotonic()
        self._listener._auto_loan_receive_count = 0
        self._listener._dropped_reschedules = 0
        self._listener._enqueued_callback_count = 0

    def destroy(self) -> None:
        """Destroy the Fast DDS DataReader and Subscriber owned by this object."""
        with self._state_lock:
            if self._destroyed and self._reader is None and self._subscriber is None:
                return
            self._destroyed = True

        registration = getattr(self, "_shm_local_registration", None)
        if registration is not None:
            try:
                registration.close()
            except Exception:
                pass
            self._shm_local_registration = None

        listener = getattr(self, "_listener", None)
        if listener is not None:
            close = getattr(listener, "close", None)
            if callable(close):
                close()

        with self._state_lock:
            deadline = time.monotonic() + max(0.0, self._destroy_loan_timeout)
            while self._active_loans > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._no_active_loans.wait(timeout=remaining)
            timed_out = self._active_loans > 0
            if timed_out:
                _logger.warning(
                    "Subscription.destroy timed out waiting for active receive loans "
                    "(loans=%d); skipping DDS entity deletion",
                    self._active_loans,
                )
                return

        with self._reader_lock:
            reader = self._reader
            subscriber = self._subscriber
            if reader is not None:
                try:
                    set_listener = getattr(reader, "set_listener", None)
                    if callable(set_listener):
                        set_listener(None)
                except Exception:
                    pass
                try:
                    delete_reader = getattr(subscriber, "delete_datareader", None) if subscriber is not None else None
                    if callable(delete_reader):
                        delete_reader(reader)
                except Exception:
                    pass
            if subscriber is not None:
                try:
                    delete_subscriber = getattr(self._participant, "delete_subscriber", None)
                    if callable(delete_subscriber):
                        delete_subscriber(subscriber)
                except Exception:
                    pass
            self._reader = None
            self._subscriber = None

    def get_topic_name(self) -> str:
        try:
            return self._topic.get_name()
        except Exception:
            return getattr(self._topic, "m_topicName", "")
