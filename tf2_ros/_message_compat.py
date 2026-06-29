# Copyright (c) 2008 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2024 Open Source Robotics Foundation, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# See LICENSE in this package and THIRD_PARTY_NOTICES.md for details.

from __future__ import annotations

import inspect


_PATCHED = "__tf2_ros_property_compat__"
_TF_FIELD_NAMES = {
    "header",
    "stamp",
    "sec",
    "nanosec",
    "frame_id",
    "child_frame_id",
    "transform",
    "translation",
    "rotation",
    "x",
    "y",
    "z",
    "w",
    "transforms",
}


def _make_property(name, getter):
    def fget(self):
        value = getter(self)
        if not isinstance(value, (str, int, float, bool, bytes, bytearray, memoryview, list, tuple, dict, set, type(None))):
            try:
                patch_message_class(value.__class__)
            except Exception:
                pass
            if name == "transforms":
                try:
                    for item in value:
                        patch_message_class(item.__class__)
                except Exception:
                    pass
        return value

    def fset(self, value):
        return getter(self, value)

    return property(fget, fset)


def patch_message_class(cls) -> None:
    if getattr(cls, _PATCHED, False):
        return
    try:
        inst = cls()
    except Exception:
        return
    fields = []
    for name in _TF_FIELD_NAMES:
        try:
            attr = getattr(inst, name)
        except Exception:
            continue
        if not callable(attr):
            continue
        try:
            sig = inspect.signature(attr)
            required = [
                p for p in sig.parameters.values()
                if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            if len(required) > 1:
                continue
        except Exception:
            pass
        try:
            attr()
        except TypeError:
            continue
        except Exception:
            continue
        fields.append((name, attr))
    for name, _sample_getter in fields:
        try:
            original = getattr(cls, name)
            if isinstance(original, property):
                continue
            setattr(cls, name, _make_property(name, original))
        except Exception:
            continue
    try:
        setattr(cls, _PATCHED, True)
    except Exception:
        pass


def patch_tf_message_modules() -> None:
    for mod_name in (
        "builtin_interfaces.msg",
        "std_msgs.msg",
        "geometry_msgs.msg",
        "tf2_msgs.msg",
    ):
        try:
            module = __import__(mod_name, fromlist=["msg"])
        except Exception:
            continue
        for name in dir(module):
            try:
                obj = getattr(module, name)
            except Exception:
                continue
            if isinstance(obj, type):
                patch_message_class(obj)
