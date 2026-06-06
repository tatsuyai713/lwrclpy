# lwrclpy/subscription.py
# DDS DataReader wrapper that enqueues received samples for executor-driven callbacks.
# Implements copy according to fastddsgen-generated getter/setter conventions.
# Supports zero-copy with Fast DDS data sharing where compatible.

from __future__ import annotations
from typing import Optional, List, Tuple, Any, Iterator
import asyncio
import inspect
import fastdds  # type: ignore
import os
import threading
from .qos import QoSProfile
from .message_utils import expose_callable_fields
from .utils import (
    _matched_handle_count,
    _matched_status_count,
    _pubsub_type_is_plain,
    _pubsub_type_supports_data_sharing,
    _retcode_is_ok,
)


_MAX_CALLBACKS_PER_DRAIN = 16
_SKIP_SAMPLE = object()


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
    __slots__ = ("source_timestamp", "received_timestamp", "publication_sequence_number", 
                 "reception_sequence_number", "publisher_gid", "from_intra_process",
                 "publisher_handle", "_sample_identity", "_is_valid")
    
    def __init__(self, sample_info=None):
        self.source_timestamp = 0
        self.received_timestamp = 0
        self.publication_sequence_number = 0
        self.reception_sequence_number = 0
        self.publisher_gid = None
        self.publisher_handle = None
        self.from_intra_process = False
        self._sample_identity = None
        self._is_valid = True
        
        if sample_info is not None:
            try:
                self._is_valid = bool(_sample_info_attr(sample_info, "valid_data", True))
                self._sample_identity = _sample_info_attr(sample_info, "sample_identity")
                # Extract timestamp
                ts = _sample_info_attr(sample_info, "source_timestamp")
                if ts is not None:
                    sec = _sample_info_attr(ts, "seconds", 0)
                    nsec = _sample_info_attr(ts, "nanosec", 0)
                    self.source_timestamp = sec * 1_000_000_000 + nsec
                
                # Extract sequence numbers if available
                if hasattr(sample_info, "publication_sequence_number"):
                    self.publication_sequence_number = _sample_info_attr(sample_info, "publication_sequence_number", 0)
                if hasattr(sample_info, "reception_sequence_number"):
                    self.reception_sequence_number = _sample_info_attr(sample_info, "reception_sequence_number", 0)
                if hasattr(sample_info, "publisher_gid"):
                    self.publisher_gid = _sample_info_attr(sample_info, "publisher_gid")
                if hasattr(sample_info, "publication_handle"):
                    self.publisher_handle = _sample_info_attr(sample_info, "publication_handle")
                if self.publisher_gid is None and self._sample_identity is not None and hasattr(self._sample_identity, "writer_guid"):
                    self.publisher_gid = _sample_info_attr(self._sample_identity, "writer_guid")
                    
                # Check for intra-process delivery
                if hasattr(sample_info, "from_intra_process"):
                    self.from_intra_process = bool(_sample_info_attr(sample_info, "from_intra_process", False))
            except Exception:
                pass

    @property
    def publisher_guid(self):
        return self.publisher_gid

    @property
    def sequence_number(self):
        return self.publication_sequence_number

    @property
    def sample_identity(self):
        return self._sample_identity

    @property
    def is_valid(self):
        return self._is_valid


