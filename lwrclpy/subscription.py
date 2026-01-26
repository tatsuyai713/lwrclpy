# lwrclpy/subscription.py
# DDS DataReader wrapper that enqueues received samples for executor-driven callbacks.
# Implements copy according to fastddsgen-generated getter/setter conventions.
# Supports zero-copy with data sharing and raw data mode.

from __future__ import annotations
from typing import Optional, Callable, List, Tuple, Any
import fastdds  # type: ignore
import os
from .qos import QoSProfile
from .message_utils import clone_message


def _retcode_is_ok(rc) -> bool:
    """Return True if 'rc' represents RETCODE_OK (v2/v3 tolerant)."""
    ok_const = getattr(fastdds, "RETCODE_OK", 0)  # v3: module-level; v2: often 0-like
    try:
        if rc == ok_const:
            return True
    except Exception:
        pass
    try:
        return int(rc) == int(ok_const)
    except Exception:
        return bool(rc) is True


def _force_data_sharing_on_reader(rq: "fastdds.DataReaderQos") -> None:
    """Prefer/force data sharing on the reader QoS when the API exists."""
    if os.environ.get("LWRCLPY_NO_DATASHARING") == "1":
        return
    try:
        if hasattr(rq, "data_sharing"):
            ds = rq.data_sharing()
            # Prefer explicit ON for internal zero-copy; fallback to automatic.
            if hasattr(ds, "on"):
                ds.on()  # Force data-sharing if supported
            elif hasattr(ds, "automatic"):
                ds.automatic()
    except Exception:
        # Silently ignore if this build doesn't expose the API
        pass


class MessageInfo:
    """Information about a received message (similar to rclpy.MessageInfo)."""
    __slots__ = ("source_timestamp", "received_timestamp", "publication_sequence_number", 
                 "reception_sequence_number", "publisher_gid", "from_intra_process")
    
    def __init__(self, sample_info=None):
        self.source_timestamp = 0
        self.received_timestamp = 0
        self.publication_sequence_number = 0
        self.reception_sequence_number = 0
        self.publisher_gid = None
        self.from_intra_process = False
        
        if sample_info is not None:
            try:
                # Extract timestamp
                ts = getattr(sample_info, "source_timestamp", None)
                if ts is not None:
                    sec = getattr(ts, "seconds", 0)
                    nsec = getattr(ts, "nanosec", 0)
                    self.source_timestamp = sec * 1_000_000_000 + nsec
                
                # Extract sequence numbers if available
                if hasattr(sample_info, "publication_sequence_number"):
                    self.publication_sequence_number = sample_info.publication_sequence_number
                if hasattr(sample_info, "reception_sequence_number"):
                    self.reception_sequence_number = sample_info.reception_sequence_number
                    
                # Check for intra-process delivery
                if hasattr(sample_info, "from_intra_process"):
                    self.from_intra_process = sample_info.from_intra_process
            except Exception:
                pass


class _ReaderListener(fastdds.DataReaderListener):
    """Listener that enqueues callbacks to the executor queue."""

    def __init__(self, enqueue_cb, user_cb, msg_ctor, raw_mode: bool = False):
        super().__init__()
        self._enqueue_cb = enqueue_cb
        self._user_cb = user_cb
        self._msg_ctor = msg_ctor
        self._raw_mode = raw_mode

    def on_subscription_matched(self, reader, info):
        """Called when subscription matches/unmatches with a publisher."""
        pass
    
    def on_data_available(self, reader):
        info = fastdds.SampleInfo()
        data = self._msg_ctor()

        # Absorb ordering & signature differences.
        try:
            rc = reader.take_next_sample(data, info)
        except TypeError:
            rc = reader.take_next_sample(info, data)
        except Exception:
            return  # Avoid director double-fault

        if getattr(info, "valid_data", True) and _retcode_is_ok(rc):
            # Enqueue the callback to be run by the executor.
            # Prefer delivering the received instance directly to avoid extra copies.
            if not self._raw_mode:
                try:
                    from .message_utils import expose_callable_fields
                    expose_callable_fields(data)
                except Exception:
                    pass
            
            if isinstance(data, self._msg_ctor):
                self._enqueue_cb(self._user_cb, data)
            else:
                cloned = clone_message(data, self._msg_ctor)
                self._enqueue_cb(self._user_cb, cloned)


class Subscription:
    """Subscription managing Subscriber/DataReader with zero-copy friendly QoS.
    コールバックは DDS リスナーで受信し、Executor にキューイングする。"""

    def __init__(self, participant, topic, qos: QoSProfile, callback, msg_ctor, enqueue_cb, 
                 *, raw: bool = False, event_callbacks=None):
        self._participant = participant
        self._topic = topic
        self._callback = callback
        self._msg_ctor = msg_ctor
        self._destroyed = False
        self._raw_mode = raw
        self._event_callbacks = event_callbacks or {}
        self._message_count = 0

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

        # >>> Zero-copy–friendly hint: prefer DataSharing if the API exists
        _force_data_sharing_on_reader(rq)
        # <<<

        # Listener enqueue to executor queue
        self._listener = _ReaderListener(enqueue_cb, callback, msg_ctor, raw_mode=raw)

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

        if reader is None:
            raise RuntimeError("Failed to create DataReader")
        self._reader = reader

    def take(self, max_count: int = 1) -> List[Tuple[Any, MessageInfo]]:
        """Take messages directly from the reader (polling mode).
        
        Returns a list of (message, message_info) tuples.
        This is useful for manual polling without callbacks.
        """
        results = []
        for _ in range(max_count):
            info = fastdds.SampleInfo()
            data = self._msg_ctor()
            
            try:
                rc = self._reader.take_next_sample(data, info)
            except TypeError:
                rc = self._reader.take_next_sample(info, data)
            except Exception:
                break
            
            if not (_retcode_is_ok(rc) and getattr(info, "valid_data", True)):
                break
            
            if not self._raw_mode:
                try:
                    from .message_utils import expose_callable_fields
                    expose_callable_fields(data)
                except Exception:
                    pass
            
            msg_info = MessageInfo(info)
            results.append((data, msg_info))
            self._message_count += 1
        
        return results

    def take_one(self) -> Optional[Tuple[Any, MessageInfo]]:
        """Take a single message. Returns (message, info) or None."""
        results = self.take(1)
        return results[0] if results else None

    def get_publisher_count(self) -> int:
        """Return the number of publishers matched to this subscription."""
        try:
            if hasattr(self._reader, "get_matched_publications"):
                matches = self._reader.get_matched_publications()
                return len(matches) if hasattr(matches, "__len__") else 0
            # Alternative API
            if hasattr(self._reader, "get_subscription_matched_status"):
                status = self._reader.get_subscription_matched_status()
                return getattr(status, "current_count", 0)
        except Exception:
            pass
        return 0

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
