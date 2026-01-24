from __future__ import annotations

from lwrclpy import (
    Node,
    Rate,
    create_node as _create_node_impl,
    create_rate as _create_rate_impl,
    Parameter,
    ParameterType,
    SetParametersResult,
    shutdown as _core_shutdown,  # Use lwrclpy.shutdown (with force_exit)
    Future,
    Clock,
    ClockType,
    Time,
    Timer,
)
from lwrclpy.context import init as _core_init, ok as _core_ok, get_domain_id, Context


class _DefaultContext:
    """Wrapper for default context that provides rclpy-compatible interface."""
    
    def ok(self) -> bool:
        return _core_ok()
    
    def get_domain_id(self) -> int:
        return get_domain_id()


_default_context = _DefaultContext()

from .executors import (
    spin,
    spin_once,
    spin_some,
    spin_until_future_complete,
    SingleThreadedExecutor,
    MultiThreadedExecutor,
    Executor,
    ExternalShutdownException,
)
from .duration import Duration
from . import logging
from . import qos
from .callback_groups import CallbackGroup, MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup


class _InitContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        shutdown()
        return False


def init(*, args=None, context=None, domain_id=None):
    """Initialize rclpy.
    
    Args:
        args: Command line arguments (ignored)
        context: Context (ignored, for compatibility)
        domain_id: Optional domain ID override
    """
    del context  # compatibility placeholder
    _core_init(args=args, domain_id=domain_id)
    return _InitContext()


def shutdown():
    _core_shutdown()


def ok() -> bool:
    return _core_ok()


def create_node(name: str, **kwargs) -> Node:
    return _create_node_impl(name, **kwargs)


def create_rate(hz: float) -> Rate:
    return _create_rate_impl(hz)


def get_default_context():
    """Return the default context wrapper."""
    return _default_context


__all__ = [
    "Node",
    "Rate",
    "init",
    "shutdown",
    "ok",
    "spin",
    "spin_once",
    "spin_some",
    "spin_until_future_complete",
    "SingleThreadedExecutor",
    "MultiThreadedExecutor",
    "Executor",
    "ExternalShutdownException",
    "create_node",
    "create_rate",
    "Parameter",
    "ParameterType",
    "SetParametersResult",
    "Duration",
    "logging",
    "qos",
    "Future",
    "Clock",
    "ClockType",
    "Time",
    "Timer",
    "CallbackGroup",
    "MutuallyExclusiveCallbackGroup",
    "ReentrantCallbackGroup",
    "get_default_context",
    "get_domain_id",
]
