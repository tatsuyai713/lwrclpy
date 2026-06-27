import logging
import os
import threading
import time
from collections import deque
from typing import Optional, List, Any

from .context import get_participant
from .parameters import Parameter, ParameterType, SetParametersResult, coerce_parameter
from .qos import QoSProfile
from .publisher import Publisher
from .subscription import Subscription
from .typesupport import RegisteredType
from .utils import (
    resolve_generated_type,
    get_or_create_topic,
    resolve_name,
    TOPIC_PREFIX,
    env_int,
)
from .client import Client
from .service import Service
from .clock import Clock
from .guard_condition import GuardCondition


def _patch_message_type_for_compat(msg_cls) -> None:
    try:
        from .compat import patch_message_class
        patch_message_class(msg_cls)
    except Exception:
        pass


_LOGGER_STATE_MAX = env_int("LWRCLPY_LOGGER_STATE_MAX", 4096, minimum=1)


# --- rclpy.Rate 相当（壁時計ベース） -----------------------------------------
class _WallRate:
    """ROS2 の rclpy.Rate に似せた壁時計ベースの Rate。
    - hz を指定（例: 10.0 なら 100ms 周期）
    - sleep() は次の周期まで待機し、ドリフトを補正
    - reset() で次周期基準を「現在」にリセット
    """

    __slots__ = ("_period_ns", "_next_ns")

    def __init__(self, hz: float):
        if hz <= 0:
            raise ValueError("rate hz must be > 0")
        self._period_ns = int(1e9 / float(hz))
        now = time.monotonic_ns()
        self._next_ns = now + self._period_ns

    def reset(self) -> None:
        """次の起床時刻を現在からにリセット。"""
        self._next_ns = time.monotonic_ns() + self._period_ns

    def sleep(self) -> None:
        """次の周期までスリープ。過剰遅延時は直ちに次周期を再設定して戻る（busy wait はしない）。"""
        now = time.monotonic_ns()
        # 既に次周期を過ぎている場合は、抜けるだけ（次基準を進めておく）
        if now >= self._next_ns:
            # どれだけ遅延していても「今から 1 周期後」を次基準にする（ドリフト補正）
            self._next_ns = now + self._period_ns
            return

        # 残り時間を sleep
        remaining_ns = self._next_ns - now
        time.sleep(remaining_ns / 1e9)

        # 次基準を 1 周期進める
        self._next_ns += self._period_ns


