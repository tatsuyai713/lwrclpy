# lwrclpy/message_utils.py
# Helpers for copying Fast-DDS-generated Python messages.
# Keeps compatibility with fastddsgen getter/setter style while honoring
# rclpy-like attribute assignment (msg.field = value).
#
# Performance notes:
# - Field names are cached per message class to avoid repeated dir() calls.
# - _copy_val / _get_value / _assign are module-level to avoid closure re-creation.
# - SWIG sub-messages are recursively cloned instead of using copy.deepcopy().

from __future__ import annotations
import copy

# Fields injected by SWIG that should never be copied onto new instances.
_SKIP_FIELDS = {"this", "thisown"}

# ---- Module-level caches -------------------------------------------------------
# msg_class -> tuple of relevant field names (excluding _ prefixed and SWIG internals)
_field_names_cache: dict[type, tuple[str, ...]] = {}
# msg_class -> tuple of callable zero-arg field names (getter/setter style)
_callable_fields_cache: dict[type, tuple[str, ...]] = {}


def _get_field_names(msg_cls) -> tuple[str, ...]:
    """Return cacheable field names for a SWIG-generated message class.

    Computes field names once by creating a temporary instance, calling dir(),
    filtering out private/skip fields, and caching the result.
    """
    cached = _field_names_cache.get(msg_cls)
    if cached is not None:
        return cached

    try:
        inst = msg_cls()
    except Exception:
        return ()

    names: list[str] = []
    seen: set[str] = set()
    for name in dir(inst):
        if name.startswith("_") or name in _SKIP_FIELDS or name in seen:
            continue
        seen.add(name)
        names.append(name)

    result = tuple(names)
    _field_names_cache[msg_cls] = result
    return result


def _get_callable_fields(msg_cls) -> tuple[str, ...]:
    """Return the names of zero-arg callable fields for a message class (cached)."""
    cached = _callable_fields_cache.get(msg_cls)
    if cached is not None:
        return cached

    try:
        inst = msg_cls()
    except Exception:
        return ()

    callable_names: list[str] = []
    for name in _get_field_names(msg_cls):
        try:
            attr = getattr(inst, name)
        except Exception:
            continue
        if not callable(attr):
            continue
        try:
            attr()  # test zero-arg call succeeds
            callable_names.append(name)
        except TypeError:
            continue
        except Exception:
            continue

    result = tuple(callable_names)
    _callable_fields_cache[msg_cls] = result
    return result


# ---- _ValueProxy ---------------------------------------------------------------

class _ValueProxy:
    """Callable wrapper so attribute access works like rclpy while keeping msg.field() usable."""

    __slots__ = ("_v",)

    def __init__(self, val):
        self._v = val

    def __call__(self):
        return self._v

    def __getattr__(self, name):
        # Try name first, then name_ (SWIG trailing underscore convention)
        try:
            return getattr(self._v, name)
        except AttributeError:
            # SWIG may add trailing underscore for C++ member variables
            return getattr(self._v, name + '_')

    def __repr__(self):
        # For SWIG vectors, convert to list for better display
        if hasattr(self._v, '__iter__') and hasattr(self._v, 'size'):
            try:
                return repr(list(self._v))
            except Exception:
                pass
        return repr(self._v)

    def __str__(self):
        # For SWIG vectors, convert to list for better display
        if hasattr(self._v, '__iter__') and hasattr(self._v, 'size'):
            try:
                return str(list(self._v))
            except Exception:
                pass
        return str(self._v)

    def __format__(self, spec):
        return format(self._v, spec)

    def __bytes__(self):
        return bytes(self._v) if hasattr(self._v, "__bytes__") else bytes(str(self._v), "utf-8")

    def __len__(self):
        return len(self._v) if hasattr(self._v, "__len__") else 0

    def __iter__(self):
        if hasattr(self._v, "__iter__"):
            return iter(self._v)
        raise TypeError(f"'{type(self._v).__name__}' object is not iterable")

    def __bool__(self):
        return bool(self._v)

    def __eq__(self, other):
        return self._v == other

    def __ne__(self, other):
        return self._v != other

    def __lt__(self, other):
        return self._v < other

    def __le__(self, other):
        return self._v <= other

    def __gt__(self, other):
        return self._v > other

    def __ge__(self, other):
        return self._v >= other

    def __int__(self):
        return int(self._v)

    def __float__(self):
        return float(self._v)

    def __index__(self):
        """Support for range(), slicing, and other operations requiring an integer."""
        return int(self._v)

    def __add__(self, other):
        try:
            return self._v + other
        except Exception:
            return NotImplemented

    def __radd__(self, other):
        try:
            return other + self._v
        except Exception:
            return NotImplemented


# ---- Module-level helpers used by clone_message --------------------------------

def _get_value(src, name):
    """Extract a field value from *src* using fastddsgen conventions."""
    if name in _SKIP_FIELDS or name.startswith("_"):
        return None
    try:
        v = getattr(src, name)
    except Exception:
        return None
    # Instance attribute wins (rclpy-style msg.foo = val)
    if not callable(v):
        return v
    # Prefer zero-arg getter
    try:
        return v()
    except TypeError:
        pass
    except Exception:
        return None
    getter = f"get_{name}"
    try:
        gv = getattr(src, getter)
        if callable(gv):
            return gv()
    except Exception:
        pass
    return None


