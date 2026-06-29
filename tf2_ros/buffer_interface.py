# Copyright (c) 2008 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2024 Open Source Robotics Foundation, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# See LICENSE in this package and THIRD_PARTY_NOTICES.md for details.

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Optional, Tuple, TypeVar, Union

from geometry_msgs.msg import PointStamped, PoseStamped, PoseWithCovarianceStamped
from geometry_msgs.msg import TransformStamped, Vector3Stamped
from rclpy.duration import Duration
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import Header

MsgStamped = Union[PointStamped, PoseStamped, PoseWithCovarianceStamped, Vector3Stamped, PointCloud2]
TransformableObject = Union[MsgStamped, Any]
TransformableObjectType = TypeVar("TransformableObjectType")


class TypeException(Exception):
    def __init__(self, errstr: str) -> None:
        self.errstr = errstr
        super().__init__(errstr)


class NotImplementedException(Exception):
    def __init__(self) -> None:
        self.errstr = "CanTransform or LookupTransform not implemented"
        super().__init__(self.errstr)


class TransformRegistration:
    __type_map = {}

    def add(self, key: TransformableObjectType, callback: Callable[[Any, TransformStamped], Any]) -> None:
        TransformRegistration.__type_map[key] = callback

    def get(self, key: TransformableObjectType) -> Callable[[Any, TransformStamped], Any]:
        if key not in TransformRegistration.__type_map:
            raise TypeException("Type %s is not loaded or supported" % str(key))
        return TransformRegistration.__type_map[key]

    def print_me(self) -> None:
        print(TransformRegistration.__type_map)


class ConvertRegistration:
    __to_msg_map = {}
    __from_msg_map = {}
    __convert_map = {}

    def add_from_msg(self, key: TransformableObjectType, callback: Callable[[MsgStamped], Any]) -> None:
        ConvertRegistration.__from_msg_map[key] = callback

    def add_to_msg(self, key: TransformableObjectType, callback: Callable[[Any], MsgStamped]) -> None:
        ConvertRegistration.__to_msg_map[key] = callback

    def add_convert(self, key: Tuple[TransformableObjectType, TransformableObjectType], callback: Callable[[Any], Any]) -> None:
        ConvertRegistration.__convert_map[key] = callback

    def get_from_msg(self, key: TransformableObjectType) -> Callable[[MsgStamped], Any]:
        if key not in ConvertRegistration.__from_msg_map:
            raise TypeException("Type %s is not loaded or supported" % str(key))
        return ConvertRegistration.__from_msg_map[key]

    def get_to_msg(self, key: TransformableObjectType) -> Callable[[Any], MsgStamped]:
        if key not in ConvertRegistration.__to_msg_map:
            raise TypeException("Type %s is not loaded or supported" % str(key))
        return ConvertRegistration.__to_msg_map[key]

    def get_convert(self, key: Tuple[TransformableObjectType, TransformableObjectType]) -> Callable[[Any], Any]:
        if key not in ConvertRegistration.__convert_map:
            raise TypeException("Type %s is not loaded or supported" % str(key))
        return ConvertRegistration.__convert_map[key]


def convert(a: TransformableObject, b_type: TransformableObjectType) -> TransformableObject:
    c = ConvertRegistration()
    try:
        return c.get_convert((type(a), b_type))(a)
    except TypeException:
        if isinstance(a, b_type):
            return deepcopy(a)
        return c.get_from_msg(b_type)(c.get_to_msg(type(a))(a))


def Stamped(obj: TransformableObject, stamp: Time, frame_id: str) -> TransformableObject:
    obj.header = Header(frame_id=frame_id, stamp=stamp)
    return obj


class BufferInterface:
    def __init__(self) -> None:
        self.registration = TransformRegistration()

    def transform(self, object_stamped: TransformableObject, target_frame: str, timeout: Duration = Duration(), new_type: Optional[TransformableObjectType] = None) -> TransformableObject:
        do_transform = self.registration.get(type(object_stamped))
        res = do_transform(
            object_stamped,
            self.lookup_transform(target_frame, object_stamped.header.frame_id, object_stamped.header.stamp, timeout),
        )
        return res if new_type is None else convert(res, new_type)

    def transform_full(self, object_stamped: TransformableObject, target_frame: str, target_time: Time, fixed_frame: str, timeout: Duration = Duration(), new_type: Optional[TransformableObjectType] = None) -> TransformableObject:
        do_transform = self.registration.get(type(object_stamped))
        res = do_transform(
            object_stamped,
            self.lookup_transform_full(
                target_frame,
                target_time,
                object_stamped.header.frame_id,
                object_stamped.header.stamp,
                fixed_frame,
                timeout,
            ),
        )
        return res if new_type is None else convert(res, new_type)

    def lookup_transform(self, target_frame: str, source_frame: str, time: Time, timeout: Duration = Duration()) -> TransformStamped:
        raise NotImplementedException()

    def lookup_transform_full(self, target_frame: str, target_time: Time, source_frame: str, source_time: Time, fixed_frame: str, timeout: Duration = Duration()) -> TransformStamped:
        raise NotImplementedException()

    def can_transform(self, target_frame: str, source_frame: str, time: Time, timeout: Duration = Duration()) -> bool:
        raise NotImplementedException()

    def can_transform_full(self, target_frame: str, target_time: Time, source_frame: str, source_time: Time, fixed_frame: str, timeout: Duration = Duration()) -> bool:
        raise NotImplementedException()
