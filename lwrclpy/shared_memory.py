"""Optional CPU shared-memory side channel for large local payloads."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import uuid
import ctypes
from dataclasses import asdict, dataclass
from multiprocessing import shared_memory
from typing import Any


_SHM_ATTR = "_lwrclpy_shared_memory_buffers"


# Names of segments this process created (owns).  Used to avoid unregistering
# the owner's resource-tracker entry when the same process also opens the
# segment as a reader (the tracker cache is a set, not a refcount).
_owned_shm_names: set[str] = set()
_owned_shm_names_lock = threading.Lock()


def _shared_memory_open(*, name: str | None = None, create: bool = False, size: int = 0, track: bool = True):
    try:
        shm = shared_memory.SharedMemory(name=name, create=create, size=size, track=track)
    except TypeError:
        # Python < 3.13 has no ``track`` parameter and always registers the
        # segment with the resource tracker.  A non-owning open must be
        # unregistered, otherwise this process unlinks the publisher-owned
        # segment when it exits.
        shm = shared_memory.SharedMemory(name=name, create=create, size=size)
        if not track and not create:
            skip = False
            with _owned_shm_names_lock:
                skip = shm._name in _owned_shm_names
            if not skip:
                try:
                    from multiprocessing import resource_tracker
                    resource_tracker.unregister(shm._name, "shared_memory")
                except Exception:
                    pass
    if create:
        with _owned_shm_names_lock:
            _owned_shm_names.add(shm._name)
    return shm


def _forget_owned_shm_name(shm) -> None:
    try:
        with _owned_shm_names_lock:
            _owned_shm_names.discard(shm._name)
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    """Return whether *pid* refers to a live process without signaling it."""
    if pid <= 0:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) calls TerminateProcess on Windows; never use it here.
        try:
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return True
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True
    return True


_host_id_cache: str | None = None


def local_host_id() -> str:
    """Return an identifier scoped to this machine and boot.

    The hostname alone can collide across containers that do not share
    /dev/shm; machine-id and boot-id disambiguate where available, and the
    boot-id also invalidates metadata files that survived a reboot.
    """
    global _host_id_cache
    if _host_id_cache is None:
        parts = [socket.gethostname()]
        for path in ("/etc/machine-id", "/proc/sys/kernel/random/boot_id"):
            try:
                with open(path, "r", encoding="ascii") as f:
                    value = f.read().strip()
                if value:
                    parts.append(value)
            except Exception:
                pass
        _host_id_cache = "-".join(parts)
    return _host_id_cache


def _sanitize_topic_name(topic_name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in topic_name).strip("_") or "root"


def shared_memory_metadata_topic(topic_name: str) -> str:
    """Return the hidden DDS topic name for CPU shared-memory metadata."""

    return f"rt/_lwrclpy/shm/{_sanitize_topic_name(topic_name)}"


@dataclass(slots=True)
class SharedMemoryMetadata:
    topic: str
    field: str
    token: str
    name: str
    nbytes: int
    owner_pid: int
    created_ns: int
    host_id: str = ""
    sequence_number: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "SharedMemoryMetadata":
        data = json.loads(text)
        return cls(
            topic=str(data["topic"]),
            field=str(data["field"]),
            token=str(data["token"]),
            name=str(data["name"]),
            nbytes=int(data["nbytes"]),
            owner_pid=int(data.get("owner_pid", 0)),
            created_ns=int(data.get("created_ns", 0)),
            host_id=str(data.get("host_id", "")),
            sequence_number=int(data.get("sequence_number", 0)),
        )


def _registration_dir(topic: str) -> str:
    return os.path.join(tempfile.gettempdir(), "lwrclpy_shm_subscribers", _sanitize_topic_name(topic))


def _metadata_dir(topic: str) -> str:
    return os.path.join(tempfile.gettempdir(), "lwrclpy_shm_metadata", _sanitize_topic_name(topic))


def write_latest_metadata(metadata: SharedMemoryMetadata) -> None:
    directory = _metadata_dir(metadata.topic)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{_sanitize_topic_name(metadata.field)}.json")
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(metadata.to_json())
    os.replace(tmp_path, path)


def read_latest_metadata(topic: str, field: str) -> SharedMemoryMetadata | None:
    path = os.path.join(_metadata_dir(topic), f"{_sanitize_topic_name(field)}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            metadata = SharedMemoryMetadata.from_json(f.read())
    except Exception:
        return None
    if metadata.topic != topic or metadata.field != field:
        return None
    if metadata.host_id and metadata.host_id != local_host_id():
        return None
    # Metadata files persist in tempdir across publisher restarts; a dead
    # owner means the shared-memory block is gone or about to be reused.
    if metadata.owner_pid and not _pid_alive(metadata.owner_pid):
        return None
    return metadata


class LocalSharedMemoryRegistration:
    __slots__ = ("path", "_closed", "_lock")

    def __init__(self, topic: str):
        directory = _registration_dir(topic)
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, f"{os.getpid()}-{uuid.uuid4().hex}")
        with open(self.path, "w", encoding="ascii") as f:
            f.write(local_host_id())
        self._closed = False
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def register_local_shared_memory_subscriber(topic: str) -> LocalSharedMemoryRegistration | None:
    try:
        return LocalSharedMemoryRegistration(topic)
    except Exception:
        return None


def count_local_shared_memory_subscribers(topic: str) -> int:
    directory = _registration_dir(topic)
    try:
        names = os.listdir(directory)
    except Exception:
        return 0
    count = 0
    for name in names:
        path = os.path.join(directory, name)
        try:
            pid = int(name.split("-", 1)[0])
        except Exception:
            try:
                os.unlink(path)
            except Exception:
                pass
            continue
        if not _pid_alive(pid):
            try:
                os.unlink(path)
            except Exception:
                pass
            continue
        count += 1
    return count


class SharedMemoryBuffer:
    """Subscriber-side shared-memory buffer descriptor."""

    __slots__ = ("metadata", "_shm", "_lock")

    def __init__(self, metadata: SharedMemoryMetadata):
        self.metadata = metadata
        self._shm: shared_memory.SharedMemory | None = None
        self._lock = threading.Lock()

    @property
    def nbytes(self) -> int:
        return self.metadata.nbytes

    @property
    def name(self) -> str:
        return self.metadata.name

    def open_memoryview(self) -> memoryview:
        """Open the shared-memory block and return a read/write memoryview."""

        with self._lock:
            if self._shm is None:
                self._shm = _shared_memory_open(name=self.metadata.name, create=False, track=False)
            return self._shm.buf[: self.metadata.nbytes]

    def tobytes(self) -> bytes:
        return bytes(self.open_memoryview())

    def close(self) -> None:
        with self._lock:
            shm = self._shm
            if shm is None:
                return
            try:
                shm.close()
            except BufferError:
                return
            self._shm = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class _SharedMemoryFieldProxy:
    """rclpy-style bytes-like view for a shared-memory-backed sequence field."""

    __slots__ = ("_buffer",)

    def __init__(self, buffer: SharedMemoryBuffer):
        self._buffer = buffer

    def __call__(self):
        return self

    def __len__(self) -> int:
        return self._buffer.nbytes

    @property
    def is_shared_memory(self) -> bool:
        return True

    @property
    def shared_memory_name(self) -> str:
        return self._buffer.name

    def __bool__(self) -> bool:
        return self._buffer.nbytes != 0

    def __getitem__(self, key):
        return self._buffer.open_memoryview()[key]

    def __iter__(self):
        return iter(self._buffer.open_memoryview())

    def __bytes__(self) -> bytes:
        return self._buffer.tobytes()

    def memoryview(self) -> memoryview:
        return self._buffer.open_memoryview()

    def tobytes(self) -> bytes:
        return self._buffer.tobytes()

    @property
    def __array_interface__(self) -> dict[str, object]:
        view = self._buffer.open_memoryview()
        ptr = ctypes.addressof(ctypes.c_uint8.from_buffer(view))
        return {
            "shape": (self._buffer.nbytes,),
            "typestr": "|u1",
            "data": (ptr, False),
            "version": 3,
        }

    def release(self) -> None:
        self._buffer.close()


class SharedMemoryAllocation:
    """Publisher-side allocation kept alive while subscribers may open it."""

    __slots__ = ("metadata", "_shm", "_closed", "_lock")

    def __init__(self, metadata: SharedMemoryMetadata, shm: shared_memory.SharedMemory):
        self.metadata = metadata
        self._shm = shm
        self._closed = False
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.metadata.name

    def close(self, *, unlink: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._shm.close()
        except Exception:
            pass
        if unlink:
            try:
                self._shm.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass
            _forget_owned_shm_name(self._shm)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def export_shared_memory_metadata(
    data: Any,
    *,
    topic: str,
    field: str = "data",
    token: str | None = None,
    sequence_number: int = 0,
) -> SharedMemoryAllocation | None:
    """Copy *data* into a shared-memory block and return metadata for it."""

    try:
        view = memoryview(data)
    except TypeError:
        try:
            view = memoryview(bytes(data))
        except Exception:
            return None
    if view.nbytes <= 0:
        return None
    if not view.contiguous:
        view = memoryview(view.tobytes())
    shm = _shared_memory_open(create=True, size=view.nbytes, track=True)
    try:
        shm.buf[: view.nbytes] = view.cast("B")
    except Exception:
        try:
            shm.close()
            shm.unlink()
        except Exception:
            pass
        raise
    metadata = SharedMemoryMetadata(
        topic=topic,
        field=field,
        token=token or uuid.uuid4().hex,
        name=shm.name,
        nbytes=int(view.nbytes),
        owner_pid=os.getpid(),
        created_ns=time.time_ns(),
        host_id=local_host_id(),
        sequence_number=int(sequence_number),
    )
    return SharedMemoryAllocation(metadata, shm)


def attach_shared_memory_buffer(msg: Any, metadata: SharedMemoryMetadata) -> bool:
    buffers = getattr(msg, _SHM_ATTR, None)
    if buffers is None:
        buffers = {}
        for setter in (setattr, object.__setattr__):
            try:
                setter(msg, _SHM_ATTR, buffers)
                break
            except Exception:
                continue
        else:
            return False
    buffer = SharedMemoryBuffer(metadata)
    buffers[metadata.field] = buffer
    try:
        view = buffer.open_memoryview()
    except Exception:
        view = None
    if view is not None:
        try:
            from .message_utils import _shadow_attr
            proxy = _SharedMemoryFieldProxy(buffer)
            _shadow_attr(msg, metadata.field, proxy)
            _shadow_attr(msg, f"_lwrclpy_{metadata.field}_memoryview", proxy.memoryview)
            _shadow_attr(msg, f"_lwrclpy_{metadata.field}_bytes", proxy.tobytes)
            _shadow_attr(msg, f"_lwrclpy_{metadata.field}_nbytes", lambda: buffer.nbytes)
            _shadow_attr(msg, f"_lwrclpy_{metadata.field}_size", lambda: buffer.nbytes)
        except Exception:
            pass
    return True


def get_shared_memory_buffer(msg: Any, field: str = "data") -> SharedMemoryBuffer | None:
    buffers = getattr(msg, _SHM_ATTR, None)
    if not isinstance(buffers, dict):
        return None
    value = buffers.get(field)
    return value if isinstance(value, SharedMemoryBuffer) else None


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
    "SharedMemoryAllocation",
    "SharedMemoryBuffer",
    "SharedMemoryMetadata",
    "attach_shared_memory_buffer",
    "export_shared_memory_metadata",
    "get_shared_memory_buffer",
    "read_latest_metadata",
    "write_latest_metadata",
    "shared_memory_metadata_topic",
]
