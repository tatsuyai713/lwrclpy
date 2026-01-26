# lwrclpy — rclpy-Compatible API Without ROS 2 (Fast DDS v3)

[![CI](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/ci.yml/badge.svg)](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/ci.yml)
[![Test Ubuntu](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/test-ubuntu.yml/badge.svg)](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/test-ubuntu.yml)
[![Test macOS](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/test-macos.yml/badge.svg)](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/test-macos.yml)
[![Build Ubuntu](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/build-ubuntu.yml/badge.svg)](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/build-ubuntu.yml)
[![Build macOS](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/build-macos.yml/badge.svg)](https://github.com/tatsuyai713/lwrclpy-for-FastDDSv3/actions/workflows/build-macos.yml)

[日本語](README.md)

**lwrclpy** (Lightweight rclpy) is an rclpy-compatible Python library built directly on Fast DDS v3. Develop robot applications using the same rclpy API without installing ROS 2.

---

## 🎯 What is lwrclpy?

lwrclpy reimplements the "rclpy" API (ROS 2's Python client library) on top of Fast DDS v3. You can use the familiar rclpy API while avoiding ROS 2's complex build system and dependencies.

### 💡 When to Use lwrclpy

- **Develop ROS 2 apps on macOS** — ROS 2 doesn't officially support macOS
- **Avoid full ROS 2 installation** — Single pip package, minimal dependencies
- **Port existing rclpy code** — API-compatible, minimal code changes needed
- **Lightweight robot communication** — Only Python and Fast DDS required
- **Interoperate with ROS 2 nodes** — Works on the same DDS/RTPS network

---

## 📊 Comparison with rclpy

### Feature Comparison

| Feature | lwrclpy | rclpy (ROS 2) | Notes |
|---------|---------|---------------|-------|
| **Installation** | `pip install` only | Full ROS 2 install required | lwrclpy has fewer dependencies |
| **macOS Support** | ✅ Full support | ⚠️ Unofficial/difficult | lwrclpy supports Apple Silicon |
| **Ubuntu/Linux Support** | ✅ Full support | ✅ Full support | Both work fine |
| **Windows Support** | 🚧 In development | ✅ Supported | - |
| **ROS 2 Interop** | ✅ Via DDS | - | Same domain ID connects |
| **Publisher/Subscriber** | ✅ | ✅ | API compatible |
| **Service Server/Client** | ✅ | ✅ | API compatible |
| **Action Server/Client** | ✅ | ✅ | API compatible |
| **Timer** | ✅ | ✅ | OneShot/Periodic supported |
| **Parameters** | ✅ | ✅ | Basic features supported |
| **Executor** | ✅ | ✅ | Single/MultiThreaded supported |
| **Callback Groups** | ✅ | ✅ | MutuallyExclusive/Reentrant |
| **Guard Conditions** | ✅ | ✅ | Thread synchronization |
| **QoS Profiles** | ✅ | ✅ | Major policies supported |
| **Zero-Copy Communication** | ✅ DataSharing/SHM | ✅ | `loan_message()` supported |
| **Clock/Time/Duration** | ✅ | ✅ | ROS Time/Sim Time supported |
| **Logging** | ✅ | ✅ | Levels/throttling supported |
| **Context/Domain ID** | ✅ | ✅ | Multiple contexts supported |
| **Launch System** | ✅ | ✅ | launch/launch_ros API compatible |
| **Lifecycle Nodes** | ❌ Not supported | ✅ | Planned for future |
| **Component Nodes** | ❌ Not supported | ✅ | Planned for future |
| **ros2 CLI** | ❌ Not needed | ✅ | lwrclpy doesn't require CLI |

### Performance Characteristics

| Metric | lwrclpy | rclpy | Notes |
|--------|---------|-------|-------|
| **Startup Time** | ⚡ Fast | 🐢 Slower | No ROS 2 middleware layer |
| **Memory Usage** | 📉 Low | 📈 Higher | Minimal dependencies |
| **Zero-Copy** | ✅ Fast DDS DataSharing | ✅ Via rmw | Effective for large messages |
| **Latency** | ⚡ Low | ⚡ Low | Same (same DDS foundation) |

### Tested Environments

| OS | Version | Python | Status |
|----|---------|--------|--------|
| **Ubuntu** | 24.04 LTS | 3.12 | ✅ Full support |
| **macOS** | Sonoma 14+ | 3.11 | ✅ Full support (Apple Silicon) |

---

## 📦 Quick Start

### With Pre-built Wheel

```bash
# 1) Create and activate venv (recommended)
python3 -m venv venv
source venv/bin/activate

# 2) Install the wheel
pip install dist/lwrclpy-*.whl

# 3) Run examples (in two terminals)
# Terminal A (receiver)
python3 examples/pubsub/string/listener.py

# Terminal B (sender)
python3 examples/pubsub/string/talker.py
```

### Verify Installation

```bash
python3 -c "
import rclpy
from std_msgs.msg import String

rclpy.init()
node = rclpy.create_node('test_node')
print('✅ lwrclpy is working!')
print(f'Node name: {node.get_name()}')
node.destroy_node()
rclpy.shutdown()
"
```

---

## 🔧 Build Instructions

### Ubuntu

```bash
# 1) Fetch submodules
git submodule update --init --recursive

# 2) Install Fast DDS v3 toolchain
bash scripts/install_fastdds_v3_colcon.sh

# 3) Create venv
python3 -m venv venv
source venv/bin/activate
pip install setuptools

# 4) Generate and install ROS DataTypes
bash scripts/install_ros_data_types.sh

# 5) Build runtime-bundled wheel
bash scripts/make_pip_package_with_runtime.sh

# 6) Install
pip install dist/lwrclpy-*.whl
```

### macOS (Apple Silicon / Intel)

```bash
# 1) Install dependencies via Homebrew
brew install cmake ninja git pkg-config tinyxml2 wget curl swig gradle openssl@3 python@3.11

# 2) Fetch submodules
git submodule update --init --recursive

# 3) Build Fast DDS v3
bash scripts/mac/mac_install_fastdds_v3_colcon.sh

# 4) Create venv
python3 -m venv venv
source venv/bin/activate
pip install setuptools

# 5) Generate and install ROS DataTypes
bash scripts/mac/mac_install_ros_data_types.sh

# 6) Build runtime-bundled wheel
bash scripts/mac/mac_make_pip_package_with_runtime.sh

# 7) Install
pip install dist/lwrclpy-*-macosx*.whl
```

---

## 📚 Basic Usage

### Publisher / Subscriber

```python
#!/usr/bin/env python3
import rclpy
from std_msgs.msg import String

# Initialize
rclpy.init()
node = rclpy.create_node('example_node')

# Create publisher
pub = node.create_publisher(String, 'chatter', 10)

# Create subscriber
def callback(msg):
    print(f'Received: {msg.data}')

sub = node.create_subscription(String, 'chatter', callback, 10)

# Publish message
msg = String()
msg.data = 'Hello, lwrclpy!'
pub.publish(msg)

# Spin (process callbacks)
rclpy.spin(node)

# Cleanup
node.destroy_node()
rclpy.shutdown()
```

### Service Server / Client

```python
#!/usr/bin/env python3
import rclpy
from std_srvs.srv import SetBool

rclpy.init()
node = rclpy.create_node('service_example')

# Service server
def handle_service(request, response):
    response.success = request.data
    response.message = 'OK' if request.data else 'NG'
    return response

server = node.create_service(SetBool, 'set_bool', handle_service)

# Service client
client = node.create_client(SetBool, 'set_bool')
client.wait_for_service()

request = SetBool.Request()
request.data = True
future = client.call_async(request)

rclpy.spin_until_future_complete(node, future)
print(f'Result: {future.result().message}')

node.destroy_node()
rclpy.shutdown()
```

### Timer

```python
#!/usr/bin/env python3
import rclpy

rclpy.init()
node = rclpy.create_node('timer_example')

count = 0

def timer_callback():
    global count
    count += 1
    print(f'Timer fired: {count} times')

# 1-second periodic timer
timer = node.create_timer(1.0, timer_callback)

rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
```

### Action Server / Client

```python
#!/usr/bin/env python3
import rclpy
from rclpy.action import ActionClient
from action_tutorials_interfaces.action import Fibonacci

rclpy.init()
node = rclpy.create_node('action_example')

# Action client
action_client = ActionClient(node, Fibonacci, 'fibonacci')
action_client.wait_for_server()

# Send goal
goal = Fibonacci.Goal()
goal.order = 10

future = action_client.send_goal_async(goal)
rclpy.spin_until_future_complete(node, future)

goal_handle = future.result()
result_future = goal_handle.get_result_async()
rclpy.spin_until_future_complete(node, result_future)

print(f'Result: {result_future.result().result.sequence}')

node.destroy_node()
rclpy.shutdown()
```

---

## 🚀 Advanced Features

### Zero-Copy Communication (loan_message)

Efficiently send large messages (images, point clouds, etc.):

```python
# Send message with zero-copy
with publisher.loan_message() as loaned_msg:
    loaned_msg.data = large_data
    # Auto-published on context exit
```

### QoS Profiles

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

# Custom QoS
qos = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL
)

pub = node.create_publisher(String, 'topic', qos)
```

### Multi-Threaded Executor

```python
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

# Callback group
group = MutuallyExclusiveCallbackGroup()

# Assign group to timer
timer = node.create_timer(1.0, callback, callback_group=group)

# Multi-threaded execution
executor = MultiThreadedExecutor(num_threads=4)
executor.add_node(node)
executor.spin()
```

### Context and Domain ID

```python
from rclpy.context import Context

# Create context with custom Domain ID
context = Context()
rclpy.init(context=context, domain_id=42)

node = rclpy.create_node('isolated_node', context=context)
```

### Launch System

Use the same Launch API as ROS 2 to start multiple processes and nodes.

```python
#!/usr/bin/env python3
# my_launch.py
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Declare arguments
        DeclareLaunchArgument('verbose', default_value='true'),
        
        # Conditional log output
        LogInfo(
            condition=IfCondition(LaunchConfiguration('verbose')),
            msg='Starting application...'
        ),
        
        # Launch publisher node
        Node(
            executable='examples/pubsub/string/talker.py',
            name='talker',
            parameters=[{'rate': 1.0}],
        ),
        
        # Launch subscriber node
        Node(
            executable='examples/pubsub/string/listener.py',
            name='listener',
        ),
    ])

