# Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
# Copyright (c) Open Source Robotics Foundation, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# See LICENSE in this package and THIRD_PARTY_NOTICES.md for details.

"""Pure-Python subset of geometry2's ``tf2_py`` API for lwrclpy.

The upstream ROS 2 package exposes a C++ ``BufferCore`` binding.  lwrclpy
ships this Python implementation so ``tf2_ros`` can be used from wheels that
do not include that extra extension module.
"""

from __future__ import annotations

from collections import deque
import math
import threading
from typing import Any

from geometry_msgs.msg import TransformStamped


class TransformException(Exception):
    pass


class LookupException(TransformException):
    pass


class ConnectivityException(TransformException):
    pass


class ExtrapolationException(TransformException):
    pass


class InvalidArgumentException(TransformException):
    pass


class TimeoutException(TransformException):
    pass


def _frame_id(frame: str) -> str:
    frame = str(frame or "")
    return frame[1:] if frame.startswith("/") else frame


def _get_value(obj, name: str, default=None):
    if obj is None:
        return default
    val = getattr(obj, name, default)
    if callable(val):
        try:
            return val()
        except TypeError:
            return val
    return val


def _assign(obj, name: str, value) -> bool:
    if obj is None:
        return False
    attr = getattr(obj, name, None)
    if callable(attr):
        try:
            attr(value)
            return True
        except TypeError:
            pass
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def _time_ns(value: Any) -> int:
    if value is None:
        return 0
    nanoseconds = getattr(value, "nanoseconds", None)
    if nanoseconds is not None:
        try:
            return int(nanoseconds)
        except Exception:
            pass
    sec = _get_value(value, "sec")
    nanosec = _get_value(value, "nanosec")
    try:
        return int(sec or 0) * 1_000_000_000 + int(nanosec or 0)
    except Exception:
        return 0


def _stamp_msg(ns: int):
    try:
        from builtin_interfaces.msg import Time
    except Exception:
        return None
    msg = Time()
    _assign(msg, "sec", int(ns // 1_000_000_000))
    _assign(msg, "nanosec", int(ns % 1_000_000_000))
    return msg


def _xyz(value: Any) -> tuple[float, float, float]:
    return (
        float(_get_value(value, "x") or 0.0),
        float(_get_value(value, "y") or 0.0),
        float(_get_value(value, "z") or 0.0),
    )


def _quat(value: Any) -> tuple[float, float, float, float]:
    q = (
        float(_get_value(value, "x") or 0.0),
        float(_get_value(value, "y") or 0.0),
        float(_get_value(value, "z") or 0.0),
        float(_get_value(value, "w") if _get_value(value, "w") is not None else 1.0),
    )
    norm = math.sqrt(sum(part * part for part in q))
    if norm <= 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(part / norm for part in q)


def _quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_conj(q):
    x, y, z, w = q
    return (-x, -y, -z, w)


def _rotate(q, v):
    x, y, z, _w = _quat_mul(_quat_mul(q, (v[0], v[1], v[2], 0.0)), _quat_conj(q))
    return (x, y, z)


def _compose(a, b):
    """Compose transforms so result maps through b then a."""
    at, aq, _atime = a
    bt, bq, btime = b
    rb = _rotate(aq, bt)
    return (
        (at[0] + rb[0], at[1] + rb[1], at[2] + rb[2]),
        _quat_mul(aq, bq),
        btime,
    )


def _inverse(t):
    trans, quat, stamp = t
    iq = _quat_conj(quat)
    rt = _rotate(iq, (-trans[0], -trans[1], -trans[2]))
    return (rt, iq, stamp)


def _identity(stamp_ns: int = 0):
    return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), stamp_ns)


def _read_transform_msg(msg: TransformStamped):
    header = _get_value(msg, "header")
    parent = _frame_id(_get_value(header, "frame_id") if header is not None else "")
    child = _frame_id(_get_value(msg, "child_frame_id"))
    transform = _get_value(msg, "transform")
    translation = _get_value(transform, "translation")
    rotation = _get_value(transform, "rotation")
    stamp = _time_ns(_get_value(header, "stamp") if header is not None else None)
    return parent, child, (_xyz(translation), _quat(rotation), stamp)


