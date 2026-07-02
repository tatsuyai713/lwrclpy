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
import operator

# Fields injected by SWIG that should never be copied onto new instances.
_SKIP_FIELDS = {"this", "thisown"}

# ---- Module-level caches -------------------------------------------------------
# msg_class -> tuple of relevant field names (excluding _ prefixed and SWIG internals)
_field_names_cache: dict[type, tuple[str, ...]] = {}
# msg_class -> tuple of callable zero-arg field names (getter/setter style)
_callable_fields_cache: dict[type, tuple[str, ...]] = {}

# Avoid eagerly materializing large SWIG vectors such as sensor_msgs/Image.data.
# Small vectors are still converted to lists for convenient rclpy-style access.
_EAGER_VECTOR_LIST_MAX_LEN = 4096


def _is_swig_vector(value) -> bool:
    return hasattr(value, '__iter__') and hasattr(value, 'size') and 'vector' in type(value).__name__


def _is_swig_sequence(value) -> bool:
    type_name = type(value).__name__.lower()
    if "vector" in type_name or "array" in type_name:
        return hasattr(value, "__iter__")
    return (
        hasattr(value, "this")
        and hasattr(value, "__iter__")
        and (hasattr(value, "size") or hasattr(value, "__len__"))
        and (hasattr(value, "begin") or hasattr(value, "end") or hasattr(value, "front") or hasattr(value, "back"))
    )


def _swig_vector_len(value) -> int | None:
    try:
        return int(value.size())
    except Exception:
        return None


def _buffer_view(value):
    lwrclpy_memoryview = getattr(value, "_lwrclpy_memoryview", None)
    if callable(lwrclpy_memoryview):
        try:
            return memoryview(lwrclpy_memoryview())
        except Exception:
            pass
    memoryview_method = getattr(value, "memoryview", None)
    if callable(memoryview_method):
        try:
            return memoryview(memoryview_method())
        except Exception:
            pass
    get_buffer = getattr(value, "get_buffer", None)
    if callable(get_buffer):
        try:
            buffer_obj = get_buffer()
            if "SwigPyObject" in type(buffer_obj).__name__:
                raise TypeError("raw SWIG pointer is not a Python buffer view")
            view = memoryview(buffer_obj)
            # Some generated bindings expose get_buffer() as a raw SWIG pointer
            # object.  memoryview(pointer) can succeed but represents the
            # pointer wrapper, not the vector contents.  Use it only when it
            # reports the same byte size as the vector.
            vector_len = _swig_vector_len(value)
            if vector_len is None or view.nbytes == vector_len:
                return view
        except Exception:
            pass
    try:
        return memoryview(value)
    except Exception:
        return None


def _buffer_bytes(value):
    lwrclpy_bytes = getattr(value, "_lwrclpy_bytes", None)
    if callable(lwrclpy_bytes):
        try:
            return bytes(lwrclpy_bytes())
        except Exception:
            pass
    view = _buffer_view(value)
    if view is not None:
        return view.tobytes()
    return None


def _message_field_memoryview(msg, name: str):
    helper = getattr(msg, f"_lwrclpy_{name}_memoryview", None)
    if callable(helper):
        try:
            return memoryview(helper())
        except Exception:
            pass
    return None


