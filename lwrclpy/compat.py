from types import ModuleType
import inspect


def _is_swig_moved_value_error(exc: BaseException) -> bool:
    text = str(exc)
    return (
        "cannot release ownership as memory is not owned" in text
        or "cannot release ownership" in text and "&&" in text
    )


def _clone_swig_message_arg(value):
    if not hasattr(value, "this"):
        return value
    from .message_utils import _copy_val
    return _copy_val(value)


def _is_swig_sequence_instance(value) -> bool:
    type_name = type(value).__name__.lower()
    if "vector" in type_name or "array" in type_name:
        return hasattr(value, "__iter__")
    return (
        hasattr(value, "this")
        and hasattr(value, "__iter__")
        and (hasattr(value, "size") or hasattr(value, "__len__"))
        and (hasattr(value, "begin") or hasattr(value, "end") or hasattr(value, "front") or hasattr(value, "back"))
    )


def _make_field_accessor(original):
    def _field_accessor(self, *args):
        if not args:
            return original(self)
        if len(args) == 1:
            try:
                return original(self, _clone_swig_message_arg(args[0]))
            except RuntimeError as exc:
                if not _is_swig_moved_value_error(exc):
                    raise
                try:
                    from .message_utils import _copy_val
                    cloned = _copy_val(args[0])
                    return original(self, cloned)
                except Exception:
                    raise exc
            except Exception:
                raise
        try:
            return original(self, *args)
        except RuntimeError as exc:
            if len(args) != 1 or not _is_swig_moved_value_error(exc):
                raise
            try:
                from .message_utils import _copy_val
                cloned = _copy_val(args[0])
                return original(self, cloned)
            except Exception:
                raise exc

    try:
        _field_accessor.__name__ = getattr(original, "__name__", "_field_accessor")
        _field_accessor.__doc__ = getattr(original, "__doc__", None)
    except Exception:
        pass
    _field_accessor.__lwrclpy_accessor_patched__ = True
    return _field_accessor


def _patch_message_class(cls):
    if getattr(cls, "__lwrclpy_attr_patched__", False):
        return
    cls_name = getattr(cls, "__name__", "")
    if cls_name.endswith("PubSubType") or "vector" in cls_name.lower() or "array" in cls_name.lower():
        return
    try:
        inst = cls()
    except Exception:
        return
    if _is_swig_sequence_instance(inst):
        return

    simple_fields = []
    for name in dir(inst):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(inst, name)
        except Exception:
            continue
        if not callable(attr):
            continue
        try:
            sig = inspect.signature(attr)
            params = list(sig.parameters.values())
            if any(p.default is inspect._empty and p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD for p in params[1:]):
                continue
        except Exception:
            pass
        try:
            attr()
        except TypeError:
            continue
        except Exception:
            continue
        simple_fields.append(name)

    if not simple_fields:
        return

    for name in simple_fields:
        try:
            original = getattr(cls, name)
        except Exception:
            continue
        if not callable(original) or getattr(original, "__lwrclpy_accessor_patched__", False):
            continue
        try:
            setattr(cls, name, _make_field_accessor(original))
        except Exception:
            continue

    # Pre-warm message_utils field name caches so that clone_message /
    # expose_callable_fields never need to call dir() for this class.
    try:
        from .message_utils import _callable_fields_cache, _field_names_cache, _SKIP_FIELDS
        _callable_fields_cache[cls] = tuple(simple_fields)
        if cls not in _field_names_cache:
            all_fields = tuple(
                n for n in dir(inst)
                if not n.startswith("_") and n not in _SKIP_FIELDS
            )
            _field_names_cache[cls] = all_fields
    except Exception:
        pass

    def __getattr__(self, name):
        if name in simple_fields:
            try:
                attr = object.__getattribute__(self, name)
                if callable(attr):
                    return attr()
            except Exception:
                pass
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in simple_fields:
            try:
                attr = object.__getattribute__(self, name)
                if callable(attr):
                    try:
                        attr(value)
                        return
                    except Exception:
                        pass
            except Exception:
                pass
        object.__setattr__(self, name, value)

    # Preserve existing __getattr__/__setattr__ if present by chaining
    if "__getattr__" not in cls.__dict__:
        cls.__getattr__ = __getattr__
    if "__setattr__" not in cls.__dict__:
        cls.__setattr__ = __setattr__
    setattr(cls, "__lwrclpy_attr_patched__", True)


def patch_message_class(cls):
    _patch_message_class(cls)


def _patch_module(mod: ModuleType):
    for name in dir(mod):
        try:
            obj = getattr(mod, name)
        except Exception:
            continue
        if isinstance(obj, type):
            _patch_message_class(obj)
            patch_kwargs = globals().get("_patch_kwargs_init")
            if callable(patch_kwargs) and not obj.__name__.endswith("PubSubType"):
                patch_kwargs(obj)


def patch_known_message_modules():
    patch_loaded_msg_modules()
    install_message_import_hook()


def patch_loaded_msg_modules():
    import sys

    for name, module in list(sys.modules.items()):
        if not module:
            continue
        if name.endswith(".msg") or ".msg." in name:
            _patch_module(module)


def install_message_import_hook():
    import builtins
    import sys

    if getattr(builtins, "__lwrclpy_msg_import_hook__", False):
        return

    original_import = builtins.__import__

    def _lwrclpy_import(name, globals=None, locals=None, fromlist=(), level=0):
        module = original_import(name, globals, locals, fromlist, level)
        try:
            candidates = {name}
            if fromlist:
                candidates.update(f"{name}.{item}" for item in fromlist if isinstance(item, str))
            for candidate in candidates:
                if candidate.endswith(".msg") or ".msg." in candidate:
                    loaded = sys.modules.get(candidate)
                    if loaded is not None:
                        _patch_module(loaded)
            package = name.split(".")[0]
            msg_module = sys.modules.get(f"{package}.msg")
            if msg_module is not None:
                _patch_module(msg_module)
        except Exception:
            pass
        return module

    builtins.__import__ = _lwrclpy_import
    builtins.__lwrclpy_msg_import_hook__ = True


def ensure_common_interface_constants():
    """Apply constant compatibility for currently loaded message modules.

    Constants are intentionally not hard-coded here. Message modules are patched
    based on the classes that are actually imported and available at runtime.
    """
    patch_loaded_msg_modules()


def _patch_kwargs_init(cls):
    """Allow msg classes to accept kwargs and assign via setters/attributes."""
    if getattr(cls, "__lwrclpy_kwargs_patched__", False):
        return
    _orig_init = getattr(cls, "__init__", None)
    if not callable(_orig_init):
        return

    def _patched_init(self, *args, **kwargs):
        try:
            _orig_init(self, *args)
        except Exception:
            try:
                _orig_init(self)
            except Exception:
                pass
        from .message_utils import _assign  # local import to avoid cycles
        for k, v in kwargs.items():
            try:
                if not _assign(self, k, v):
                    setattr(self, k, v)
            except Exception:
                continue

    try:
        cls.__init__ = _patched_init
        cls.__lwrclpy_kwargs_patched__ = True
    except Exception:
        pass


def patch_kwargs_for_common_interfaces():
    """Patch loaded message classes to accept kwargs and future imports too."""
    patch_loaded_msg_modules()
    install_message_import_hook()
