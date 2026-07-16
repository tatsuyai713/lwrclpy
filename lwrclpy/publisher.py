# lwrclpy/publisher.py
# Zero-copy–friendly DataWriter wrapper for Fast DDS v3.
# - Prefer DDS internal zero-copy (DataSharing) where available.
# - Keep compatibility with QoSProfile mapping.

from __future__ import annotations
import fastdds  # type: ignore
import logging
import os
import sys
import threading
import time
from typing import TypeVar, Generic
from .qos import QoSProfile
from .message_utils import clone_message, expose_callable_fields, _assign
from .message_utils import _buffer_view, _copy_val, _get_field_names, _get_value, _is_swig_vector
from .duration import Duration
from .utils import (
    _matched_handle_count,
    _matched_status_count,
    _pubsub_type_is_plain,
    _pubsub_type_supports_data_sharing,
    _retcode_is_ok,
    env_int,
    set_fastdds_duration,
)

T = TypeVar('T')
_logger = logging.getLogger(__name__)


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.environ.get(name, default)))
    except Exception:
        return default


_DESTROY_ACK_TIMEOUT = _env_float("LWRCLPY_DESTROY_ACK_TIMEOUT", 0.25)


def _materialize_shadow_attributes(msg) -> bool:
    """Apply rclpy-style shadow attributes to their SWIG setters in-place."""
    inst_dict = getattr(msg, "__dict__", None)
    if not inst_dict:
        return False
    msg_cls = type(msg)
    materialized = False
    for name, value in list(inst_dict.items()):
        if name.startswith("_") or name in {"this", "thisown"}:
            continue
        try:
            class_attr = getattr(msg_cls, name, None)
        except Exception:
            class_attr = None
        if callable(class_attr):
            if callable(value):
                try:
                    value = value()
                except Exception:
                    pass
            try:
                delattr(msg, name)
            except Exception:
                try:
                    inst_dict.pop(name, None)
                except Exception:
                    pass
            materialized = _assign(msg, name, value) or materialized
    return materialized


def _copy_message_into(src, dst, *, skip_fields: set[str] | None = None) -> bool:
    """Copy generated message fields from *src* into existing *dst*."""
    copied = False
    skip_fields = skip_fields or set()
    for name in _get_field_names(type(dst)):
        if name.startswith("_") or name in {"this", "thisown"} or name in skip_fields:
            continue
        value = _get_value(src, name)
        if value is None:
            continue
        view = _buffer_view(value)
        if view is not None and _assign(dst, name, view):
            copied = True
            continue
        # Avoid materializing large arrays as Python bytes when copying into a
        # loaned sample.  The generated setter can copy the native SWIG vector
        # directly, which keeps rclpy-visible behavior unchanged while removing
        # a large intermediate allocation.
        if _is_swig_vector(value) and _assign(dst, name, value):
            copied = True
            continue
        copied = _assign(dst, name, _copy_val(value)) or copied
    return copied


def _write_checked(writer, msg) -> None:
    rc = writer.write(msg)
    if not _retcode_is_ok(rc, none_is_ok=True):
        raise RuntimeError(f"Fast DDS DataWriter.write failed: retcode={rc!r}")


