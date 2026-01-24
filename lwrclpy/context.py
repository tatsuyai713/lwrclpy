import threading
import os
import atexit
import weakref
from typing import List, Optional, Any

try:
    import fastdds  # type: ignore
except Exception:
    fastdds = None

__all__ = ["init", "shutdown", "ok", "is_shutdown", "get_participant", "try_shutdown", "Context", "get_domain_id"]

_lock = threading.RLock()
_initialized = False
_shutdown_flag = False
_participant = None
_tracked_entities: List[weakref.ref] = []  # Track all entities for proper cleanup order
_domain_env = os.environ.get("LWRCL_DOMAIN_ID")
# ROS 2 互換：ROS_DOMAIN_ID をフォールバックに使う
if _domain_env is None:
    _domain_env = os.environ.get("ROS_DOMAIN_ID")
try:
    _domain = int(_domain_env) if _domain_env is not None else 0
except ValueError:
    _domain = 0


def init(args=None, *, domain_id: Optional[int] = None):
    """Initialize lwrclpy context.
    
    Args:
        args: Command line arguments (ignored, for compatibility)
        domain_id: Optional domain ID override
    """
    global _initialized, _shutdown_flag, _participant, _domain
    with _lock:
        if _initialized:
            return
        if fastdds is None:
            raise RuntimeError(
                "fastdds Python bindings not found. Build Fast-DDS-python and source its setup.bash.")
        
        if domain_id is not None:
            _domain = domain_id
            
        factory = fastdds.DomainParticipantFactory.get_instance()
        pq = fastdds.DomainParticipantQos()
        factory.get_default_participant_qos(pq)
        _participant = factory.create_participant(_domain, pq)
        if _participant is None:
            raise RuntimeError("Failed to create DomainParticipant")
        _initialized = True
        _shutdown_flag = False
        
        # Register atexit handler for graceful cleanup
        atexit.register(_atexit_shutdown)


def _atexit_shutdown():
    """Atexit handler for graceful shutdown."""
    try:
        shutdown(force_exit=False)
    except Exception:
        pass


def shutdown(*, force_exit: bool = False):
    """Shutdown the context.
    
    Args:
        force_exit: If True, use os._exit(0) to bypass Python cleanup and avoid
                   Fast DDS v3 "double free" errors. Default is False for compatibility.
    """
    global _initialized, _shutdown_flag, _participant, _tracked_entities
    with _lock:
        if not _initialized or _shutdown_flag:
            return
        
        # Mark as shutting down first to prevent new operations
        _shutdown_flag = True
        
        # Destroy tracked entities in reverse order (LIFO)
        # Use weak references to handle already-deleted entities
        entities_to_destroy = []
        for entity_ref in reversed(_tracked_entities):
            entity = entity_ref()
            if entity is not None:
                entities_to_destroy.append(entity)
        
        for entity in entities_to_destroy:
            try:
                if hasattr(entity, 'destroy'):
                    entity.destroy()
            except Exception:
                pass
        
        _tracked_entities.clear()
        
        # Don't delete participant - let Fast DDS clean it up on process exit
        # Attempting to delete can cause "double free" errors
        _participant = None
        _initialized = False
    
    # If force_exit is requested, use os._exit to bypass Python cleanup
    # This avoids "double free or corruption (fasttop)" errors in Fast DDS v3
    if force_exit:
        os._exit(0)


def try_shutdown():
    """Attempt to shutdown without force_exit. Safe to call multiple times."""
    try:
        shutdown(force_exit=False)
    except Exception:
        pass


def ok() -> bool:
    """Return True if context is initialized and not shutting down."""
    with _lock:
        return _initialized and not _shutdown_flag


def is_shutdown() -> bool:
    """Return True if context is shutting down or has shutdown."""
    with _lock:
        return _shutdown_flag


def get_participant():
    """Get the DomainParticipant. Raises RuntimeError if not initialized."""
    with _lock:
        if not _initialized:
            raise RuntimeError("lwrclpy.init() must be called first")
        return _participant


def get_domain_id() -> int:
    """Return the current domain ID."""
    return _domain


def track_entity(entity: Any):
    """Track an entity for proper cleanup order during shutdown.
    
    Uses weak references to avoid preventing garbage collection.
    """
    with _lock:
        # Use weak reference to avoid preventing garbage collection
        ref = weakref.ref(entity)
        _tracked_entities.append(ref)


def untrack_entity(entity: Any):
    """Remove an entity from tracking (when manually destroyed)."""
    with _lock:
        # Remove any weak references to this entity
        _tracked_entities[:] = [
            ref for ref in _tracked_entities 
            if ref() is not None and ref() is not entity
        ]


class Context:
    """ROS 2 compatible Context class for managing DDS lifecycle.
    
    This provides a class-based interface similar to rclpy.Context.
    Multiple contexts can be created with different domain IDs for
    isolated communication.
    """
    
    def __init__(self):
        self._initialized = False
        self._shutdown_flag = False
        self._participant = None
        self._domain_id = 0
        self._lock = threading.RLock()
    
    def init(self, args=None, *, domain_id: Optional[int] = None):
        """Initialize this context.
        
        Args:
            args: Command line arguments (ignored, for compatibility)
            domain_id: Optional domain ID for this context
        """
        with self._lock:
            if self._initialized:
                return
            
            if fastdds is None:
                raise RuntimeError(
                    "fastdds Python bindings not found.")
            
            if domain_id is not None:
                self._domain_id = domain_id
            else:
                # Use environment variable or default
                env_domain = os.environ.get("ROS_DOMAIN_ID", os.environ.get("LWRCL_DOMAIN_ID", "0"))
                try:
                    self._domain_id = int(env_domain)
                except ValueError:
                    self._domain_id = 0
            
            factory = fastdds.DomainParticipantFactory.get_instance()
            pq = fastdds.DomainParticipantQos()
            factory.get_default_participant_qos(pq)
            self._participant = factory.create_participant(self._domain_id, pq)
            
            if self._participant is None:
                raise RuntimeError("Failed to create DomainParticipant")
            
            self._initialized = True
            self._shutdown_flag = False
    
    def shutdown(self):
        """Shutdown this context."""
        with self._lock:
            if not self._initialized or self._shutdown_flag:
                return
            
            self._shutdown_flag = True
            self._participant = None
            self._initialized = False
    
    def try_shutdown(self) -> bool:
        """Attempt to shutdown. Returns True if shutdown happened, False if already shut down."""
        with self._lock:
            if not self._initialized or self._shutdown_flag:
                return False
            self.shutdown()
            return True
    
    def ok(self) -> bool:
        """Return True if context is initialized and not shutting down."""
        with self._lock:
            return self._initialized and not self._shutdown_flag
    
    def get_domain_id(self) -> int:
        """Return the domain ID for this context."""
        return self._domain_id
    
    def get_participant(self):
        """Get the DomainParticipant for this context."""
        with self._lock:
            if not self._initialized:
                raise RuntimeError("Context not initialized")
            return self._participant
