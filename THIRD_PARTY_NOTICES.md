# Third-Party Notices

This repository includes compatibility code and APIs derived from or modeled
after the ROS 2 ecosystem.

## ROS 2 rclpy

The `rclpy` package in this repository is a compatibility shim that exposes
ROS 2 rclpy-style module names and APIs while delegating implementation to
`lwrclpy`.  It is modeled after the public API surface of ROS 2 `rclpy`.

The upstream ROS 2 `rclpy` project is licensed under Apache License 2.0.  A
copy of the Apache License 2.0 text is retained at `rclpy/LICENSE`.

Upstream repository: https://github.com/ros2/rclpy

## ROS 2 geometry2: tf2_py / tf2_ros_py

The `tf2_py` and `tf2_ros` compatibility packages are derived from and
compatible with the Python APIs in `ros2/geometry2` (`tf2_py` and
`tf2_ros_py`).  The upstream project declares these packages under the BSD
license.

Copyright notices retained from upstream source files:

- Copyright (c) 2008 Willow Garage, Inc. All rights reserved.
- Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
- Copyright (c) 2024 Open Source Robotics Foundation, Inc. All rights reserved.

BSD license text:

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

- Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.
- Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.
- Neither the name of the copyright holder nor the names of its contributors
  may be used to endorse or promote products derived from this software without
  specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Upstream repository: https://github.com/ros2/geometry2