def _wait_writer_acked(writer, timeout_sec: float) -> None:
    if writer is None or timeout_sec <= 0:
        return
    wait = getattr(writer, "wait_for_acknowledgments", None)
    if not callable(wait):
        return
    try:
        duration = fastdds.Duration_t()
        total_ns = int(timeout_sec * 1_000_000_000)
        set_fastdds_duration(duration, total_ns // 1_000_000_000, total_ns % 1_000_000_000)
        wait(duration)
    except Exception:
        pass


def _force_data_sharing_on_writer(wq: "fastdds.DataWriterQos") -> bool:
    """Prefer/force data sharing on the writer QoS when the API exists."""
    if os.environ.get("LWRCLPY_NO_DATASHARING") == "1":
        return False
    if sys.platform == "win32" and os.environ.get("LWRCLPY_ENABLE_WINDOWS_DATASHARING") != "1":
        return False
    try:
        if hasattr(wq, "data_sharing"):
            ds = wq.data_sharing()
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


def _disable_data_sharing_on_writer(wq: "fastdds.DataWriterQos") -> None:
    try:
        if hasattr(wq, "data_sharing"):
            ds = wq.data_sharing()
            if hasattr(ds, "automatic"):
                ds.automatic()
            elif hasattr(ds, "off"):
                ds.off()
    except Exception:
        pass


class _LoanedMessage(Generic[T]):
    """Internal wrapper for a DataWriter loaned sample."""

    __slots__ = ("_publisher", "_msg", "_from_middleware", "_published", "_addr", "_released")

    def __init__(self, publisher: "Publisher", msg: T, from_middleware: bool, addr: int = 0):
        object.__setattr__(self, "_publisher", publisher)
        object.__setattr__(self, "_msg", msg)
        object.__setattr__(self, "_from_middleware", from_middleware)
        object.__setattr__(self, "_published", False)
        object.__setattr__(self, "_addr", int(addr or 0))
        object.__setattr__(self, "_released", False)
        publisher._register_loan()

    def __getattr__(self, name):
        return getattr(self._msg, name)

    def __setattr__(self, name, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            if not _assign(self._msg, name, value):
                setattr(self._msg, name, value)
    
    @property
    def msg(self) -> T:
        """Access the loaned message."""
        return self._msg

    @property
    def is_zero_copy(self) -> bool:
        """Return True when this message was loaned by the middleware."""
        return self._from_middleware

    def __repr__(self):
        return repr(self._msg)

    def __str__(self):
        return str(self._msg)
    
    def __enter__(self) -> T:
        return self._msg
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._published and exc_type is None:
            try:
                self._publisher.publish_loaned(self)
            finally:
                if not self._published:
                    self.release()
        elif exc_type is not None:
            self.release()
        return False

    def release(self) -> None:
        if not self._released:
            object.__setattr__(self, "_released", True)
            self._publisher._release_loan()

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass


class Publisher:
    """Publisher managing Publisher/DataWriter with zero-copy friendly QoS."""

    def __init__(
        self,
        participant,
        topic,
        qos: QoSProfile,
        msg_ctor=None,
        msg_module=None,
        pubsub_cls=None,
        event_callbacks=None,
        qos_overriding_options=None,
    ):
        self._participant = participant
        self._topic = topic
        self._qos_profile = qos
        self._msg_ctor = msg_ctor
        self._msg_module = msg_module
        self._event_callbacks = event_callbacks
        self._qos_overriding_options = qos_overriding_options
        self._destroyed = False
        self._publish_count = 0
        self._stats_started_at = time.monotonic()
        self._cuda_ipc_metadata_pub = None
        self._cuda_ipc_topic_name = ""
        self._cuda_ipc_keepalive = {}
        self._cuda_ipc_keepalive_limit = env_int("LWRCLPY_CUDA_IPC_KEEPALIVE", 32)
        self._cuda_ipc_sequence = 0
        self._cuda_ipc_lock = threading.Lock()
        self._shm_metadata_pub = None
        self._shm_topic_name = ""
        self._shm_keepalive = {}
        self._shm_keepalive_limit = env_int("LWRCLPY_SHM_KEEPALIVE", 32)
        self._shm_sequence = 0
        self._shm_lock = threading.Lock()
        self._auto_shm_threshold = env_int("LWRCLPY_AUTO_SHM_THRESHOLD", 256 * 1024)
        self._shm_subscriber_count_ttl = _env_float("LWRCLPY_SHM_SUBSCRIBER_COUNT_TTL", 0.05)
        self._shm_subscriber_count_cache = 0
        self._shm_subscriber_count_expires_at = 0.0
        self._auto_shm_fields = tuple(
            field.strip()
            for field in os.environ.get("LWRCLPY_AUTO_SHM_FIELDS", "data").split(",")
            if field.strip()
        )
        self._state_lock = threading.Lock()
        self._no_active_writes = threading.Condition(self._state_lock)
        self._active_writes = 0
        self._active_loans = 0
        self._destroy_loan_timeout = float(os.environ.get("LWRCLPY_DESTROY_LOAN_TIMEOUT", "1.0"))
        self._zero_copy_fallback_count = 0
        self._last_zero_copy_fallback_reason = ""

        # Create Publisher
        pub_qos = fastdds.PublisherQos()
        participant.get_default_publisher_qos(pub_qos)
        self._publisher = participant.create_publisher(pub_qos)
        if self._publisher is None:
            raise RuntimeError("Failed to create Publisher")

        # Prepare Writer QoS (map from high-level QoSProfile first)
        wq = fastdds.DataWriterQos()
        self._publisher.get_default_datawriter_qos(wq)
        qos.apply_to_writer(wq)

        self._data_sharing_enabled = (
            _pubsub_type_supports_data_sharing(pubsub_cls)
            and _force_data_sharing_on_writer(wq)
        )
        self._is_fixed_size_type = _pubsub_type_is_plain(pubsub_cls)
        self._auto_loan_publish_count = 0

        # Create DataWriter
        self._writer = self._publisher.create_datawriter(self._topic, wq)
        if self._writer is None and self._data_sharing_enabled:
            _disable_data_sharing_on_writer(wq)
            self._data_sharing_enabled = False
            self._writer = self._publisher.create_datawriter(self._topic, wq)
        if self._writer is None:
            raise RuntimeError("Failed to create DataWriter")

    def _set_cuda_ipc_metadata_publisher(self, publisher, topic_name: str) -> None:
        self._cuda_ipc_metadata_pub = publisher
        self._cuda_ipc_topic_name = topic_name

    def _set_shared_memory_metadata_publisher(self, publisher, topic_name: str) -> None:
        self._shm_metadata_pub = publisher
        self._shm_topic_name = topic_name
        self._shm_subscriber_count_cache = 0
        self._shm_subscriber_count_expires_at = 0.0

    def borrow_loaned_message(self, *, require_zero_copy: bool = True) -> _LoanedMessage:
        """Borrow a message sample for in-place filling before publishing.

        When Fast DDS middleware loaning is available this returns a wrapper
        around the loaned sample, allowing the caller to fill fields directly
        and publish without first creating a separate Python message to copy
        from.  Use it as a context manager or pass it to publish_loaned().
        """
        self._begin_writer_use()
        try:
            return self._loan_message(require_zero_copy=require_zero_copy)
        finally:
            self._end_writer_use()

    def loan_message(self, *, require_zero_copy: bool = True) -> _LoanedMessage:
        """Compatibility alias for borrow_loaned_message()."""
        return self.borrow_loaned_message(require_zero_copy=require_zero_copy)

    def publish_loaned(self, loaned: _LoanedMessage) -> None:
        """Publish a message previously returned by borrow_loaned_message()."""
        if not isinstance(loaned, _LoanedMessage) or loaned._publisher is not self:
            raise ValueError("loaned message was not borrowed from this publisher")
        self._begin_writer_use()
        try:
            self._publish_loaned(loaned)
        finally:
            if not loaned._published:
                loaned.release()
            self._end_writer_use()

    def publish(self, msg) -> None:
        """Publish a message instance generated from the SWIG type."""
        target_ctor = self._msg_ctor if self._msg_ctor is not None else msg.__class__

        self._begin_writer_use()
        try:
            if self._try_publish_auto_shared_memory(msg, target_ctor):
                return

            if self._automatic_loaned_publish_enabled:
                loaned = None
                try:
                    loaned = self._loan_message(require_zero_copy=True)
                    _copy_message_into(msg, loaned._msg)
                    self._publish_loaned(loaned)
                    self._auto_loan_publish_count += 1
                    return
                except Exception as exc:
                    if loaned is not None and not loaned._published:
                        loaned.release()
                    self._record_zero_copy_fallback(exc)

            self._publish_regular_message(msg, target_ctor)
        finally:
            try:
                expose_callable_fields(msg)
            except Exception:
                pass
            self._end_writer_use()

    def _publish_regular_message(self, msg, target_ctor) -> None:
        # Fast path: if msg is already the correct SWIG type, apply any
        # rclpy-style shadow attributes in-place and write the same instance.
        if isinstance(msg, target_ctor):
            _materialize_shadow_attributes(msg)
            _write_checked(self._writer, msg)
        else:
            to_send = clone_message(msg, target_ctor)
            _write_checked(self._writer, to_send)
        self._publish_count += 1

    def _try_publish_auto_shared_memory(self, msg, target_ctor) -> bool:
        if self._shm_metadata_pub is None or self._auto_shm_threshold <= 0:
            return False
        local_shm_subscribers = self._local_shared_memory_subscriber_count()
        if local_shm_subscribers <= 0:
            return False
        for field in self._auto_shm_fields:
            payload = _get_value(msg, field)
            if payload is None:
                continue
            view = _buffer_view(payload)
            if view is None or view.nbytes < self._auto_shm_threshold:
                continue
            if not self._publish_shared_memory_metadata(view, field=field):
                return False
            if self._has_remote_or_plain_dds_subscribers(local_shm_subscribers):
                self._publish_regular_message(msg, target_ctor)
            else:
                signal_msg = self._make_shared_memory_signal_message(msg, target_ctor, field)
                self._publish_regular_message(signal_msg, target_ctor)
            return True
        return False

    def _local_shared_memory_subscriber_count(self) -> int:
        if not self._shm_topic_name:
            return 0
        now = time.monotonic()
        if now < self._shm_subscriber_count_expires_at:
            return self._shm_subscriber_count_cache
        try:
            from .shared_memory import count_local_shared_memory_subscribers
            count = count_local_shared_memory_subscribers(self._shm_topic_name)
        except Exception:
            count = 0
        self._shm_subscriber_count_cache = count
        self._shm_subscriber_count_expires_at = now + self._shm_subscriber_count_ttl
        return count


    def _subscription_count_unlocked(self) -> int:
        writer = self._writer
        if writer is None:
            return 0
        status_method = getattr(writer, "get_publication_matched_status", None)
        if status_method is not None:
            count = _matched_status_count(status_method, getattr(fastdds, "PublicationMatchedStatus", None))
            if count is not None:
                return count
        handles_method = getattr(writer, "get_matched_subscriptions", None)
        if handles_method is not None:
            count = _matched_handle_count(handles_method, getattr(fastdds, "InstanceHandleVector", None))
            if count is not None:
                return count
        return 0

    def _has_remote_or_plain_dds_subscribers(self, local_shm_subscribers: int) -> bool:
        main_subscribers = self._subscription_count_unlocked()
        return main_subscribers <= 0 or main_subscribers > local_shm_subscribers

    def _make_shared_memory_signal_message(self, msg, target_ctor, field: str):
        signal_msg = target_ctor()
        _copy_message_into(msg, signal_msg, skip_fields={field})
        if not _assign(signal_msg, field, memoryview(b"")):
            raise AttributeError(
                f"Failed to clear field {type(signal_msg).__name__}.{field} for side-channel signaling"
            )
        return signal_msg

    def publish_buffer(self, buffer, *, field: str = "data", msg=None) -> None:
        """Publish a message after assigning a bytes-like object to one field.

        This keeps large payloads on the buffer/memoryview assignment path and
        avoids building Python lists or extra bytes objects before publish().
        """
        if msg is None:
            if self._msg_ctor is None:
                raise RuntimeError("publish_buffer requires msg when no message constructor is available")
            msg = self._msg_ctor()
        view = memoryview(buffer)
        if not _assign(msg, field, view):
            raise AttributeError(f"Failed to assign buffer field {field!r}")
        self.publish(msg)

    def publish_buffers(self, buffers: dict[str, object], *, msg=None) -> None:
        """Publish after assigning multiple bytes-like fields via memoryview."""
        if msg is None:
            msg = self.create_message()
        for field, buffer in buffers.items():
            view = memoryview(buffer)
            if not _assign(msg, field, view):
                raise AttributeError(f"Failed to assign buffer field {field!r}")
        self.publish(msg)

    def create_message(self):
        if self._msg_ctor is None:
            raise RuntimeError("Message constructor is not available")
        return self._msg_ctor()

    def _begin_writer_use(self) -> None:
        with self._state_lock:
            if self._destroyed or self._writer is None:
                raise RuntimeError("Cannot publish with a destroyed Publisher")
            self._active_writes += 1

    def _end_writer_use(self) -> None:
        with self._state_lock:
            self._active_writes -= 1
            if self._active_writes == 0:
                self._no_active_writes.notify_all()

    def _register_loan(self) -> None:
        with self._state_lock:
            if self._destroyed:
                raise RuntimeError("Cannot loan message from a destroyed Publisher")
            self._active_loans += 1

    def _release_loan(self) -> None:
        with self._state_lock:
            if self._active_loans > 0:
                self._active_loans -= 1
            if self._active_writes == 0 and self._active_loans == 0:
                self._no_active_writes.notify_all()

    def _record_zero_copy_fallback(self, exc: BaseException) -> None:
        self._zero_copy_fallback_count += 1
        self._last_zero_copy_fallback_reason = f"{type(exc).__name__}: {exc}"
        if os.environ.get("LWRCLPY_LOG_ZERO_COPY_FALLBACK") == "1":
            _logger.debug("Falling back to regular publish path: %s", self._last_zero_copy_fallback_reason)

    def publish_cuda(
        self,
        msg,
        cuda_array,
        *,
        field: str = "data",
        publish_ros_payload: bool = True,
        nbytes: int | None = None,
        device_id: int | None = None,
    ) -> bool:
        """Publish a ROS-compatible message with an optional CUDA IPC side channel.

        The normal DDS payload is still published by default, preserving ROS 2
        interoperability.  When ``cuda_array`` exposes ``__cuda_array_interface__``
        and CUDA IPC export succeeds, lwrclpy subscribers on the same host can
        open the device allocation from metadata on a hidden topic.

        Returns True when CUDA IPC metadata was published.  If CUDA IPC is not
        available, the method falls back to the normal ROS-compatible publish and
        returns False.
        """

        metadata = None
        try:
            from .cuda_ipc import export_cuda_ipc_metadata
            with self._cuda_ipc_lock:
                self._cuda_ipc_sequence += 1
                sequence_number = self._cuda_ipc_sequence
            metadata = export_cuda_ipc_metadata(
                cuda_array,
                topic=self._cuda_ipc_topic_name,
                field=field,
                nbytes=nbytes,
                device_id=device_id,
                sequence_number=sequence_number,
            )
        except Exception as exc:
            self._record_zero_copy_fallback(exc)
            metadata = None

        if metadata is not None and self._cuda_ipc_metadata_pub is not None:
            try:
                from .cuda_ipc import set_string_data
                meta_msg = self._cuda_ipc_metadata_pub._msg_ctor()
                set_string_data(meta_msg, metadata.to_json())
                self._cuda_ipc_metadata_pub.publish(meta_msg)
                with self._cuda_ipc_lock:
                    self._cuda_ipc_keepalive[metadata.token] = cuda_array
                    if len(self._cuda_ipc_keepalive) > self._cuda_ipc_keepalive_limit:
                        oldest = next(iter(self._cuda_ipc_keepalive))
                        self._cuda_ipc_keepalive.pop(oldest, None)
            except Exception as exc:
                self._record_zero_copy_fallback(exc)
                metadata = None

        target_ctor = self._msg_ctor if self._msg_ctor is not None else msg.__class__
        self._begin_writer_use()
        try:
            if metadata is not None and not publish_ros_payload:
                msg = self._make_shared_memory_signal_message(msg, target_ctor, field)
            self._publish_regular_message(msg, target_ctor)
        finally:
            self._end_writer_use()
        return metadata is not None

    def publish_shared_memory(
        self,
        msg,
        payload,
        *,
        field: str = "data",
        publish_ros_payload: bool = True,
    ) -> bool:
        """Publish a message with a CPU shared-memory side channel.

        ``payload`` is copied into a POSIX shared-memory block and small
        metadata is published on a hidden topic.  lwrclpy subscribers on the
        same host can call ``get_shared_memory_buffer(msg, field)`` to open the
        shared memory instead of reading the ROS payload field.
        """

        target_ctor = self._msg_ctor if self._msg_ctor is not None else msg.__class__
        allocation = self._publish_shared_memory_metadata(payload, field=field)
        should_publish = allocation is not None or publish_ros_payload
        if should_publish:
            self._begin_writer_use()
            try:
                if allocation is not None and not publish_ros_payload:
                    msg = self._make_shared_memory_signal_message(msg, target_ctor, field)
                self._publish_regular_message(msg, target_ctor)
            finally:
                self._end_writer_use()
        return allocation is not None

    def _publish_shared_memory_metadata(self, payload, *, field: str = "data"):
        allocation = None
        try:
            from .shared_memory import export_shared_memory_metadata
            with self._shm_lock:
                self._shm_sequence += 1
                sequence_number = self._shm_sequence
            allocation = export_shared_memory_metadata(
                payload,
                topic=self._shm_topic_name,
                field=field,
                sequence_number=sequence_number,
            )
        except Exception:
            allocation = None

        if allocation is not None and self._shm_metadata_pub is None:
            try:
                allocation.close()
            except Exception:
                pass
            allocation = None

        if allocation is not None:
            try:
                from .shared_memory import set_string_data, write_latest_metadata
                try:
                    write_latest_metadata(allocation.metadata)
                except Exception:
                    pass
                meta_msg = self._shm_metadata_pub._msg_ctor()
                set_string_data(meta_msg, allocation.metadata.to_json())
                self._shm_metadata_pub.publish(meta_msg)
                with self._shm_lock:
                    self._shm_keepalive[allocation.metadata.token] = allocation
                    while len(self._shm_keepalive) > self._shm_keepalive_limit:
                        oldest_token = next(iter(self._shm_keepalive))
                        oldest = self._shm_keepalive.pop(oldest_token)
                        oldest.close()
            except Exception:
                try:
                    allocation.close()
                except Exception:
                    pass
                allocation = None
        return allocation

    @property
    def _automatic_loaned_publish_enabled(self) -> bool:
        return self._data_sharing_enabled and self._is_fixed_size_type and self._can_loan_messages

    @property
    def _can_loan_messages(self) -> bool:
        """Return whether this publisher can use the true loaned write path."""
        with self._state_lock:
            writer = self._writer
        return (
            writer is not None
            and hasattr(writer, "lwrclpy_loan_sample_addr")
            and hasattr(writer, "lwrclpy_write_addr")
            and self._loan_from_addr is not None
        )

    @property
    def _loan_from_addr(self):
        if self._msg_ctor is None:
            return None
        module = self._msg_module
        if module is None:
            module = __import__(self._msg_ctor.__module__, fromlist=[self._msg_ctor.__name__])
        return getattr(module, f"lwrclpy_{self._msg_ctor.__name__}_from_addr", None)

    @property
    def performance_stats(self) -> dict[str, object]:
        elapsed = max(1e-9, time.monotonic() - self._stats_started_at)
        fallback_ratio = (
            self._zero_copy_fallback_count / max(1, self._publish_count + self._zero_copy_fallback_count)
        )
        return {
            "publish_count": self._publish_count,
            "publish_rate_hz": self._publish_count / elapsed,
            "data_sharing_enabled": self._data_sharing_enabled,
            "can_loan_messages": self._can_loan_messages,
            "automatic_loaned_publish_enabled": self._automatic_loaned_publish_enabled,
            "auto_loan_publish_count": self._auto_loan_publish_count,
            "zero_copy_fallback_count": self._zero_copy_fallback_count,
            "zero_copy_fallback_ratio": fallback_ratio,
            "last_zero_copy_fallback_reason": self._last_zero_copy_fallback_reason,
        }

    def reset_performance_stats(self) -> None:
        self._publish_count = 0
        self._auto_loan_publish_count = 0
        self._zero_copy_fallback_count = 0
        self._last_zero_copy_fallback_reason = ""
        self._stats_started_at = time.monotonic()

    def _loan_message(self, *, require_zero_copy: bool = False) -> _LoanedMessage:
        if self._msg_ctor is None:
            raise RuntimeError("Cannot loan message: message constructor not available")
        if require_zero_copy and not self._can_loan_messages:
            raise RuntimeError("Cannot loan message: middleware loaned write path is not available")

        loaned_msg = None
        from_middleware = False
        loaned_addr = 0
        try:
            from_addr = self._loan_from_addr
            if from_addr is not None and hasattr(self._writer, "lwrclpy_loan_sample_addr"):
                loaned_addr = int(self._writer.lwrclpy_loan_sample_addr())
                if loaned_addr:
                    loaned_msg = from_addr(loaned_addr)
                    from_middleware = True
            elif hasattr(self._writer, "loan_sample"):
                try:
                    loaned_msg = self._writer.loan_sample()
                    from_middleware = loaned_msg is not None
                except TypeError:
                    candidate = self._msg_ctor()
                    rc = self._writer.loan_sample(candidate)
                    if _retcode_is_ok(rc, none_is_ok=True):
                        loaned_msg = candidate
                        from_middleware = True
        except Exception:
            pass

        if require_zero_copy and not from_middleware:
            raise RuntimeError("Cannot loan message: middleware loan_sample() did not return a loaned sample")

        if loaned_msg is None:
            loaned_msg = self._msg_ctor()

        return _LoanedMessage(self, loaned_msg, from_middleware, addr=loaned_addr)

    def _publish_loaned(self, loaned: _LoanedMessage) -> None:
        msg = loaned._msg
        _materialize_shadow_attributes(msg)
        if self._writer is None:
            raise RuntimeError("Cannot publish with a destroyed Publisher")
        if loaned._from_middleware and loaned._addr and hasattr(self._writer, "lwrclpy_write_addr"):
            if not self._writer.lwrclpy_write_addr(loaned._addr):
                raise RuntimeError("Failed to write middleware-loaned sample")
        elif loaned._from_middleware and hasattr(self._writer, "write_loaned"):
            rc = self._writer.write_loaned(msg)
            if not _retcode_is_ok(rc, none_is_ok=True):
                raise RuntimeError(f"Fast DDS DataWriter.write_loaned failed: retcode={rc!r}")
        else:
            _write_checked(self._writer, msg)
        loaned._published = True
        loaned.release()
        self._publish_count += 1

    def get_subscription_count(self) -> int:
        """Return the number of subscriptions matched to this publisher."""
        try:
            self._begin_writer_use()
        except RuntimeError:
            return 0
        try:
            status_method = getattr(self._writer, "get_publication_matched_status", None)
            if status_method is not None:
                count = _matched_status_count(status_method, getattr(fastdds, "PublicationMatchedStatus", None))
                if count is not None:
                    return count
            handles_method = getattr(self._writer, "get_matched_subscriptions", None)
            if handles_method is not None:
                count = _matched_handle_count(handles_method, getattr(fastdds, "InstanceHandleVector", None))
                if count is not None:
                    return count
            return 0
        finally:
            self._end_writer_use()

    def assert_liveliness(self) -> bool:
        """Manually assert liveliness (for MANUAL_BY_TOPIC liveliness policy)."""
        try:
            self._begin_writer_use()
        except RuntimeError:
            return False
        try:
            if hasattr(self._writer, "assert_liveliness"):
                self._writer.assert_liveliness()
                return True
        except Exception:
            pass
        finally:
            self._end_writer_use()
        return False

    def wait_for_all_acked(self, timeout: Duration | float | int | None = None) -> bool:
        """Block until all samples are acknowledged or timeout occurs."""
        try:
            self._begin_writer_use()
        except RuntimeError:
            return False
        duration = fastdds.Duration_t()
        if timeout is None:
            set_fastdds_duration(
                duration,
                getattr(fastdds, "DURATION_INFINITE_SEC", 0x7fffffff),
                getattr(fastdds, "DURATION_INFINITE_NSEC", 0xffffffff),
            )
        else:
            if isinstance(timeout, Duration):
                total_ns = timeout.nanoseconds
            else:
                total_ns = int(float(timeout) * 1_000_000_000)
            if total_ns < 0:
                total_ns = 0
            set_fastdds_duration(duration, total_ns // 1_000_000_000, total_ns % 1_000_000_000)
        try:
            rc = self._writer.wait_for_acknowledgments(duration)
            return _retcode_is_ok(rc, none_is_ok=True)
        except Exception:
            return False
        finally:
            self._end_writer_use()

    def destroy(self) -> None:
        """Destroy the Fast DDS DataWriter and Publisher owned by this object."""
        with self._state_lock:
            if self._destroyed and self._writer is None and self._publisher is None:
                return
            self._destroyed = True
            deadline = time.monotonic() + max(0.0, self._destroy_loan_timeout)
            while self._active_writes > 0 or self._active_loans > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._no_active_writes.wait(timeout=remaining)
            timed_out = self._active_writes > 0 or self._active_loans > 0
            if timed_out:
                _logger.warning(
                    "Publisher.destroy timed out waiting for active writes/loans "
                    "(writes=%d loans=%d); skipping DDS entity deletion",
                    self._active_writes,
                    self._active_loans,
                )
                writer = None
                publisher = None
            else:
                writer = self._writer
                publisher = self._publisher
                self._writer = None
                self._publisher = None
        with self._shm_lock:
            allocations = list(self._shm_keepalive.values())
            self._shm_keepalive.clear()
        for allocation in allocations:
            try:
                allocation.close()
            except Exception:
                pass
        if writer is not None:
            try:
                _wait_writer_acked(writer, _DESTROY_ACK_TIMEOUT)
                delete_writer = getattr(publisher, "delete_datawriter", None) if publisher is not None else None
                if callable(delete_writer):
                    delete_writer(writer)
            except Exception:
                pass
        if publisher is not None:
            try:
                delete_publisher = getattr(self._participant, "delete_publisher", None)
                if callable(delete_publisher):
                    delete_publisher(publisher)
            except Exception:
                pass