def _assign(target, name, val) -> bool:
    """Assign *val* to *name* on *target* using fastddsgen conventions."""
    if name in _SKIP_FIELDS or name.startswith("_"):
        return False
    try:
        setter = getattr(target, name, None)
        if callable(setter):
            try:
                setter(val)
            except Exception:
                pass
            # Expose rclpy-style attribute access while keeping callable behavior.
            try:
                setattr(target, name, _ValueProxy(val))
            except Exception:
                try:
                    object.__setattr__(target, name, _ValueProxy(val))
                except Exception:
                    pass
            return True
    except Exception:
        pass
    # Fallback: explicit special-case for common fields present in __dict__ only
    if name == "data" and isinstance(val, (bytes, bytearray, memoryview)):
        try:
            target.data(val)
            return True
        except Exception:
            pass
    try:
        setattr(target, name, val)
        return True
    except Exception:
        try:
            object.__setattr__(target, name, val)
            return True
        except Exception:
            return False


def _copy_val(val):
    """Copy a field value. Optimised for SWIG-generated types."""
    # Fast path for immutable primitives
    if isinstance(val, (str, int, float, bool, type(None))):
        return val

    # Bytes / bytearray / memoryview
    if isinstance(val, (bytes, bytearray)):
        return bytes(val)
    if isinstance(val, memoryview):
        return bytes(val)

    # Buffer protocol fallback (e.g. numpy arrays exposed as buffer)
    if not isinstance(val, (list, tuple, set, dict)) and not callable(val):
        try:
            return bytes(val)
        except Exception:
            pass

    # Collections
    if isinstance(val, list):
        return [_copy_val(v) for v in val]
    if isinstance(val, tuple):
        return tuple(_copy_val(v) for v in val)
    if isinstance(val, set):
        return {_copy_val(v) for v in val}
    if isinstance(val, dict):
        return {k: _copy_val(v) for k, v in val.items()}

    # Callable (SWIG getter) -- call it to get the actual value
    if callable(val):
        try:
            return _copy_val(val())
        except Exception:
            return val

    # SWIG-generated sub-messages: recursive clone instead of deepcopy
    if hasattr(val, "this"):
        try:
            sub_cls = type(val)
            sub_clone = sub_cls()
            for fname in _get_field_names(sub_cls):
                sub_val = _get_value(val, fname)
                if sub_val is not None:
                    _assign(sub_clone, fname, _copy_val(sub_val))
            return sub_clone
        except Exception:
            pass

    # Last resort (should rarely be reached now)
    try:
        return copy.deepcopy(val)
    except Exception:
        return val


# ---- Public API ----------------------------------------------------------------

def expose_callable_fields(msg):
    """
    For a SWIG-generated message instance, expose callable zero-arg fields as
    attributes containing their current value (wrapped in _ValueProxy). This
    improves repr/debugging without cloning the whole message.

    Uses cached callable-field names to avoid re-computing dir() per message.
    """
    msg_cls = type(msg)
    callable_names = _get_callable_fields(msg_cls)

    for name in callable_names:
        try:
            attr = getattr(msg, name)
        except Exception:
            continue
        if not callable(attr):
            # Already replaced (e.g., by __setattr__ patch) -- skip
            continue
        try:
            val = attr()
        except TypeError:
            continue
        except Exception:
            continue
        # Convert SWIG vectors to Python lists to avoid lifetime issues
        if hasattr(val, '__iter__') and hasattr(val, 'size') and 'vector' in type(val).__name__:
            try:
                val = list(val)
            except Exception:
                pass
        try:
            setattr(msg, name, _ValueProxy(val))
        except Exception:
            try:
                object.__setattr__(msg, name, _ValueProxy(val))
            except Exception:
                pass
    return msg


def clone_message(msg, msg_ctor):
    """
    Copy the received/sent message into a fresh instance using
    fastddsgen conventions:
      - getter/setter share the same name (foo() / foo(value))
      - getter fallback: get_foo()
    Also propagates plain attributes to support rclpy-style `msg.foo = x`.

    Uses cached field names to avoid repeated dir() calls.
    """
    clone = msg_ctor()

    # Use cached field names from the message constructor type
    field_names = _get_field_names(msg_ctor)

    # Collect extra instance __dict__ attributes (rclpy-style msg.foo = val)
    extra_names: tuple[str, ...] = ()
    msg_dict = getattr(msg, "__dict__", None)
    if msg_dict:
        extra_names = tuple(
            n for n in msg_dict
            if not n.startswith("_") and n not in _SKIP_FIELDS
        )

    # Process cached fields
    for name in field_names:
        val = _get_value(msg, name)
        if val is None:
            continue
        copied = _copy_val(val)
        _assign(clone, name, copied)

    # Handle extra instance attributes not in the SWIG class definition
    if extra_names:
        field_set = frozenset(field_names)
        for name in extra_names:
            if name in field_set:
                continue  # already processed
            val = _get_value(msg, name)
            if val is None:
                continue
            copied = _copy_val(val)
            _assign(clone, name, copied)

    return clone