if __name__ == '__main__':
    from launch import LaunchService
    ls = LaunchService()
    ls.include_launch_description(generate_launch_description())
    ls.run()
```

**Running:**
```bash
# Basic execution
python3 my_launch.py

# With arguments
python3 my_launch.py verbose:=false
```

---

## 🔗 ROS 2 Interoperability

lwrclpy nodes communicate with ROS 2 nodes on the same DDS/RTPS network.

### Configuration

```bash
# Match Domain IDs
export ROS_DOMAIN_ID=0      # ROS 2 side
export LWRCL_DOMAIN_ID=0    # lwrclpy side
```

### Communication Example

```bash
# Terminal A: ROS 2 listener
ros2 run demo_nodes_cpp listener

# Terminal B: lwrclpy talker
python3 examples/pubsub/string/talker.py
```

### Notes

- **Topic name/type**: Must match exactly
- **QoS**: Use compatible settings (especially Reliability/Durability)
- **Discovery time**: DDS discovery may take a few seconds

---

## 📖 Examples

See [examples/README.md](examples/README.md) for details.

| Category | Example | Description |
|----------|---------|-------------|
| **Pub/Sub** | `pubsub/string/` | Basic string messages |
| **Pub/Sub** | `pubsub/typed_messages/` | Various ROS message types |
| **Pub/Sub** | `pubsub/zero_copy/` | Zero-copy communication |
| **Service** | `services/set_bool/` | SetBool service |
| **Service** | `services/trigger/` | Trigger service |
| **Action** | `actions/` | Fibonacci action |
| **Timer** | `timers/` | Periodic/OneShot timers |
| **Executor** | `executor/` | Single/MultiThreaded |
| **QoS** | `qos/` | Various QoS profiles |
| **Parameters** | `parameters/` | Node parameters |
| **Launch** | `launch/` | ROS 2 compatible Launch system |
| **Logging** | `logging/` | Log level settings |
| **Clock** | `clock/` | ROS Time/Sim Time |
| **Context** | `context/` | Domain ID settings |
| **Guard Condition** | `guard_condition/` | Thread synchronization |

---

## 🧪 Testing

```bash
# Ubuntu
python3 test/test_examples_ubuntu.py

# macOS
python3 test/test_examples_mac.py
```

---

## 🐛 Troubleshooting

### `ModuleNotFoundError: std_msgs`

Use the runtime-bundled wheel or run `bash scripts/install_ros_data_types.sh`.

### `ImportError: libXxx.so` (source builds)

Ensure `/opt/fast-dds-v3-libs/lib` is in `LD_LIBRARY_PATH`.

### DDS Discovery Fails

- Verify Domain IDs match
- Check firewall isn't blocking UDP ports 7400+
- Ensure you're on the same network

### Slow Startup on macOS

Initial DDS discovery may take a few seconds on macOS. For inter-process communication, add `time.sleep(1.0)` to wait for discovery.

---

## 📄 License

- This repository: Apache-2.0
- Generated code includes eProsima Fast-DDS templates
- rclpy compatibility layer is Apache-2.0 (see `rclpy/LICENSE`)

---

## 🙏 Acknowledgments

- [eProsima Fast DDS](https://github.com/eProsima/Fast-DDS) - High-performance DDS middleware
- [ROS 2](https://ros.org/) - Robot development framework
- [rclpy](https://github.com/ros2/rclpy) - Official ROS 2 Python client library
