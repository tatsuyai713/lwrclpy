# lwrclpy/publisher.py
# Zero-copy–friendly DataWriter wrapper for Fast DDS v3.
# - Prefer DDS internal zero-copy (DataSharing) where available.
# - Keep compatibility with QoSProfile mapping.
# - Expose loan_message() as a lwrclpy extension; portable rclpy code should use publish(msg).

from __future__ import annotations
import fastdds  # type: ignore
import os
from typing import TypeVar, Generic
from .qos import QoSProfile
from .message_utils import clone_message, _assign
from .duration import Duration
from .utils import (
    _matched_handle_count,
    _matched_status_count,
    _pubsub_type_supports_data_sharing,
    _retcode_is_ok,
)

T = TypeVar('T')


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


def _force_data_sharing_on_writer(wq: "fastdds.DataWriterQos") -> bool:
    """Prefer/force data sharing on the writer QoS when the API exists."""
    if os.environ.get("LWRCLPY_NO_DATASHARING") == "1":
        return False
    try:
        if hasattr(wq, "data_sharing"):
            ds = wq.data_sharing()
            shared_dir = os.environ.get("LWRCLPY_DATASHARING_DIR", "")
            if hasattr(ds, "on"):
                try:
                    if shared_dir:
                        ds.on(shared_dir)
                    else:
                        ds.on()
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


class LoanedMessage(Generic[T]):
    """Message-like wrapper for a DataWriter loaned sample.

    The wrapper forwards field access to the underlying message, so callers can
    use it like a normal message and pass it to ``publish()``.  It also supports
    the existing context-manager examples, publishing on successful exit.
    """

    __slots__ = ("_publisher", "_msg", "_from_middleware", "_published", "_addr")

    def __init__(self, publisher: "Publisher", msg: T, from_middleware: bool, addr: int = 0):
        object.__setattr__(self, "_publisher", publisher)
        object.__setattr__(self, "_msg", msg)
        object.__setattr__(self, "_from_middleware", from_middleware)
        object.__setattr__(self, "_published", False)
        object.__setattr__(self, "_addr", int(addr or 0))

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
            self._publisher.publish(self)
        return False


