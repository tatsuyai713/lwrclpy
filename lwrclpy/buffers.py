"""Buffer helpers for ROS-compatible variable-length sequence fields.

The helpers in this module keep the ROS 2 IDL shape unchanged.  They operate on
generated Fast DDS Python message instances and expose large ``sequence<T>``
fields as buffer-protocol objects instead of Python lists when the generated
bindings include the lwrclpy SWIG extensions.
"""

from __future__ import annotations

from typing import Any


class RosidlBuffer:
    """A buffer-oriented view over a generated message sequence field."""

    __slots__ = ("_msg", "_field")

    def __init__(self, msg: Any, field: str):
        self._msg = msg
        self._field = field

    @property
    def field(self) -> str:
        return self._field

    def __len__(self) -> int:
        size = self.size()
        if size is None:
            view = self.memoryview(writable=False)
            return view.nbytes
        return size

    def _helper(self, suffix: str):
        return getattr(self._msg, f"_lwrclpy_{self._field}_{suffix}", None)

    def size(self) -> int | None:
        """Return the element count when the generated binding exposes it."""

        helper = self._helper("size")
        if callable(helper):
            return int(helper())
        try:
            value = getattr(self._msg, self._field)
            if callable(value):
                value = value()
            if hasattr(value, "size"):
                return int(value.size())
            return len(value)
        except Exception:
            return None

    def nbytes(self) -> int:
        """Return the byte length of the exposed buffer."""

        helper = self._helper("nbytes")
        if callable(helper):
            return int(helper())
        size = self.size()
        if size is not None and self._field == "data":
            return size
        return self.memoryview(writable=False).nbytes

    def resize(self, size: int) -> "RosidlBuffer":
        """Resize the field to *size* elements and return self."""

        if size < 0:
            raise ValueError("buffer size must be non-negative")
        helper = self._helper("resize")
        if not callable(helper):
            raise RuntimeError(
                f"{type(self._msg).__name__}.{self._field} does not expose "
                "the lwrclpy resize helper; regenerate message bindings"
            )
        helper(int(size))
        return self

    def memoryview(self, *, writable: bool = True) -> memoryview:
        """Return a memoryview for the sequence field.

        The view is valid while the parent message is alive and the sequence is
        not resized.  Resizing can reallocate the underlying C++ vector.
        """

        helper = self._helper("memoryview")
        if callable(helper):
            view = memoryview(helper())
        else:
            try:
                value = getattr(self._msg, self._field)
                if callable(value):
                    value = value()
                raw_helper = getattr(value, "_lwrclpy_memoryview", None)
                if callable(raw_helper):
                    view = memoryview(raw_helper())
                else:
                    view = memoryview(value)
            except Exception as exc:
                raise RuntimeError(
                    f"{type(self._msg).__name__}.{self._field} does not expose "
                    "a buffer view; regenerate message bindings"
                ) from exc
        if writable and view.readonly:
            raise TypeError(f"{self._field} buffer is read-only")
        return view

    def assign(self, data: Any) -> "RosidlBuffer":
        """Assign bytes-like or buffer-protocol data to the sequence field."""

        setter = getattr(self._msg, self._field, None)
        if not callable(setter):
            raise RuntimeError(f"{type(self._msg).__name__}.{self._field} is not settable")
        setter(data)
        return self

    def tobytes(self) -> bytes:
        """Return a bytes copy of the sequence field."""

        helper = self._helper("bytes")
        if callable(helper):
            return bytes(helper())
        return self.memoryview(writable=False).tobytes()


def sequence_buffer(msg: Any, field: str = "data") -> RosidlBuffer:
    """Return a buffer helper for *msg.field*.

    This is intentionally a free function so generated ROS-compatible message
    classes do not need a public API change or different type name.
    """

    return RosidlBuffer(msg, field)


def data_buffer(msg: Any) -> RosidlBuffer:
    """Shortcut for ``sequence_buffer(msg, "data")``."""

    return sequence_buffer(msg, "data")


__all__ = ["RosidlBuffer", "sequence_buffer", "data_buffer"]