def _message_field_bytes(msg, name: str):
    helper = getattr(msg, f"_lwrclpy_{name}_bytes", None)
    if callable(helper):
        try:
            return bytes(helper())
        except Exception:
            pass
    view = _message_field_memoryview(msg, name)
    if view is not None:
        return view
    return None


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
        # For small SWIG vectors, convert to list for better display.  Large
        # payload fields such as sensor_msgs/Image.data must stay compact.
        if _is_swig_vector(self._v):
            vector_len = _swig_vector_len(self._v)
            if vector_len is not None and vector_len > _EAGER_VECTOR_LIST_MAX_LEN:
                return f"<{type(self._v).__name__} size={vector_len}>"
            try:
                return repr(list(self._v))
            except Exception:
                pass
        return repr(self._v)

    def __str__(self):
        # For small SWIG vectors, convert to list for better display.  Large
        # payload fields such as sensor_msgs/Image.data must stay compact.
        if _is_swig_vector(self._v):
            vector_len = _swig_vector_len(self._v)
            if vector_len is not None and vector_len > _EAGER_VECTOR_LIST_MAX_LEN:
                return f"<{type(self._v).__name__} size={vector_len}>"
            try:
                return str(list(self._v))
            except Exception:
                pass
        return str(self._v)

    def __format__(self, spec):
        return format(self._v, spec)

    def __bytes__(self):
        data = _buffer_bytes(self._v)
        if data is not None:
            return data
        if _is_swig_vector(self._v):
            try:
                return bytes(bytearray(self._v))
            except Exception:
                pass
        try:
            return bytes(self._v)
        except Exception:
            return bytes(str(self._v), "utf-8")

    def __len__(self):
        vector_len = _swig_vector_len(self._v)
        if vector_len is not None:
            return vector_len
        return len(self._v) if hasattr(self._v, "__len__") else 0

    def __iter__(self):
        if hasattr(self._v, "__iter__"):
            return iter(self._v)
        raise TypeError(f"'{type(self._v).__name__}' object is not iterable")

    def __getitem__(self, key):
        try:
            return self._v[key]
        except TypeError:
            if isinstance(key, int):
                return self._v[int(key)]
            raise

    def __bool__(self):
        vector_len = _swig_vector_len(self._v)
        if vector_len is not None:
            return vector_len != 0
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
        return _proxy_binary(operator.add, self._v, other)

    def __radd__(self, other):
        return _proxy_binary(operator.add, other, self._v)

    def __sub__(self, other):
        return _proxy_binary(operator.sub, self._v, other)

    def __rsub__(self, other):
        return _proxy_binary(operator.sub, other, self._v)

    def __mul__(self, other):
        return _proxy_binary(operator.mul, self._v, other)

    def __rmul__(self, other):
        return _proxy_binary(operator.mul, other, self._v)

    def __truediv__(self, other):
        return _proxy_binary(operator.truediv, self._v, other)

    def __rtruediv__(self, other):
        return _proxy_binary(operator.truediv, other, self._v)

    def __floordiv__(self, other):
        return _proxy_binary(operator.floordiv, self._v, other)

    def __rfloordiv__(self, other):
        return _proxy_binary(operator.floordiv, other, self._v)

    def __mod__(self, other):
        return _proxy_binary(operator.mod, self._v, other)

    def __rmod__(self, other):
        return _proxy_binary(operator.mod, other, self._v)

    def __pow__(self, other):
        return _proxy_binary(operator.pow, self._v, other)

    def __rpow__(self, other):
        return _proxy_binary(operator.pow, other, self._v)

    def __neg__(self):
        return -self._v

    def __pos__(self):
        return +self._v

    def __abs__(self):
        return abs(self._v)


def _proxy_binary(op, left, right):
    try:
        if isinstance(left, _ValueProxy):
            left = left()
        if isinstance(right, _ValueProxy):
            right = right()
        return op(left, right)
    except Exception:
        return NotImplemented


def _shadow_attr(obj, name: str, value) -> bool:
    for setter in (object.__setattr__, setattr):
        try:
            setter(obj, name, value)
            return True
        except Exception:
            continue
    return False


# ---- Module-level helpers used by clone_message --------------------------------

def _get_value(src, name):
    """Extract a field value from *src* using fastddsgen conventions."""
    if name in _SKIP_FIELDS or name.startswith("_"):
        return None
    fast_value = _message_field_memoryview(src, name)
    if fast_value is None:
        fast_value = _message_field_bytes(src, name)
    if fast_value is not None:
        return fast_value
    try:
        inst_dict = getattr(src, "__dict__", None)
        if inst_dict and name in inst_dict:
            v = inst_dict[name]
            if not callable(v):
                return v
            try:
                return v()
            except Exception:
                return v
    except Exception:
        pass
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