class _LoanedSamples:
    """Container for DataReader-loaned samples.

    Samples are valid until ``return_loan()`` is called.  Use it as a context
    manager when possible so Fast DDS reader resources are returned promptly.
    """

    __slots__ = ("_native", "_expose_fn", "_returned")

    def __init__(self, native, *, raw_mode: bool = False):
        self._native = native
        self._expose_fn = None if raw_mode else expose_callable_fields
        self._returned = False

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
        return MessageInfo(info)

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
        try:
            ok = bool(self._native.return_loan())
        except Exception:
            ok = False
        self._returned = True
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
    ):
        super().__init__()
        self._enqueue_cb = enqueue_cb
        self._user_cb = user_cb
        self._msg_ctor = msg_ctor
        self._raw_mode = raw_mode
        self._reader_lock = reader_lock
        self._loaned_samples_cls = loaned_samples_cls
        self._auto_loan_receive = bool(auto_loan_receive and loaned_samples_cls is not None)
        self._auto_loan_receive_count = 0
        self._pending_lock = threading.Lock()
        self._callback_pending = False
        self._reschedule_requested = False
        # Cache the import once at construction time instead of every callback
        self._expose_fn = None if raw_mode else expose_callable_fields
        self._has_callback = callable(user_cb)
        self._with_message_info = self._has_callback and _callback_accepts_message_info(user_cb)

    def set_auto_loan_receive(self, enabled: bool) -> None:
        self._auto_loan_receive = bool(enabled and self._loaned_samples_cls is not None)

    @property
    def auto_loan_receive_count(self) -> int:
        return self._auto_loan_receive_count

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
        msg_info = MessageInfo(info) if include_message_info else None
        return data, msg_info

    def _take_one_from_reader(self, reader):
        return self._read_or_take_one_from_reader(reader, include_message_info=True)

    def _read_one_from_reader(self, reader):
        return self._read_or_take_one_from_reader(reader, include_message_info=self._with_message_info)

    def _loaned_take_one_from_reader(self, reader):
        loan_cls = self._loaned_samples_cls
        if loan_cls is None:
            return None
        loaned = _LoanedSamples(loan_cls(), raw_mode=self._raw_mode)
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
            msg_info = loaned.info(0) if self._with_message_info else None
            callback_owned_loan = None if _attach_loan_to_sample(sample, loaned) else loaned
            self._auto_loan_receive_count += 1
            return sample, msg_info, callback_owned_loan
        except Exception:
            loaned.return_loan()
            return None

    def _invoke_user_callback(self, data, msg_info):
        if self._with_message_info:
            result = self._user_cb(data, msg_info)
        else:
            result = self._user_cb(data)
        if inspect.iscoroutine(result):
            asyncio.run(result)

    def _enqueue_user_callback(self, data, msg_info, loaned: Optional[_LoanedSamples] = None):
        if loaned is not None:
            if self._with_message_info:
                def callback_with_loan(_msg=None, user_cb=self._user_cb, sample=data, info=msg_info, samples=loaned):
                    try:
                        result = user_cb(sample, info)
                        if inspect.iscoroutine(result):
                            asyncio.run(result)
                    finally:
                        samples.return_loan()
            else:
                def callback_with_loan(_msg=None, user_cb=self._user_cb, sample=data, samples=loaned):
                    try:
                        result = user_cb(sample)
                        if inspect.iscoroutine(result):
                            asyncio.run(result)
                    finally:
                        samples.return_loan()

            self._enqueue_cb(callback_with_loan, None)
            return

        if self._with_message_info:
            def callback_with_info(_msg=None, user_cb=self._user_cb, sample=data, info=msg_info):
                result = user_cb(sample, info)
                if inspect.iscoroutine(result):
                    asyncio.run(result)

            self._enqueue_cb(callback_with_info, None)
        else:
            self._enqueue_cb(self._user_cb, data)

    def _drain_reader_callbacks(self, reader):
        hit_drain_limit = False
        try:
            for _ in range(_MAX_CALLBACKS_PER_DRAIN):
                if self._auto_loan_receive:
                    result = self._loaned_take_one_from_reader(reader)
                elif self._reader_lock is not None:
                    with self._reader_lock:
                        result = self._read_one_from_reader(reader)
                else:
                    result = self._read_one_from_reader(reader)
                if result is None:
                    break
                if result is _SKIP_SAMPLE:
                    continue
                if len(result) == 3:
                    data, msg_info, loaned = result
                else:
                    data, msg_info = result
                    loaned = None
                self._enqueue_user_callback(data, msg_info, loaned)
            else:
                hit_drain_limit = True
        finally:
            schedule_again = False
            with self._pending_lock:
                if hit_drain_limit or self._reschedule_requested:
                    self._reschedule_requested = False
                    schedule_again = True
                else:
                    self._callback_pending = False
            if schedule_again:
                self._enqueue_drain(reader)

    def _enqueue_drain(self, reader):
        def drain_task(_msg=None, listener=self, reader=reader):
            listener._drain_reader_callbacks(reader)

        self._enqueue_cb(drain_task, None)
    
    def on_data_available(self, reader):
        if not self._has_callback:
            return
        with self._pending_lock:
            if self._callback_pending:
                self._reschedule_requested = True
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
                 *, raw: bool = False, event_callbacks=None, pubsub_cls=None, msg_module=None):
        self._participant = participant
        self._topic = topic
        self._callback = callback
        self._msg_ctor = msg_ctor
        self._msg_module = msg_module
        self._destroyed = False
        self._raw_mode = raw
        self._event_callbacks = event_callbacks or {}
        self._message_count = 0
        self._reader_lock = threading.Lock()

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
            for _ in range(max_count):
                result = self._listener._take_one_from_reader(self._reader)
                if result is None:
                    break
                if result is _SKIP_SAMPLE:
                    continue
                results.append(result)
        self._message_count += len(results)
        
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
            ok = native.read(self._reader, max_count) if read else native.take(self._reader, max_count)
        if not ok:
            try:
                native.return_loan()
            except Exception:
                pass
            return _LoanedSamples(native, raw_mode=self._raw_mode)
        return _LoanedSamples(native, raw_mode=self._raw_mode)

    def _loaned_read(self, max_count: int = 1) -> _LoanedSamples:
        return self._loaned_take(max_count, read=True)

    def get_publisher_count(self) -> int:
        """Return the number of publishers matched to this subscription."""
        status_method = getattr(self._reader, "get_subscription_matched_status", None)
        if status_method is not None:
            count = _matched_status_count(status_method, getattr(fastdds, "SubscriptionMatchedStatus", None))
            if count is not None:
                return count
        handles_method = getattr(self._reader, "get_matched_publications", None)
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

    def destroy(self) -> None:
        """Mark as destroyed. Fast DDS will clean up resources automatically."""
        if self._destroyed:
            return
        self._destroyed = True
        
        # Don't explicitly delete Fast DDS entities - let Fast DDS handle cleanup
        # Attempting to delete them causes "double free" errors
        # Fast DDS will automatically clean up when the participant is destroyed
        self._reader = None
        self._subscriber = None

    def get_topic_name(self) -> str:
        try:
            return self._topic.get_name()
        except Exception:
            return getattr(self._topic, "m_topicName", "")
