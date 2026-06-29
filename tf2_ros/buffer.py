# Copyright (c) 2008 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2024 Open Source Robotics Foundation, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# See LICENSE in this package and THIRD_PARTY_NOTICES.md for details.

from __future__ import annotations

import threading
from time import sleep
from typing import Callable, List, Optional

from geometry_msgs.msg import TransformStamped
from lwrclpy.message_utils import _assign
from rclpy.clock import Clock
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.task import Future
from rclpy.time import Time
from tf2_msgs.srv import FrameGraph
import tf2_py as tf2

from .buffer_interface import BufferInterface


class Buffer(tf2.BufferCore, BufferInterface):
    def __init__(self, cache_time: Optional[Duration] = None, node: Optional[Node] = None) -> None:
        tf2.BufferCore.__init__(self, cache_time) if cache_time is not None else tf2.BufferCore.__init__(self)
        BufferInterface.__init__(self)
        self._new_data_callbacks: List[Callable[[], None]] = []
        self._callbacks_to_remove: List[Callable[[], None]] = []
        self._callbacks_lock = threading.RLock()
        self.clock = node.get_clock() if node is not None else Clock()
        if node is not None:
            self.srv = node.create_service(FrameGraph, "tf2_frames", self.__get_frames)

    def __get_frames(self, req, res):
        del req
        frame_yaml = self.all_frames_as_yaml()
        if _assign(res, "frame_yaml", frame_yaml):
            return res
        response = FrameGraph.Response()
        _assign(response, "frame_yaml", frame_yaml)
        return response

    def set_transform(self, transform: TransformStamped, authority: str) -> None:
        super().set_transform(transform, authority)
        self._call_new_data_callbacks()

    def set_transform_static(self, transform: TransformStamped, authority: str) -> None:
        super().set_transform_static(transform, authority)
        self._call_new_data_callbacks()

    def _call_new_data_callbacks(self) -> None:
        with self._callbacks_lock:
            for callback in list(self._new_data_callbacks):
                callback()
            for callback in self._callbacks_to_remove:
                if callback in self._new_data_callbacks:
                    self._new_data_callbacks.remove(callback)
            self._callbacks_to_remove.clear()

    def _remove_callback(self, callback: Callable[[], None]) -> None:
        with self._callbacks_lock:
            self._callbacks_to_remove.append(callback)

    def lookup_transform(self, target_frame: str, source_frame: str, time: Time, timeout: Duration = Duration()) -> TransformStamped:
        self.can_transform(target_frame, source_frame, time, timeout)
        return self.lookup_transform_core(target_frame, source_frame, time)

    async def lookup_transform_async(self, target_frame: str, source_frame: str, time: Time) -> TransformStamped:
        await self.wait_for_transform_async(target_frame, source_frame, time)
        return self.lookup_transform_core(target_frame, source_frame, time)

    def lookup_transform_full(self, target_frame: str, target_time: Time, source_frame: str, source_time: Time, fixed_frame: str, timeout: Duration = Duration()) -> TransformStamped:
        self.can_transform_full(target_frame, target_time, source_frame, source_time, fixed_frame, timeout)
        return self.lookup_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame)

    async def lookup_transform_full_async(self, target_frame: str, target_time: Time, source_frame: str, source_time: Time, fixed_frame: str) -> TransformStamped:
        await self.wait_for_transform_full_async(target_frame, target_time, source_frame, source_time, fixed_frame)
        return self.lookup_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame)

    def can_transform(self, target_frame: str, source_frame: str, time: Time, timeout: Duration = Duration(), return_debug_tuple: bool = False):
        if timeout != Duration():
            start_time = self.clock.now()
            while self.clock.now() < start_time + timeout and not self.can_transform_core(target_frame, source_frame, time)[0]:
                sleep(0.02)
        result = self.can_transform_core(target_frame, source_frame, time)
        return result if return_debug_tuple else result[0]

    def can_transform_full(self, target_frame: str, target_time: Time, source_frame: str, source_time: Time, fixed_frame: str, timeout: Duration = Duration(), return_debug_tuple: bool = False):
        if timeout != Duration():
            start_time = self.clock.now()
            while self.clock.now() < start_time + timeout and not self.can_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame)[0]:
                sleep(0.02)
        result = self.can_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame)
        return result if return_debug_tuple else result[0]

    def wait_for_transform_async(self, target_frame: str, source_frame: str, time: Time) -> Future:
        fut = Future()
        if self.can_transform_core(target_frame, source_frame, time)[0]:
            fut.set_result(self.lookup_transform(target_frame, source_frame, time))
            return fut

        def _on_new_data():
            try:
                if self.can_transform_core(target_frame, source_frame, time)[0]:
                    fut.set_result(self.lookup_transform(target_frame, source_frame, time))
            except BaseException as exc:
                fut.set_exception(exc)

        self._new_data_callbacks.append(_on_new_data)
        fut.add_done_callback(lambda _: self._remove_callback(_on_new_data))
        return fut

    def wait_for_transform_full_async(self, target_frame: str, target_time: Time, source_frame: str, source_time: Time, fixed_frame: str) -> Future:
        fut = Future()
        if self.can_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame)[0]:
            fut.set_result(self.lookup_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame))
            return fut

        def _on_new_data():
            try:
                if self.can_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame)[0]:
                    fut.set_result(self.lookup_transform_full_core(target_frame, target_time, source_frame, source_time, fixed_frame))
            except BaseException as exc:
                fut.set_exception(exc)

        self._new_data_callbacks.append(_on_new_data)
        fut.add_done_callback(lambda _: self._remove_callback(_on_new_data))
        return fut