def _assign(target, name, val, *, strict: bool = False) -> bool:
    """Assign *val* to *name* on *target* using fastddsgen conventions."""
    if name in _SKIP_FIELDS or name.startswith("_"):
        return False
    setter = getattr(target, name, None)
    if callable(setter):
        candidates = [val]
        view = _buffer_view(val)
        if view is not None:
            candidates.append(view)
            try:
                candidates.append(view.cast("B"))
            except Exception:
                pass
            # Last-resort fallback for bindings that do not consume
            # Py_buffer directly.  Prefer the buffer objects above so
            # generated uint8/octet setters can do a single C++ copy.
            candidates.append(view.tobytes())
        seen_candidate_ids: set[int] = set()
        last_error = None
        for candidate in candidates:
            candidate_id = id(candidate)
            if candidate_id in seen_candidate_ids:
                continue
            seen_candidate_ids.add(candidate_id)
            try:
                setter(candidate)
            except Exception as exc:
                last_error = exc
                continue
            break
        else:
            if strict:
                raise TypeError(
                    f"Failed to assign field {type(target).__name__}.{name}: "
                    f"setter rejected {type(val).__name__}"
                ) from last_error
            return False
        return True
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
        return False


def _assign_required(target, name, val) -> None:
    if not _assign(target, name, val, strict=True):
        raise AttributeError(f"Failed to assign field {type(target).__name__}.{name}")


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

    if _is_swig_sequence(val):
        try:
            return [_copy_val(v) for v in val]
        except Exception:
            try:
                return list(val)
            except Exception:
                return val

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
                    if _is_swig_vector(sub_val) and _assign(sub_clone, fname, sub_val):
                        continue
                    _assign_required(sub_clone, fname, _copy_val(sub_val))
            return sub_clone
        except Exception as exc:
            raise TypeError(f"Failed to clone nested message {type(val).__name__}") from exc

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
        fast_view = _message_field_memoryview(msg, name)
        if fast_view is not None:
            _shadow_attr(msg, name, fast_view)
            continue
        try:
            val = attr()
        except TypeError:
            continue
        except Exception:
            continue
        # Convert only small SWIG vectors to Python lists for display
        # convenience.  Large byte vectors are exposed as memoryview when the
        # generated binding supports it, avoiding Python list allocation and
        # enabling bytes-like consumers such as numpy.frombuffer().
        if _is_swig_vector(val):
            vector_len = _swig_vector_len(val)
            if vector_len is None:
                vector_len = _EAGER_VECTOR_LIST_MAX_LEN + 1
            if vector_len <= _EAGER_VECTOR_LIST_MAX_LEN:
                try:
                    val = list(val)
                except Exception:
                    pass
            else:
                view = _buffer_view(val)
                if view is not None:
                    _shadow_attr(msg, name, view)
                    continue
        _shadow_attr(msg, name, _ValueProxy(val))
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
        view = _buffer_view(val)
        if view is not None and _assign(clone, name, view):
            continue
        if _is_swig_vector(val) and _assign(clone, name, val):
            continue
        copied = _copy_val(val)
        _assign_required(clone, name, copied)

    # Handle extra instance attributes not in the SWIG class definition
    if extra_names:
        field_set = frozenset(field_names)
        for name in extra_names:
            if name in field_set:
                continue  # already processed
            val = _get_value(msg, name)
            if val is None:
                continue
            view = _buffer_view(val)
            if view is not None and _assign(clone, name, view):
                continue
            if _is_swig_vector(val) and _assign(clone, name, val):
                continue
            copied = _copy_val(val)
            _assign_required(clone, name, copied)

    return clone
