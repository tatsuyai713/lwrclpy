import logging
import threading

from ._callback_queue import CallbackQueue
from .publisher import Publisher
from .subscription import Subscription
from .qos import QoSProfile
from .typesupport import RegisteredType
from .utils import resolve_service_type, service_topics
from .utils import get_or_create_topic
from .context import get_participant, track_entity, untrack_entity


_logger = logging.getLogger(__name__)


class Service:
    """Best-effort rclpy-like Service (one callback per request)."""

    def __init__(self, service_type, service_name: str, callback, qos_profile: QoSProfile, topic_prefix: str = "", *, enqueue_cb=None):
        self._participant = get_participant()
        self._service_name = service_name
        self._callback = callback
        self._prefix = topic_prefix
        self._callback_queue = None if enqueue_cb is not None else CallbackQueue()
        self._enqueue_cb = enqueue_cb or self._callback_queue.enqueue
        self._destroyed = False
        self._lock = threading.Lock()

        req_cls, res_cls, _req_pubsub, _res_pubsub = resolve_service_type(service_type)
        self._request_cls = req_cls
        self._response_cls = res_cls

        # Register types
        self._req_type_name = RegisteredType(req_cls).register()
        self._res_type_name = RegisteredType(res_cls).register()

        req_topic, res_topic = service_topics(service_name, topic_prefix)

        self._response_pub = Publisher(
            self._participant,
            self._make_topic(res_topic, self._res_type_name),
            qos_profile,
            msg_ctor=self._response_cls,
        )

        def _on_request(msg):
            with self._lock:
                if self._destroyed:
                    return
            response = self._response_cls()
            try:
                ret = self._callback(msg, response)
                if ret is not None:
                    response = ret
            except Exception:
                _logger.exception("Service callback failed for %s", self._service_name)
            with self._lock:
                if self._destroyed:
                    return
                publisher = self._response_pub
            if publisher is None:
                return
            try:
                publisher.publish(response)
            except Exception:
                _logger.debug(
                    "Service response publish skipped for %s during shutdown",
                    self._service_name,
                    exc_info=True,
                )

        self._request_sub = Subscription(
            self._participant,
            self._make_topic(req_topic, self._req_type_name),
            qos_profile,
            _on_request,
            self._request_cls,
            enqueue_cb=self._enqueue_cb,
        )
        
        # Track for proper cleanup
        track_entity(self)

    def _make_topic(self, name: str, type_name: str):
        topic_obj, _ = get_or_create_topic(self._participant, name, type_name)
        return topic_obj

    def destroy(self):
        """Clean up service resources in the correct order."""
        with self._lock:
            if self._destroyed:
                return
            self._destroyed = True

        # Untrack from global cleanup
        untrack_entity(self)
        
        # Destroy subscription first (stop receiving requests)
        if hasattr(self, '_request_sub') and self._request_sub:
            try:
                self._request_sub.destroy()
            except Exception:
                pass
            self._request_sub = None
        
        # Then destroy publisher
        if hasattr(self, '_response_pub') and self._response_pub:
            try:
                self._response_pub.destroy()
            except Exception:
                pass
            self._response_pub = None

        if self._callback_queue is not None:
            self._callback_queue.close()
            self._callback_queue = None

