import fastdds
import threading
from .context import get_participant
from .utils import resolve_generated_type


_registered_type_supports = {}
_registered_type_names = {}
_type_support_cache = {}
_registered_type_supports_lock = threading.Lock()


def _get_type_name(ps):
    """PubSubType から型名を取得（getName/get_name/name の順で対応）。"""
    if hasattr(ps, "getName"):
        return ps.getName()
    if hasattr(ps, "get_name"):
        return ps.get_name()
    if hasattr(ps, "name"):  # 一部ビルドで name() を持つ場合
        n = ps.name
        return n() if callable(n) else n
    raise AttributeError("PubSubType has no getName/get_name/name")


def _set_type_name(ps, name):
    """PubSubType の型名を設定（setName/set_name/name の順で対応）。"""
    if hasattr(ps, "setName"):
        ps.setName(name)
        return
    if hasattr(ps, "set_name"):
        ps.set_name(name)
        return
    # name の setter がある場合
    if hasattr(ps, "name") and callable(getattr(ps, "name")):
        try:
            ps.name(name)  # 一部バインディングは name(str) でセット
            return
        except TypeError:
            pass
    raise AttributeError("PubSubType has no setName/set_name/name(str)")


class RegisteredType:
    """生成型の PubSubType を参加者へ登録するユーティリティ。"""

    def __init__(self, obj, type_name_override: str | None = None):
        # obj は「モジュール or クラス」両対応で解決
        _mod, _msg_cls, pubsub_cls = resolve_generated_type(obj)
        self._cache_key = (pubsub_cls, type_name_override)
        with _registered_type_supports_lock:
            cached = _type_support_cache.get(self._cache_key)
        if cached is not None:
            self._type_support, self._type_name = cached
            return

        ps = pubsub_cls()

        if type_name_override:
            _set_type_name(ps, type_name_override)

        # Fast-DDS Python: TypeSupport(TopicDataType) で OK
        self._type_support = fastdds.TypeSupport(ps)
        self._type_name = _get_type_name(ps)
        with _registered_type_supports_lock:
            _type_support_cache[self._cache_key] = (self._type_support, self._type_name)
            if type_name_override is None:
                _registered_type_names[self._cache_key] = self._type_name

    @property
    def type_name(self) -> str:
        return self._type_name

    def register(self):
        participant = get_participant()
        # Fast DDS entities keep references to the registered TopicDataType.
        # Some Python bindings do not keep the wrapping TypeSupport alive for
        # us, so retain it for the participant lifetime.
        key = (id(participant), self._type_name)
        with _registered_type_supports_lock:
            cached = _registered_type_supports.get(key)
            if cached is not None and cached[0] is participant:
                return self._type_name
            if cached is not None:
                _registered_type_supports.pop(key, None)
        participant.register_type(self._type_support)
        with _registered_type_supports_lock:
            _registered_type_supports[key] = (participant, self._type_support)
        return self._type_name
