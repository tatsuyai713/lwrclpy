"""Optional CUDA IPC side channel for lwrclpy-local subscribers.

This module does not make DDS carry CUDA device memory.  It publishes small
metadata messages containing CUDA IPC handles on a hidden side topic while the
normal ROS-compatible topic remains unchanged.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any


_CUDA_ATTR = "_lwrclpy_cuda_ipc_buffers"


def _sanitize_topic_name(topic_name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in topic_name).strip("_") or "root"


def cuda_metadata_topic(topic_name: str) -> str:
    """Return the hidden DDS topic name for CUDA IPC metadata."""

    return f"rt/_lwrclpy/cuda_ipc/{_sanitize_topic_name(topic_name)}"


def _to_jsonable(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [int(v) if isinstance(v, bool | int) else v for v in value]
    return value


@dataclass(slots=True)
class CudaIpcMetadata:
    topic: str
    field: str
    token: str
    handle_b64: str
    nbytes: int
    shape: list[int]
    typestr: str
    strides: list[int] | None
    data_ptr: int
    device_id: int
    owner_pid: int
    created_ns: int
    sequence_number: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "CudaIpcMetadata":
        data = json.loads(text)
        return cls(
            topic=str(data["topic"]),
            field=str(data["field"]),
            token=str(data["token"]),
            handle_b64=str(data["handle_b64"]),
            nbytes=int(data["nbytes"]),
            shape=[int(v) for v in data.get("shape", [])],
            typestr=str(data.get("typestr", "|u1")),
            strides=(
                [int(v) for v in data["strides"]]
                if data.get("strides") is not None
                else None
            ),
            data_ptr=int(data["data_ptr"]),
            device_id=int(data.get("device_id", 0)),
            owner_pid=int(data.get("owner_pid", 0)),
            created_ns=int(data.get("created_ns", 0)),
            sequence_number=int(data.get("sequence_number", 0)),
        )


class CudaIpcBuffer:
    """Subscriber-side CUDA IPC buffer descriptor.

    ``open_cupy()`` is optional and requires CuPy.  Applications that use another
    CUDA binding can consume ``handle`` and metadata directly.
    """

    __slots__ = ("metadata", "_cupy_mem", "_cupy_ptr", "_lock")

    def __init__(self, metadata: CudaIpcMetadata):
        self.metadata = metadata
        self._cupy_mem = None
        self._cupy_ptr = None
        self._lock = threading.Lock()

    @property
    def handle(self) -> bytes:
        return base64.b64decode(self.metadata.handle_b64)

    @property
    def nbytes(self) -> int:
        return self.metadata.nbytes

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(self.metadata.shape)

    @property
    def dtype_typestr(self) -> str:
        return self.metadata.typestr

    @property
    def device_id(self) -> int:
        return self.metadata.device_id

    def open_cupy(self):
        """Open the CUDA IPC memory as a CuPy ndarray.

        This is intentionally lazy so importing lwrclpy does not require CUDA or
        CuPy.  The returned array shares the publisher allocation until closed or
        process exit; the publisher must keep the original allocation alive.
        """

        import numpy as np
        import cupy as cp
        from cupy.cuda import runtime

        with self._lock:
            if self._cupy_mem is None:
                mem_ptr = runtime.ipcOpenMemHandle(self.handle)
                self._cupy_mem = cp.cuda.UnownedMemory(mem_ptr, self.nbytes, self)
                self._cupy_ptr = cp.cuda.MemoryPointer(self._cupy_mem, 0)
            dtype = np.dtype(self.dtype_typestr)
            arr = cp.ndarray(self.shape, dtype=dtype, memptr=self._cupy_ptr)
            if self.metadata.strides:
                arr = cp.ndarray(self.shape, dtype=dtype, memptr=self._cupy_ptr, strides=tuple(self.metadata.strides))
            return arr

    def close(self) -> None:
        with self._lock:
            self._cupy_ptr = None
            self._cupy_mem = None


def attach_cuda_buffer(msg: Any, metadata: CudaIpcMetadata) -> bool:
    buffers = getattr(msg, _CUDA_ATTR, None)
    if buffers is None:
        buffers = {}
        for setter in (setattr, object.__setattr__):
            try:
                setter(msg, _CUDA_ATTR, buffers)
                break
            except Exception:
                continue
        else:
            return False
    buffers[metadata.field] = CudaIpcBuffer(metadata)
    return True


def get_cuda_buffer(msg: Any, field: str = "data") -> CudaIpcBuffer | None:
    buffers = getattr(msg, _CUDA_ATTR, None)
    if not isinstance(buffers, dict):
        return None
    value = buffers.get(field)
    return value if isinstance(value, CudaIpcBuffer) else None


def _array_interface_from_cuda_object(obj: Any) -> dict[str, Any] | None:
    iface = getattr(obj, "__cuda_array_interface__", None)
    if isinstance(iface, dict):
        return iface
    return None


def _device_id_from_cupy() -> int:
    try:
        import cupy as cp
        return int(cp.cuda.runtime.getDevice())
    except Exception:
        return 0


def _ipc_handle_for_pointer(data_ptr: int) -> bytes | None:
    # CuPy exposes cudaIpcGetMemHandle through runtime on common builds.
    try:
        import cupy as cp
        handle = cp.cuda.runtime.ipcGetMemHandle(int(data_ptr))
        if isinstance(handle, bytes):
            return handle
        if isinstance(handle, bytearray):
            return bytes(handle)
        if isinstance(handle, (list, tuple)):
            return bytes(handle)
    except Exception:
        pass

    # cuda-python exposes the driver API on environments that prefer it.
    try:
        from cuda import cuda
        err, handle = cuda.cuIpcGetMemHandle(int(data_ptr))
        if int(err) == 0:
            return bytes(handle.reserved)
    except Exception:
        pass

    return None


def export_cuda_ipc_metadata(
    obj: Any,
    *,
    topic: str,
    field: str = "data",
    token: str | None = None,
    nbytes: int | None = None,
    device_id: int | None = None,
    sequence_number: int = 0,
) -> CudaIpcMetadata | None:
    """Create CUDA IPC metadata for an object exposing ``__cuda_array_interface__``."""

    iface = _array_interface_from_cuda_object(obj)
    if iface is None:
        return None
    data = iface.get("data")
    if not data:
        return None
    data_ptr = int(data[0])
    if data_ptr == 0:
        return None
    handle = _ipc_handle_for_pointer(data_ptr)
    if handle is None:
        return None
    shape = [int(v) for v in iface.get("shape", [])]
    typestr = str(iface.get("typestr", "|u1"))
    strides = iface.get("strides")
    if strides is not None:
        strides = [int(v) for v in strides]

    if nbytes is None:
        itemsize = 1
        try:
            import numpy as np
            itemsize = int(np.dtype(typestr).itemsize)
        except Exception:
            pass
        count = 1
        for dim in shape:
            count *= max(int(dim), 0)
        nbytes = count * itemsize

    return CudaIpcMetadata(
        topic=topic,
        field=field,
        token=token or uuid.uuid4().hex,
        handle_b64=base64.b64encode(handle).decode("ascii"),
        nbytes=int(nbytes),
        shape=shape,
        typestr=typestr,
        strides=strides,
        data_ptr=data_ptr,
        device_id=int(device_id if device_id is not None else _device_id_from_cupy()),
        owner_pid=os.getpid(),
        created_ns=time.time_ns(),
        sequence_number=int(sequence_number),
    )


def set_string_data(msg: Any, text: str) -> Any:
    setter = getattr(msg, "data", None)
    if callable(setter):
        setter(text)
    else:
        setattr(msg, "data", text)
    return msg


def get_string_data(msg: Any) -> str:
    value = getattr(msg, "data", "")
    if callable(value):
        value = value()
    return str(value)


__all__ = [
    "CudaIpcBuffer",
    "CudaIpcMetadata",
    "attach_cuda_buffer",
    "cuda_metadata_topic",
    "export_cuda_ipc_metadata",
    "get_cuda_buffer",
]
