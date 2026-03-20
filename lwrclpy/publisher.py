# lwrclpy/publisher.py
# Zero-copy–friendly DataWriter wrapper for Fast DDS v3.
# - Prefer DDS internal zero-copy (DataSharing) where available.
# - Keep compatibility with QoSProfile mapping.
# - Support loan_message() for true zero-copy publishing.

from __future__ import annotations
from contextlib import contextmanager
import fastdds  # type: ignore
import os
from typing import Optional, TypeVar, Generic, TYPE_CHECKING
from .qos import QoSProfile
from .message_utils import clone_message, _ValueProxy
from .duration import Duration

if TYPE_CHECKING:
    from typing import Type

T = TypeVar('T')


def _has_proxy_attributes(msg) -> bool:
    """Check if any instance __dict__ entries are _ValueProxy objects.

    If the user received a message via subscription (which wraps fields in
    _ValueProxy) and re-publishes it, we need to clone to unwrap.
    If the user created a fresh message and set fields directly, no proxy exists.
    """
    inst_dict = getattr(msg, "__dict__", None)
    if not inst_dict:
        return False
    return any(isinstance(v, _ValueProxy) for v in inst_dict.values())


def _force_data_sharing_on_writer(wq: "fastdds.DataWriterQos") -> None:
    """Prefer/force data sharing on the writer QoS when the API exists."""
    if os.environ.get("LWRCLPY_NO_DATASHARING") == "1":
        return
    try:
        if hasattr(wq, "data_sharing"):
            ds = wq.data_sharing()
            # Prefer explicit ON (or automatic when ON is unavailable).
            if hasattr(ds, "on"):
                ds.on()
            elif hasattr(ds, "automatic"):
                ds.automatic()
    except Exception:
        # Ignore when API is absent
        pass


class LoanedMessage(Generic[T]):
    """Context manager for loaned messages enabling zero-copy publishing.
    
    Usage:
        with publisher.loan_message() as msg:
            msg.data = "Hello"
        # Message is automatically published when exiting the context
    """
    
    __slots__ = ("_publisher", "_msg", "_published")
    
    def __init__(self, publisher: "Publisher", msg: T):
        self._publisher = publisher
        self._msg = msg
        self._published = False
    
    @property
    def msg(self) -> T:
        """Access the loaned message."""
        return self._msg
    
    def __enter__(self) -> T:
        return self._msg
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._published and exc_type is None:
            self._publisher._publish_loaned(self._msg)
            self._published = True
        return False


class Publisher:
    """Publisher managing Publisher/DataWriter with zero-copy friendly QoS."""

    def __init__(self, participant, topic, qos: QoSProfile, msg_ctor=None):
        self._participant = participant
        self._topic = topic
        self._msg_ctor = msg_ctor
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

        # >>> Zero-copy–friendly hint: prefer DataSharing if the API exists
        _force_data_sharing_on_writer(wq)
        # <<<

        # Create DataWriter
        self._writer = self._publisher.create_datawriter(self._topic, wq)
        if self._writer is None:
            raise RuntimeError("Failed to create DataWriter")

    def publish(self, msg) -> None:
        """Publish a message instance generated from the SWIG type."""
        target_ctor = self._msg_ctor if self._msg_ctor is not None else msg.__class__

        # Fast path: if msg is already the correct SWIG type and has no
        # _ValueProxy-wrapped attributes, skip the full clone_message.
        if isinstance(msg, target_ctor) and not _has_proxy_attributes(msg):
            self._writer.write(msg)
        else:
            try:
                to_send = clone_message(msg, target_ctor)
            except Exception:
                to_send = msg  # fall back to original on failure
            self._writer.write(to_send)
        self._publish_count += 1

    def loan_message(self) -> LoanedMessage:
        """Loan a message from the middleware for zero-copy publishing.
        
        Returns a LoanedMessage context manager. The message is published
        automatically when exiting the context (unless an exception occurred).
        
        Note: Fast DDS loan support depends on the data type and QoS settings.
        If loaning fails, a regular message instance is created instead.
        """
        if self._msg_ctor is None:
            raise RuntimeError("Cannot loan message: message constructor not available")
        
        # Try to use Fast DDS loan API if available
        loaned_msg = None
        try:
            if hasattr(self._writer, "loan_sample"):
                loaned_msg = self._writer.loan_sample()
        except Exception:
            pass
        
        # Fall back to creating a regular message if loaning not supported
        if loaned_msg is None:
            loaned_msg = self._msg_ctor()
        
        return LoanedMessage(self, loaned_msg)

    def _publish_loaned(self, msg) -> None:
        """Publish a loaned message. Called by LoanedMessage context manager."""
        try:
            # Try to use discard_loan if available (for true loaned messages)
            if hasattr(self._writer, "write_loaned"):
                self._writer.write_loaned(msg)
            else:
                self._writer.write(msg)
        except Exception:
            # Fallback to regular write
            self._writer.write(msg)
        self._publish_count += 1

    def get_subscription_count(self) -> int:
        """Return the number of subscriptions matched to this publisher."""
        try:
            if hasattr(self._writer, "get_matched_subscriptions"):
                matches = self._writer.get_matched_subscriptions()
                return len(matches) if hasattr(matches, "__len__") else 0
            # Alternative API
            if hasattr(self._writer, "get_publication_matched_status"):
                status = self._writer.get_publication_matched_status()
                return getattr(status, "current_count", 0)
        except Exception:
            pass
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