def _write_transform_msg(target: str, source: str, transform):
    msg = TransformStamped()
    header = _get_value(msg, "header")
    if header is not None:
        _assign(header, "frame_id", target)
        stamp = _stamp_msg(transform[2])
        if stamp is not None:
            _assign(header, "stamp", stamp)
    _assign(msg, "child_frame_id", source)
    transform_msg = _get_value(msg, "transform")
    translation = _get_value(transform_msg, "translation")
    rotation = _get_value(transform_msg, "rotation")
    for name, value in zip(("x", "y", "z"), transform[0]):
        _assign(translation, name, float(value))
    for name, value in zip(("x", "y", "z", "w"), transform[1]):
        _assign(rotation, name, float(value))
    return msg


class BufferCore:
    """Small, latest-sample TF buffer compatible with the common tf2_py API."""

    def __init__(self, cache_time=None):
        self.cache_time = cache_time
        self._dynamic: dict[tuple[str, str], tuple[tuple, str]] = {}
        self._static: dict[tuple[str, str], tuple[tuple, str]] = {}
        self._lock = threading.RLock()

    def clear(self):
        with self._lock:
            self._dynamic.clear()

    def set_transform(self, transform: TransformStamped, authority: str):
        self._set(transform, authority, is_static=False)

    def set_transform_static(self, transform: TransformStamped, authority: str):
        self._set(transform, authority, is_static=True)

    def _set(self, transform: TransformStamped, authority: str, *, is_static: bool):
        parent, child, value = _read_transform_msg(transform)
        if not parent:
            raise InvalidArgumentException("Transform has an empty parent frame id")
        if not child:
            raise InvalidArgumentException("Transform has an empty child frame id")
        if parent == child:
            raise InvalidArgumentException("Transform parent and child frames are identical")
        with self._lock:
            target = self._static if is_static else self._dynamic
            target[(parent, child)] = (value, authority or "")

    def can_transform_core(self, target_frame: str, source_frame: str, time):
        try:
            self.lookup_transform_core(target_frame, source_frame, time)
            return (True, "", 0)
        except TransformException as exc:
            return (False, str(exc), 0)

    def can_transform_full_core(self, target_frame, target_time, source_frame, source_time, fixed_frame):
        return self.can_transform_core(target_frame, source_frame, source_time)

    def lookup_transform_core(self, target_frame: str, source_frame: str, time):
        target = _frame_id(target_frame)
        source = _frame_id(source_frame)
        if not target or not source:
            raise InvalidArgumentException("target_frame and source_frame must be non-empty")
        if target == source:
            return _write_transform_msg(target, source, _identity(_time_ns(time)))
        with self._lock:
            result = self._find_path_transform(source, target)
        if result is None:
            raise LookupException(f'Could not transform from "{source}" to "{target}"')
        return _write_transform_msg(target, source, result)

    def lookup_transform_full_core(self, target_frame, target_time, source_frame, source_time, fixed_frame):
        del target_time, fixed_frame
        return self.lookup_transform_core(target_frame, source_frame, source_time)

    def _all_edges(self):
        merged = dict(self._dynamic)
        merged.update(self._static)
        return merged

    def _find_path_transform(self, source: str, target: str):
        edges = self._all_edges()
        graph: dict[str, list[tuple[str, tuple]]] = {}
        for (parent, child), (transform, _authority) in edges.items():
            graph.setdefault(child, []).append((parent, transform))
            graph.setdefault(parent, []).append((child, _inverse(transform)))

        queue = deque([(source, _identity())])
        seen = {source}
        while queue:
            frame, accumulated = queue.popleft()
            for neighbor, step in graph.get(frame, ()):
                if neighbor in seen:
                    continue
                combined = _compose(step, accumulated)
                if neighbor == target:
                    return combined
                seen.add(neighbor)
                queue.append((neighbor, combined))
        return None

    def all_frames_as_yaml(self) -> str:
        with self._lock:
            edges = self._all_edges()
            lines = []
            for (parent, child), (_transform, authority) in sorted(edges.items()):
                lines.append(f"{child}:")
                lines.append(f"  parent: {parent}")
                lines.append(f"  authority: {authority}")
            return "\n".join(lines)

    def all_frames_as_string(self) -> str:
        return self.all_frames_as_yaml()


__all__ = [
    "BufferCore",
    "TransformException",
    "LookupException",
    "ConnectivityException",
    "ExtrapolationException",
    "InvalidArgumentException",
    "TimeoutException",
]