class Publisher:
    """Publisher managing Publisher/DataWriter with zero-copy friendly QoS."""

    def __init__(self, participant, topic, qos: QoSProfile, msg_ctor=None, msg_module=None, pubsub_cls=None):
        self._participant = participant
        self._topic = topic
        self._msg_ctor = msg_ctor
        self._msg_module = msg_module
        self._destroyed = False
        self._publish_count = 0

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

        # Create DataWriter
        self._writer = self._publisher.create_datawriter(self._topic, wq)
        if self._writer is None and self._data_sharing_enabled:
            _disable_data_sharing_on_writer(wq)
            self._data_sharing_enabled = False
            self._writer = self._publisher.create_datawriter(self._topic, wq)
        if self._writer is None:
            raise RuntimeError("Failed to create DataWriter")

    def publish(self, msg) -> None:
        """Publish a message instance generated from the SWIG type."""
        if isinstance(msg, LoanedMessage):
            if msg._publisher is not self:
                raise ValueError(
                    "Cannot publish a LoanedMessage created by a different "
                    "publisher; publish loaned messages only with their "
                    "originating publisher."
                )
            if msg._published:
                raise ValueError(
                    "Cannot publish the same LoanedMessage more than once; "
                    "obtain a new loaned message or publish a normal message "
                    "instance instead."
                )
            self._publish_loaned(msg)
            return

        target_ctor = self._msg_ctor if self._msg_ctor is not None else msg.__class__

        # Fast path: if msg is already the correct SWIG type, apply any
        # rclpy-style shadow attributes in-place and write the same instance.
        if isinstance(msg, target_ctor):
            _materialize_shadow_attributes(msg)
            self._writer.write(msg)
        else:
            try:
                to_send = clone_message(msg, target_ctor)
            except Exception:
                to_send = msg  # fall back to original on failure
            self._writer.write(to_send)
        self._publish_count += 1

    @property
    def data_sharing_enabled(self) -> bool:
        """Return whether Fast DDS DataSharing was explicitly enabled."""
        return self._data_sharing_enabled

    @property
    def zero_copy_enabled(self) -> bool:
        """Return whether lwrclpy enabled its zero-copy transport path."""
        return self._data_sharing_enabled

    @property
    def can_loan_messages(self) -> bool:
        """Return whether this publisher can use the true loaned write path."""
        return (
            hasattr(self._writer, "lwrclpy_loan_sample_addr")
            and hasattr(self._writer, "lwrclpy_write_addr")
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

    def loan_message(self, *, require_zero_copy: bool = False) -> LoanedMessage:
        """Borrow a message for efficient publishing.

        Returns a message-like object that can be passed to ``publish()``.  When
        Fast DDS exposes sample loaning for this type, publish uses the loaned
        write path.  Otherwise the object falls back to a normal message while
        preserving the same public API.  Set ``require_zero_copy=True`` to fail
        instead of falling back when the middleware loan path is unavailable.
        """
        if self._msg_ctor is None:
            raise RuntimeError("Cannot loan message: message constructor not available")
        if require_zero_copy and not self.can_loan_messages:
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

        return LoanedMessage(self, loaned_msg, from_middleware, addr=loaned_addr)

    def _publish_loaned(self, loaned: LoanedMessage) -> None:
        """Publish a loaned message through the appropriate writer path.

        Used by ``Publisher.publish()`` for explicit loaned publishing and by
        the ``LoanedMessage`` context manager on successful exit.
        """
        msg = loaned._msg
        _materialize_shadow_attributes(msg)
        if loaned._from_middleware and loaned._addr and hasattr(self._writer, "lwrclpy_write_addr"):
            if not self._writer.lwrclpy_write_addr(loaned._addr):
                raise RuntimeError("Failed to write middleware-loaned sample")
        elif loaned._from_middleware and hasattr(self._writer, "write_loaned"):
            self._writer.write_loaned(msg)
        else:
            self._writer.write(msg)
        loaned._published = True
        self._publish_count += 1

    def get_subscription_count(self) -> int:
        """Return the number of subscriptions matched to this publisher."""
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

    def assert_liveliness(self) -> bool:
        """Manually assert liveliness (for MANUAL_BY_TOPIC liveliness policy)."""
        try:
            if hasattr(self._writer, "assert_liveliness"):
                self._writer.assert_liveliness()
                return True
        except Exception:
            pass
        return False

    def wait_for_all_acked(self, timeout: Duration | float | int | None = None) -> bool:
        """Block until all samples are acknowledged or timeout occurs."""
        duration = fastdds.Duration_t()
        if timeout is None:
            duration.seconds = getattr(fastdds, "DURATION_INFINITE_SEC", 0x7fffffff)
            duration.nanosec = getattr(fastdds, "DURATION_INFINITE_NSEC", 0x7fffffff)
        else:
            if isinstance(timeout, Duration):
                total_ns = timeout.nanoseconds
            else:
                total_ns = int(float(timeout) * 1_000_000_000)
            if total_ns < 0:
                total_ns = 0
            duration.seconds = total_ns // 1_000_000_000
            duration.nanosec = total_ns % 1_000_000_000
        try:
            rc = self._writer.wait_for_acknowledgments(duration)
            return bool(rc) if isinstance(rc, bool) else True
        except Exception:
            return False

    def destroy(self) -> None:
        """Mark as destroyed. Fast DDS will clean up resources automatically."""
        if self._destroyed:
            return
        self._destroyed = True
        
        # Don't explicitly delete Fast DDS entities - let Fast DDS handle cleanup
        # Attempting to delete them causes "double free" errors
        # Fast DDS will automatically clean up when the participant is destroyed
        self._writer = None
        self._publisher = None