class _NodeLogger:
    """Minimal rclpy.get_logger() equivalent backed by Python logging."""

    _configured = False
    _throttle_last: dict = {}  # class-level storage for throttle timestamps
    _once_logged: set = set()  # class-level storage for once-only messages
    _skipfirst_done: set = set()  # class-level storage for skipfirst messages

    def __init__(self, name: str):
        if not _NodeLogger._configured and not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="[%(levelname)s] %(name)s: %(message)s",
            )
            _NodeLogger._configured = True
        self._logger = logging.getLogger(name)
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def set_level(self, level):
        """Set the logging level."""
        if hasattr(level, 'value'):
            self._logger.setLevel(level.value)
        else:
            self._logger.setLevel(level)

    def get_effective_level(self):
        """Get the effective logging level."""
        from .logging import LoggingSeverity
        level = self._logger.getEffectiveLevel()
        try:
            return LoggingSeverity(level)
        except ValueError:
            return LoggingSeverity.INFO

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def fatal(self, msg, *args, **kwargs):
        self._logger.fatal(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        self._logger.log(level, msg, *args, **kwargs)

    # Throttled logging methods
    def _should_log_throttle(self, key: str, period: float) -> bool:
        now = time.time()
        last = _NodeLogger._throttle_last.get(key, 0)
        if now - last >= period:
            _NodeLogger._throttle_last[key] = now
            _NodeLogger._prune_mapping(_NodeLogger._throttle_last)
            return True
        return False

    @staticmethod
    def _prune_mapping(mapping: dict) -> None:
        while len(mapping) > _LOGGER_STATE_MAX:
            try:
                mapping.pop(next(iter(mapping)))
            except Exception:
                break

    @staticmethod
    def _add_bounded(state: set, key: str) -> None:
        state.add(key)
        while len(state) > _LOGGER_STATE_MAX:
            try:
                state.pop()
            except KeyError:
                break

    def debug_throttle(self, period: float, msg, *args, **kwargs):
        key = f"{self._name}:debug:{msg}"
        if self._should_log_throttle(key, period):
            self.debug(msg, *args, **kwargs)

    def info_throttle(self, period: float, msg, *args, **kwargs):
        key = f"{self._name}:info:{msg}"
        if self._should_log_throttle(key, period):
            self.info(msg, *args, **kwargs)

    def warn_throttle(self, period: float, msg, *args, **kwargs):
        key = f"{self._name}:warn:{msg}"
        if self._should_log_throttle(key, period):
            self.warn(msg, *args, **kwargs)

    def warning_throttle(self, period: float, msg, *args, **kwargs):
        self.warn_throttle(period, msg, *args, **kwargs)

    def error_throttle(self, period: float, msg, *args, **kwargs):
        key = f"{self._name}:error:{msg}"
        if self._should_log_throttle(key, period):
            self.error(msg, *args, **kwargs)

    def fatal_throttle(self, period: float, msg, *args, **kwargs):
        key = f"{self._name}:fatal:{msg}"
        if self._should_log_throttle(key, period):
            self.fatal(msg, *args, **kwargs)

    # Once-only logging methods
    def debug_once(self, msg, *args, **kwargs):
        key = f"{self._name}:debug:{msg}"
        if key not in _NodeLogger._once_logged:
            _NodeLogger._add_bounded(_NodeLogger._once_logged, key)
            self.debug(msg, *args, **kwargs)

    def info_once(self, msg, *args, **kwargs):
        key = f"{self._name}:info:{msg}"
        if key not in _NodeLogger._once_logged:
            _NodeLogger._add_bounded(_NodeLogger._once_logged, key)
            self.info(msg, *args, **kwargs)

    def warn_once(self, msg, *args, **kwargs):
        key = f"{self._name}:warn:{msg}"
        if key not in _NodeLogger._once_logged:
            _NodeLogger._add_bounded(_NodeLogger._once_logged, key)
            self.warn(msg, *args, **kwargs)

    def warning_once(self, msg, *args, **kwargs):
        self.warn_once(msg, *args, **kwargs)

    def error_once(self, msg, *args, **kwargs):
        key = f"{self._name}:error:{msg}"
        if key not in _NodeLogger._once_logged:
            _NodeLogger._add_bounded(_NodeLogger._once_logged, key)
            self.error(msg, *args, **kwargs)

    def fatal_once(self, msg, *args, **kwargs):
        key = f"{self._name}:fatal:{msg}"
        if key not in _NodeLogger._once_logged:
            _NodeLogger._add_bounded(_NodeLogger._once_logged, key)
            self.fatal(msg, *args, **kwargs)

    # Skip-first logging methods
    def debug_skipfirst(self, msg, *args, **kwargs):
        key = f"{self._name}:debug:{msg}"
        if key in _NodeLogger._skipfirst_done:
            self.debug(msg, *args, **kwargs)
        else:
            _NodeLogger._add_bounded(_NodeLogger._skipfirst_done, key)

    def info_skipfirst(self, msg, *args, **kwargs):
        key = f"{self._name}:info:{msg}"
        if key in _NodeLogger._skipfirst_done:
            self.info(msg, *args, **kwargs)
        else:
            _NodeLogger._add_bounded(_NodeLogger._skipfirst_done, key)

    def warn_skipfirst(self, msg, *args, **kwargs):
        key = f"{self._name}:warn:{msg}"
        if key in _NodeLogger._skipfirst_done:
            self.warn(msg, *args, **kwargs)
        else:
            _NodeLogger._add_bounded(_NodeLogger._skipfirst_done, key)

    def warning_skipfirst(self, msg, *args, **kwargs):
        self.warn_skipfirst(msg, *args, **kwargs)

    def error_skipfirst(self, msg, *args, **kwargs):
        key = f"{self._name}:error:{msg}"
        if key in _NodeLogger._skipfirst_done:
            self.error(msg, *args, **kwargs)
        else:
            _NodeLogger._add_bounded(_NodeLogger._skipfirst_done, key)

    def fatal_skipfirst(self, msg, *args, **kwargs):
        key = f"{self._name}:fatal:{msg}"
        if key in _NodeLogger._skipfirst_done:
            self.fatal(msg, *args, **kwargs)
        else:
            _NodeLogger._add_bounded(_NodeLogger._skipfirst_done, key)

    def get_child(self, suffix: str) -> "_NodeLogger":
        """Get a child logger with the given suffix."""
        child_name = f"{self._name}.{suffix}"
        return _NodeLogger(child_name)


class Node:
    def __init__(
        self,
        name: str,
        namespace: str = "",
        *,
        allow_undeclared_parameters: bool = True,
        automatically_declare_parameters_from_overrides: bool = False,
        parameters: Optional[List[Parameter]] = None,
    ):
        self._name = name
        self._namespace = namespace if namespace.startswith("/") or namespace == "" else "/" + namespace
        self._pubsub_prefix = TOPIC_PREFIX  # ROS 2 DDS mapping: rt/<topic>
        self._service_prefix = ""  # rq/rr are applied in client/service helpers
        self._participant = get_participant()
        self._logger = _NodeLogger(self.get_fully_qualified_name())
        self._topics: dict[str, tuple[object, bool]] = {}  # resolved name -> (Topic, owned)
        self._publishers: List[Publisher] = []
        self._subscriptions: List[Subscription] = []
        self._clients: List[Client] = []
        self._services: List[Service] = []
        self._action_servers: List[Any] = []
        self._action_clients: List[Any] = []
        self._timers: List[Any] = []
        self._guard_conditions: List[GuardCondition] = []
        self._destroyed = False
        self._callback_queue: deque = deque()
        self._callback_lock = threading.Lock()
        self._callback_queue_maxsize = env_int("LWRCLPY_NODE_CALLBACK_QUEUE_MAXSIZE", 0)
        self._callback_queue_drop_policy = os.environ.get("LWRCLPY_NODE_CALLBACK_DROP_POLICY", "drop_oldest")
        self._callback_drop_count = 0
        self._executor_wake_event = None  # set by Executor.add_node()
        self._type_cache = {}  # key: message classの完全修飾名 / module名
        self._parameters: dict[str, Parameter] = {}
        self._parameter_descriptors: dict[str, Any] = {}
        self._parameters_lock = threading.Lock()
        self._allow_undeclared_parameters = allow_undeclared_parameters
        self._auto_declare_from_overrides = automatically_declare_parameters_from_overrides
        self._clock = Clock()
        self._default_callback_group = None
        self._callback_groups: List[Any] = []
        self._entity_callback_groups: dict[Any, Any] = {}
        self._cuda_ipc_metadata_publishers: dict[str, Publisher] = {}
        self._cuda_ipc_metadata_subscriptions: List[Subscription] = []
        self._shm_metadata_publishers: dict[str, Publisher] = {}
        self._shm_metadata_subscriptions: List[Subscription] = []

        if parameters:
            self.declare_parameters("", [(p.name, p.value) if isinstance(p, Parameter) else p for p in parameters])

    def _cache_key(self, msg_cls):
        return f"{msg_cls.__module__}.{msg_cls.__name__}"

    def _raise_if_destroyed(self) -> None:
        if self._destroyed:
            raise RuntimeError("Node has been destroyed")

    def _resolve_topic_name(self, name: str) -> str:
        """Apply ROS 2 name resolution and DDS topic prefix (rt/)."""
        resolved = resolve_name(name, self._namespace, self._name).lstrip("/")
        if resolved.startswith(self._pubsub_prefix):
            return resolved
        return f"{self._pubsub_prefix}{resolved}" if self._pubsub_prefix else resolved

    # ------------------- rclpy 風の Rate / sleep -------------------
    def create_rate(self, hz: float) -> _WallRate:
        """rclpy.create_rate に相当（Node メソッド版）。壁時計ベース。"""
        self._raise_if_destroyed()
        return _WallRate(hz)

    # 好みで使えるエイリアス（rclpy.rate(...) 風）
    def rate(self, hz: float) -> _WallRate:
        return self.create_rate(hz)

    def sleep(self, seconds: float) -> None:
        """rclpy の簡易 sleep に相当（壁時計の time.sleep）。"""
        if seconds <= 0:
            return
        time.sleep(float(seconds))

    # ------------------- Logger / Parameters / Namespace -------------
    def get_logger(self):
        return self._logger

    def get_namespace(self) -> str:
        return self._namespace if self._namespace else "/"

    def get_fully_qualified_name(self) -> str:
        ns = self.get_namespace().rstrip("/")
        return f"{ns}/{self._name}" if ns else f"/{self._name}"

    def get_clock(self) -> Clock:
        return self._clock

    def declare_parameter(self, name: str, value=None, descriptor=None, ignore_override: bool = False):
        """Store a parameter locally (best-effort rclpy compatibility)."""
        del ignore_override
        with self._parameters_lock:
            if name in self._parameters:
                if descriptor is not None:
                    self._parameter_descriptors[name] = descriptor
                return self._parameters[name]
            param = Parameter(name, value)
            validation = self._validate_parameter_update(param, descriptor)
            if not validation.successful:
                raise ValueError(validation.reason)
            self._parameters[name] = param
            if descriptor is not None:
                self._parameter_descriptors[name] = descriptor
            return param

    def declare_parameters(self, namespace: str, parameters):
        """Bulk declare with optional namespace prefix."""
        ns = namespace.rstrip("/") + "/" if namespace else ""
        declared = []
        for p in parameters:
            if isinstance(p, Parameter):
                name, value, descriptor = p.name, p.value, None
            else:
                if len(p) == 2:
                    name, value = p
                    descriptor = None
                elif len(p) == 3:
                    name, value, descriptor = p
                else:
                    raise TypeError("declare_parameters expects (name, value) or (name, value, descriptor) tuples")
            declared.append(self.declare_parameter(ns + name, value, descriptor=descriptor))
        return declared

    def has_parameter(self, name: str) -> bool:
        with self._parameters_lock:
            return name in self._parameters

    def get_parameter(self, name: str) -> Parameter:
        with self._parameters_lock:
            if name in self._parameters:
                return self._parameters[name]
        if self._allow_undeclared_parameters:
            return Parameter(name, ParameterType.NOT_SET)
        raise KeyError(f"Parameter '{name}' is not declared")

    def get_parameter_or(self, name: str, alternative_value=None):
        with self._parameters_lock:
            param = self._parameters.get(name)
        return param if param is not None else alternative_value

    def get_parameters(self, names) -> List[Parameter]:
        return [self.get_parameter(n) for n in names]

    def set_parameter(self, name: str, value) -> SetParametersResult:
        """Set a single parameter by name and value."""
        param = Parameter(name, value)
        results = self.set_parameters([param])
        return results[0] if results else SetParametersResult(False, "Failed to set parameter")

    def set_parameters(self, parameters) -> List[SetParametersResult]:
        """Set parameters from Parameter objects or (name, value) tuples."""
        results = []
        with self._parameters_lock:
            for p in parameters:
                param = coerce_parameter(p)
                if param.name not in self._parameters:
                    if self._auto_declare_from_overrides or self._allow_undeclared_parameters:
                        pass
                    else:
                        results.append(SetParametersResult(False, f"Parameter '{param.name}' not declared"))
                        continue
                validation = self._validate_parameter_update(param, self._parameter_descriptors.get(param.name))
                if not validation.successful:
                    results.append(validation)
                    continue
                self._parameters[param.name] = param
                results.append(SetParametersResult(True, ""))
        return results

    def set_parameters_atomically(self, parameters) -> SetParametersResult:
        coerced = [coerce_parameter(p) for p in parameters]
        with self._parameters_lock:
            for param in coerced:
                if param.name not in self._parameters and not (
                    self._auto_declare_from_overrides or self._allow_undeclared_parameters
                ):
                    return SetParametersResult(False, f"Parameter '{param.name}' not declared")
                validation = self._validate_parameter_update(param, self._parameter_descriptors.get(param.name))
                if not validation.successful:
                    return validation
            for param in coerced:
                self._parameters[param.name] = param
        return SetParametersResult(True, "")

    def describe_parameter(self, name: str):
        return self._parameter_descriptors.get(name)

    def describe_parameters(self, names):
        return [self.describe_parameter(name) for name in names]

    def _validate_parameter_update(self, param: Parameter, descriptor) -> SetParametersResult:
        if descriptor is None:
            return SetParametersResult(True, "")
        if getattr(descriptor, "read_only", False) and param.name in self._parameters:
            return SetParametersResult(False, f"Parameter '{param.name}' is read-only")

        expected_type = getattr(descriptor, "type", ParameterType.NOT_SET)
        try:
            expected_type = ParameterType(expected_type)
        except ValueError:
            return SetParametersResult(False, f"Invalid descriptor type for parameter '{param.name}'")
        if expected_type != ParameterType.NOT_SET and param.type != expected_type:
            return SetParametersResult(False, f"Parameter '{param.name}' has type {param.type.name}; expected {expected_type.name}")

        if param.type == ParameterType.INTEGER:
            return self._validate_numeric_ranges(param.name, param.value, getattr(descriptor, "integer_range", ()))
        if param.type == ParameterType.DOUBLE:
            return self._validate_numeric_ranges(param.name, param.value, getattr(descriptor, "floating_point_range", ()))
        return SetParametersResult(True, "")

    @staticmethod
    def _validate_numeric_ranges(name: str, value, ranges) -> SetParametersResult:
        if not ranges:
            return SetParametersResult(True, "")
        for range_spec in ranges:
            low = getattr(range_spec, "from_value", None)
            high = getattr(range_spec, "to_value", None)
            step = getattr(range_spec, "step", 0)
            if low is not None and value < low:
                return SetParametersResult(False, f"Parameter '{name}' is below minimum {low}")
            if high is not None and value > high:
                return SetParametersResult(False, f"Parameter '{name}' is above maximum {high}")
            if step:
                base = low or 0
                offset = (value - base) / step
                if abs(offset - round(offset)) > 1e-9:
                    return SetParametersResult(False, f"Parameter '{name}' does not satisfy step {step}")
        return SetParametersResult(True, "")

    @property
    def default_callback_group(self):
        if self._default_callback_group is None:
            from .callback_groups import MutuallyExclusiveCallbackGroup
            self._default_callback_group = MutuallyExclusiveCallbackGroup()
            self._callback_groups.append(self._default_callback_group)
        return self._default_callback_group

    @property
    def callback_groups(self):
        return list(self._callback_groups)

    def create_callback_group(self, group_type=None):
        if group_type is None:
            from .callback_groups import MutuallyExclusiveCallbackGroup
            group_type = MutuallyExclusiveCallbackGroup
        group = group_type()
        if group not in self._callback_groups:
            self._callback_groups.append(group)
        return group

    def _resolve_callback_group(self, callback_group):
        group = callback_group if callback_group is not None else self.default_callback_group
        if group not in self._callback_groups:
            self._callback_groups.append(group)
        return group

    def _register_entity_callback_group(self, entity, callback_group):
        if callback_group is None:
            return
        self._entity_callback_groups[entity] = callback_group
        add_entity = getattr(callback_group, "add_entity", None)
        if callable(add_entity):
            add_entity(entity)

    def _get_callback_group(self, entity):
        return self._entity_callback_groups.get(entity)

    def _unregister_entity_callback_group(self, entity):
        group = self._entity_callback_groups.pop(entity, None)
        if group is not None:
            remove_entity = getattr(group, "remove_entity", None)
            if callable(remove_entity):
                remove_entity(entity)

    def _begin_callback_execution(self, entity):
        group = self._get_callback_group(entity) if entity is not None else None
        if group is None:
            return None
        can_execute = getattr(group, "can_execute", None)
        if callable(can_execute) and not can_execute(entity):
            return None
        beginning_execution = getattr(group, "beginning_execution", None)
        if callable(beginning_execution) and not beginning_execution(entity):
            return None
        return group

    def _end_callback_execution(self, entity, group):
        if entity is None or group is None:
            return
        ending_execution = getattr(group, "ending_execution", None)
        if callable(ending_execution):
            ending_execution(entity)

    def _make_deferred_entity_enqueue(self):
        state = {"entity": None, "pending": []}
        lock = threading.Lock()

        def enqueue(cb, msg):
            with lock:
                entity = state["entity"]
                if entity is None:
                    state["pending"].append((cb, msg))
                    return
            self._enqueue_callback(cb, msg, entity)

        def bind(entity):
            with lock:
                state["entity"] = entity
                pending = state["pending"]
                state["pending"] = []
            for cb, msg in pending:
                self._enqueue_callback(cb, msg, entity)

        return enqueue, bind

    def _enqueue_callback_for_callback_owner(self, owner_callback, cb, msg):
        self._enqueue_callback(cb, msg, getattr(owner_callback, "__self__", None))

    # ------------------- Publisher / Subscription 等 -------------------
    def create_publisher(
        self,
        msg_type,
        topic: str,
        qos_profile: QoSProfile | int = 10,
        *,
        callback_group=None,
        event_callbacks=None,
        qos_overriding_options=None,
    ):
        self._raise_if_destroyed()
        del callback_group
        qos = qos_profile if isinstance(qos_profile, QoSProfile) else QoSProfile(depth=int(qos_profile))
        # 型解決（モジュール or クラスの両対応）
        _mod, msg_cls, _pubsub_cls = resolve_generated_type(msg_type)
        _patch_message_type_for_compat(msg_cls)
        key = self._cache_key(msg_cls)
        type_name = self._type_cache.get(key)
        if not type_name:
            ts = RegisteredType(msg_cls)
            type_name = ts.register()
            self._type_cache[key] = type_name
        resolved_topic = self._resolve_topic_name(topic)
        topic_obj, owned = self._create_topic(resolved_topic, type_name)
        self._topics[resolved_topic] = (topic_obj, owned)
        pub = Publisher(
            self._participant,
            topic_obj,
            qos,
            msg_ctor=msg_cls,
            msg_module=_mod,
            pubsub_cls=_pubsub_cls,
            event_callbacks=event_callbacks,
            qos_overriding_options=qos_overriding_options,
        )
        self._configure_cuda_ipc_publisher(pub, resolved_topic, qos)
        self._configure_shared_memory_publisher(pub, resolved_topic, qos)
        self._publishers.append(pub)
        return pub

    def create_subscription(
        self,
        msg_type,
        topic: str,
        callback,
        qos_profile: QoSProfile | int = 10,
        *,
        callback_group=None,
        raw: bool = False,
        event_callbacks=None,
        qos_overriding_options=None,
        content_filter_options=None,
        fast_callback: bool = False,
        expose_fields: Optional[bool] = None,
        batch_callback: bool = False,
        batch_size: Optional[int] = None,
    ):
        self._raise_if_destroyed()
        if raw:
            raise NotImplementedError(
                "create_subscription(raw=True) is not supported: rclpy raw "
                "subscriptions deliver serialized bytes, and lwrclpy does not "
                "currently expose an equivalent serialized receive path"
            )
        if expose_fields is None:
            expose_fields = not fast_callback
        group = self._resolve_callback_group(callback_group)
        qos = qos_profile if isinstance(qos_profile, QoSProfile) else QoSProfile(depth=int(qos_profile))
        # 型解決（モジュール or クラスの両対応）
        _mod, msg_cls, _pubsub_cls = resolve_generated_type(msg_type)
        _patch_message_type_for_compat(msg_cls)
        key = self._cache_key(msg_cls)
        type_name = self._type_cache.get(key)
        if not type_name:
            ts = RegisteredType(msg_cls)
            type_name = ts.register()
            self._type_cache[key] = type_name
        resolved_topic = self._resolve_topic_name(topic)
        topic_obj, owned = self._create_topic(resolved_topic, type_name)
        self._topics[resolved_topic] = (topic_obj, owned)
        # メッセージ生成
        msg_ctor = msg_cls
        enqueue_subscription_callback, bind_subscription_callback = self._make_deferred_entity_enqueue()

        sub = Subscription(
            self._participant,
            topic_obj,
            qos,
            callback,
            msg_ctor,
            enqueue_subscription_callback,
            raw=raw,
            event_callbacks=event_callbacks,
            pubsub_cls=_pubsub_cls,
            msg_module=_mod,
            expose_fields=expose_fields,
            batch_callback=batch_callback,
            batch_size=batch_size,
            qos_overriding_options=qos_overriding_options,
            content_filter_options=content_filter_options,
        )
        self._register_entity_callback_group(sub, group)
        self._configure_cuda_ipc_subscription(sub, resolved_topic, qos)
        self._configure_shared_memory_subscription(sub, resolved_topic, qos)
        self._subscriptions.append(sub)
        bind_subscription_callback(sub)
        return sub

    def create_client(self, srv_type, srv_name: str, qos_profile: QoSProfile | int = 10, *, callback_group=None):
        self._raise_if_destroyed()
        group = self._resolve_callback_group(callback_group)
        qos = qos_profile if isinstance(qos_profile, QoSProfile) else QoSProfile(depth=int(qos_profile))
        resolved = resolve_name(srv_name, self._namespace, self._name)
        enqueue_client_callback, bind_client_callback = self._make_deferred_entity_enqueue()

        client = Client(srv_type, resolved, qos, topic_prefix=self._service_prefix, enqueue_cb=enqueue_client_callback)
        self._clients.append(client)
        self._register_entity_callback_group(client, group)
        bind_client_callback(client)
        return client

    def create_service(self, srv_type, srv_name: str, callback, qos_profile: QoSProfile | int = 10, *, callback_group=None):
        self._raise_if_destroyed()
        group = self._resolve_callback_group(callback_group)
        qos = qos_profile if isinstance(qos_profile, QoSProfile) else QoSProfile(depth=int(qos_profile))
        resolved = resolve_name(srv_name, self._namespace, self._name)
        enqueue_service_callback, bind_service_callback = self._make_deferred_entity_enqueue()

        service = Service(srv_type, resolved, callback, qos, topic_prefix=self._service_prefix, enqueue_cb=enqueue_service_callback)
        self._services.append(service)
        self._register_entity_callback_group(service, group)
        bind_service_callback(service)
        return service

    def create_action_server(self, action_type, action_name: str, execute_callback, **kwargs):
        self._raise_if_destroyed()
        from .action import ActionServer
        server = ActionServer(self, action_type, action_name, execute_callback, **kwargs)
        self._action_servers.append(server)
        return server

    def create_action_client(self, action_type, action_name: str, **kwargs):
        self._raise_if_destroyed()
        from .action import ActionClient
        client = ActionClient(self, action_type, action_name, **kwargs)
        self._action_clients.append(client)
        return client

    def create_timer(self, period_sec: float, callback, *, callback_group=None, oneshot: bool = False):
        self._raise_if_destroyed()
        from .timer import create_timer
        group = self._resolve_callback_group(callback_group)
        enqueue_timer_callback, bind_timer_callback = self._make_deferred_entity_enqueue()

        # Enqueue timer callbacks into the node's callback queue
        t = create_timer(period_sec, callback, oneshot=oneshot, enqueue_cb=enqueue_timer_callback)
        self._timers.append(t)
        self._register_entity_callback_group(t, group)
        bind_timer_callback(t)
        return t

    def create_wall_timer(self, period_sec: float, callback):
        return self.create_timer(period_sec, callback)

    def create_guard_condition(self, callback, *, callback_group=None):
        self._raise_if_destroyed()
        group = self._resolve_callback_group(callback_group)
        enqueue_guard_callback, bind_guard_callback = self._make_deferred_entity_enqueue()

        gc = GuardCondition(callback, enqueue_guard_callback)
        self._guard_conditions.append(gc)
        self._register_entity_callback_group(gc, group)
        bind_guard_callback(gc)
        return gc

    def destroy_publisher(self, pub):
        try:
            pub.destroy()
        finally:
            if pub in self._publishers:
                self._publishers.remove(pub)

    def destroy_subscription(self, sub):
        try:
            sub.destroy()
        finally:
            self._unregister_entity_callback_group(sub)
            if sub in self._subscriptions:
                self._subscriptions.remove(sub)

    def destroy_timer(self, timer):
        try:
            timer.cancel()
        finally:
            self._unregister_entity_callback_group(timer)
            if timer in self._timers:
                self._timers.remove(timer)

    def destroy_client(self, client):
        try:
            client.destroy()
        finally:
            self._unregister_entity_callback_group(client)
            if client in self._clients:
                self._clients.remove(client)

    def destroy_service(self, service):
        try:
            service.destroy()
        finally:
            self._unregister_entity_callback_group(service)
            if service in self._services:
                self._services.remove(service)

    def destroy_action_server(self, server):
        try:
            server.destroy()
        finally:
            if server in self._action_servers:
                self._action_servers.remove(server)

    def destroy_action_client(self, client):
        try:
            client.destroy()
        finally:
            if client in self._action_clients:
                self._action_clients.remove(client)

    def destroy_guard_condition(self, gc):
        try:
            gc.destroy()
        finally:
            self._unregister_entity_callback_group(gc)
            if gc in self._guard_conditions:
                self._guard_conditions.remove(gc)

    def get_name(self):
        return self._name

    def destroy_node(self):
        with self._callback_lock:
            if self._destroyed:
                return
            self._destroyed = True
        # Cancel timers first
        for t in self._timers:
            try:
                self._unregister_entity_callback_group(t)
                t.cancel()
            except Exception:
                pass
        self._timers.clear()
        
        # Destroy clients
        for client in self._clients:
            try:
                self._unregister_entity_callback_group(client)
                client.destroy()
            except Exception:
                pass
        self._clients.clear()
        
        # Destroy services
        for service in self._services:
            try:
                self._unregister_entity_callback_group(service)
                service.destroy()
            except Exception:
                pass
        self._services.clear()

        # Destroy actions
        for server in self._action_servers:
            try:
                server.destroy()
            except Exception:
                pass
        self._action_servers.clear()
        for client in self._action_clients:
            try:
                client.destroy()
            except Exception:
                pass
        self._action_clients.clear()
        
        # Destroy publishers
        for pub in self._publishers:
            try:
                pub.destroy()
            except Exception:
                pass
        self._publishers.clear()
        
        # Destroy subscriptions
        for sub in self._subscriptions:
            try:
                self._unregister_entity_callback_group(sub)
                sub.destroy()
            except Exception:
                pass
        self._subscriptions.clear()
        
        # Destroy guard conditions
        for gc in self._guard_conditions:
            try:
                self._unregister_entity_callback_group(gc)
                gc.destroy()
            except Exception:
                pass
        self._guard_conditions.clear()
        self._entity_callback_groups.clear()
        with self._callback_lock:
            self._callback_queue.clear()
        
        # Note: Topics are managed by Fast DDS and shared across multiple
        # DataWriters/DataReaders. We don't delete them explicitly to avoid
        # double-free issues. Fast DDS will clean them up when the participant
        # is destroyed.
        self._topics.clear()

    def _resolve_std_msgs_string(self):
        try:
            from std_msgs.msg import String
        except Exception:
            return None
        try:
            mod, msg_cls, pubsub_cls = resolve_generated_type(String)
        except Exception:
            return None
        return mod, msg_cls, pubsub_cls

    def _ensure_registered_type(self, msg_cls) -> str | None:
        key = self._cache_key(msg_cls)
        type_name = self._type_cache.get(key)
        if type_name:
            return type_name
        try:
            ts = RegisteredType(msg_cls)
            type_name = ts.register()
        except Exception:
            return None
        self._type_cache[key] = type_name
        return type_name

    def _create_cuda_ipc_metadata_publisher(self, source_topic: str, qos: QoSProfile) -> Publisher | None:
        try:
            from .cuda_ipc import cuda_metadata_topic
            metadata_topic = cuda_metadata_topic(source_topic)
        except Exception:
            return None
        cached = self._cuda_ipc_metadata_publishers.get(metadata_topic)
        if cached is not None:
            return cached
        resolved = self._resolve_std_msgs_string()
        if resolved is None:
            return None
        mod, msg_cls, pubsub_cls = resolved
        type_name = self._ensure_registered_type(msg_cls)
        if not type_name:
            return None
        topic_obj, owned = self._create_topic(metadata_topic, type_name)
        self._topics[metadata_topic] = (topic_obj, owned)
        try:
            pub = Publisher(self._participant, topic_obj, qos, msg_ctor=msg_cls, msg_module=mod, pubsub_cls=pubsub_cls)
        except Exception:
            return None
        self._cuda_ipc_metadata_publishers[metadata_topic] = pub
        self._publishers.append(pub)
        return pub

    def _create_cuda_ipc_metadata_subscription(self, source_topic: str, qos: QoSProfile, callback) -> Subscription | None:
        try:
            from .cuda_ipc import cuda_metadata_topic, get_string_data
            metadata_topic = cuda_metadata_topic(source_topic)
        except Exception:
            return None
        resolved = self._resolve_std_msgs_string()
        if resolved is None:
            return None
        mod, msg_cls, pubsub_cls = resolved
        type_name = self._ensure_registered_type(msg_cls)
        if not type_name:
            return None
        topic_obj, owned = self._create_topic(metadata_topic, type_name)
        self._topics[metadata_topic] = (topic_obj, owned)

        def on_metadata(msg):
            callback(get_string_data(msg))

        def enqueue_metadata_callback(cb, msg):
            self._enqueue_callback_for_callback_owner(callback, cb, msg)

        try:
            sub = Subscription(
                self._participant,
                topic_obj,
                qos,
                on_metadata,
                msg_cls,
                enqueue_metadata_callback,
                raw=False,
                pubsub_cls=pubsub_cls,
                msg_module=mod,
            )
        except Exception:
            return None
        self._cuda_ipc_metadata_subscriptions.append(sub)
        self._subscriptions.append(sub)
        return sub

    def _create_shared_memory_metadata_publisher(self, source_topic: str, qos: QoSProfile) -> Publisher | None:
        try:
            from .shared_memory import shared_memory_metadata_topic
            metadata_topic = shared_memory_metadata_topic(source_topic)
        except Exception:
            return None
        cached = self._shm_metadata_publishers.get(metadata_topic)
        if cached is not None:
            return cached
        resolved = self._resolve_std_msgs_string()
        if resolved is None:
            return None
        mod, msg_cls, pubsub_cls = resolved
        type_name = self._ensure_registered_type(msg_cls)
        if not type_name:
            return None
        topic_obj, owned = self._create_topic(metadata_topic, type_name)
        self._topics[metadata_topic] = (topic_obj, owned)
        try:
            pub = Publisher(self._participant, topic_obj, qos, msg_ctor=msg_cls, msg_module=mod, pubsub_cls=pubsub_cls)
        except Exception:
            return None
        self._shm_metadata_publishers[metadata_topic] = pub
        self._publishers.append(pub)
        return pub

    def _create_shared_memory_metadata_subscription(self, source_topic: str, qos: QoSProfile, callback) -> Subscription | None:
        try:
            from .shared_memory import shared_memory_metadata_topic, get_string_data
            metadata_topic = shared_memory_metadata_topic(source_topic)
        except Exception:
            return None
        resolved = self._resolve_std_msgs_string()
        if resolved is None:
            return None
        mod, msg_cls, pubsub_cls = resolved
        type_name = self._ensure_registered_type(msg_cls)
        if not type_name:
            return None
        topic_obj, owned = self._create_topic(metadata_topic, type_name)
        self._topics[metadata_topic] = (topic_obj, owned)

        def on_metadata(msg):
            callback(get_string_data(msg))

        def enqueue_metadata_callback(cb, msg):
            self._enqueue_callback_for_callback_owner(callback, cb, msg)

        try:
            sub = Subscription(
                self._participant,
                topic_obj,
                qos,
                on_metadata,
                msg_cls,
                enqueue_metadata_callback,
                raw=False,
                pubsub_cls=pubsub_cls,
                msg_module=mod,
            )
        except Exception:
            return None
        self._shm_metadata_subscriptions.append(sub)
        self._subscriptions.append(sub)
        return sub

    def _configure_cuda_ipc_publisher(self, pub: Publisher, resolved_topic: str, qos: QoSProfile) -> None:
        try:
            from .cuda_ipc import cuda_metadata_topic
            metadata_pub = self._create_cuda_ipc_metadata_publisher(resolved_topic, qos)
            if metadata_pub is not None:
                pub._set_cuda_ipc_metadata_publisher(metadata_pub, cuda_metadata_topic(resolved_topic))
        except Exception:
            pass

    def _configure_cuda_ipc_subscription(self, sub: Subscription, resolved_topic: str, qos: QoSProfile) -> None:
        try:
            from .cuda_ipc import cuda_metadata_topic
            metadata_topic = cuda_metadata_topic(resolved_topic)
            sub._set_cuda_ipc_topic(metadata_topic)
            self._create_cuda_ipc_metadata_subscription(resolved_topic, qos, sub._update_cuda_ipc_metadata)
        except Exception:
            pass

    def _configure_shared_memory_publisher(self, pub: Publisher, resolved_topic: str, qos: QoSProfile) -> None:
        try:
            from .shared_memory import shared_memory_metadata_topic
            metadata_pub = self._create_shared_memory_metadata_publisher(resolved_topic, qos)
            if metadata_pub is not None:
                pub._set_shared_memory_metadata_publisher(metadata_pub, shared_memory_metadata_topic(resolved_topic))
        except Exception:
            pass

    def _configure_shared_memory_subscription(self, sub: Subscription, resolved_topic: str, qos: QoSProfile) -> None:
        try:
            from .shared_memory import shared_memory_metadata_topic
            metadata_topic = shared_memory_metadata_topic(resolved_topic)
            sub._set_shared_memory_topic(metadata_topic)
            self._create_shared_memory_metadata_subscription(resolved_topic, qos, sub._update_shared_memory_metadata)
        except Exception:
            pass

    # ------------- internal helpers -----------------
    def _create_topic(self, name: str, type_name: str):
        # Reuse already created topics per name when possible to avoid duplicate registration
        existing = self._topics.get(name)
        if existing:
            return existing
        return get_or_create_topic(self._participant, name, type_name)

    # ---- executor enqueue/dequeue -------------------------------------------------
    def _enqueue_callback(self, cb, msg, entity=None):
        dropped_new = False
        with self._callback_lock:
            if self._destroyed:
                return
            if self._callback_queue_maxsize and len(self._callback_queue) >= self._callback_queue_maxsize:
                if self._callback_queue_drop_policy == "drop_newest":
                    self._callback_drop_count += 1
                    dropped_new = True
                else:
                    self._callback_queue.popleft()
                    self._callback_drop_count += 1
            if dropped_new:
                return
            self._callback_queue.append((cb, msg, entity))
        # Wake the executor immediately after enqueuing
        wake = self._executor_wake_event
        if wake is not None:
            wake.set()

    def _drain_callbacks(self):
        queue = []
        while True:
            item = self._pop_callback()
            if item is None:
                break
            queue.append(item)
        return queue

    def _pop_callback(self):
        with self._callback_lock:
            remaining = len(self._callback_queue)
        for _ in range(remaining):
            with self._callback_lock:
                try:
                    item = self._callback_queue.popleft()
                except IndexError:
                    return None
            if len(item) == 3:
                cb, msg, entity = item
            else:
                cb, msg = item
                entity = None
            group = self._begin_callback_execution(entity)
            if entity is not None and self._get_callback_group(entity) is not None and group is None:
                with self._callback_lock:
                    self._callback_queue.append(item)
                continue
            return cb, msg, entity, group
        return None

    def _has_pending_work(self) -> bool:
        """Internal: check if callbacks are queued or timers are still active."""
        with self._callback_lock:
            if self._callback_queue:
                return True
        for t in self._timers:
            try:
                if not t.is_canceled():
                    return True
            except Exception:
                continue
        return False

    @property
    def performance_stats(self) -> dict[str, object]:
        with self._callback_lock:
            queue_size = len(self._callback_queue)
            dropped = self._callback_drop_count
        return {
            "callback_queue_size": queue_size,
            "callback_queue_maxsize": self._callback_queue_maxsize,
            "callback_queue_drop_policy": self._callback_queue_drop_policy,
            "callback_drop_count": dropped,
        }


# --- Module-level helpers to mirror rclpy API --------------------------------
def create_node(name: str, **kwargs) -> Node:
    return Node(name, **kwargs)


def create_rate(hz: float) -> _WallRate:
    return _WallRate(hz)


Rate = _WallRate
