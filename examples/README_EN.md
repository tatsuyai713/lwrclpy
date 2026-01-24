# lwrclpy Examples

This directory contains example code demonstrating various features of lwrclpy.

[日本語](README.md)

---

## 📁 Directory Structure

```
examples/
├── actions/              # Action server/client
│   ├── fibonacci_action_server.py
│   ├── fibonacci_action_client.py
│   └── advanced_action_client.py
├── async/                # asyncio integration with Future
│   └── async_future_demo.py
├── callback_groups/      # MutuallyExclusive/Reentrant callbacks
│   └── callback_groups_demo.py
├── clock/                # Clock, Time, Duration
│   ├── clock_time_duration_demo.py
│   └── sim_time_demo.py
├── context/              # Context management and Domain ID
│   └── context_demo.py
├── duration/             # Duration arithmetic and comparisons
│   └── duration_demo.py
├── executor/             # Single/MultiThreaded Executor
│   ├── single_threaded_demo.py
│   ├── multithreaded_executor_demo.py
│   └── multiple_nodes.py
├── guard_condition/      # Guard Condition triggers
│   ├── trigger_guard_condition.py
│   └── guard_condition_advanced.py
├── logging/              # Logging levels and patterns
│   └── logging_demo.py
├── node/                 # Comprehensive node usage
│   ├── comprehensive_node_demo.py
│   └── class_based_node.py
├── parameters/           # Node parameters
│   ├── logger_and_params.py
│   └── parameter_events.py
├── pubsub/               # Publisher/Subscriber patterns
│   ├── string/           # Basic string messages
│   ├── sensor_qos/       # Sensor-optimized QoS
│   ├── ml/               # Machine learning integration
│   ├── zero_copy/        # Zero-copy with loan_message
│   ├── typed_messages/   # Geometry, Sensor, Nav messages
│   ├── rate_publisher.py
│   ├── multi_pubsub.py
│   ├── smart_publisher.py
│   └── message_info_demo.py
├── qos/                  # QoS profiles and policies
│   ├── qos_profiles_demo.py
│   ├── reliable_pubsub.py
│   └── best_effort_pubsub.py
├── services/             # Service server/client
│   ├── set_bool/
│   ├── trigger/
│   └── advanced_client.py
├── timers/               # Timer features
│   ├── wall_timer.py
│   ├── oneshot_and_periodic.py
│   └── timer_features_demo.py
└── video/                # Video streaming
```

---

## 🚀 Running Examples

All examples can be run directly with Python:

```bash
python examples/<category>/<example_name>.py
```

Many examples require two terminals (Publisher/Subscriber, Server/Client, etc.).

---

## 📚 Feature Examples

### Core Features

| Feature | Example | Description |
|---------|---------|-------------|
| Basic Pub/Sub | `pubsub/string/` | Simple string message publishing and subscribing |
| Typed Messages | `pubsub/typed_messages/` | Geometry, Sensor, Nav messages |
| Rate Publishing | `pubsub/rate_publisher.py` | Fixed-frequency publishing with `create_rate()` |
| Multi Pub/Sub | `pubsub/multi_pubsub.py` | Multiple publishers/subscribers in one node |
| QoS Profiles | `qos/qos_profiles_demo.py` | All QoS including Deadline, Lifespan, Liveliness |
| Reliable QoS | `qos/reliable_pubsub.py` | Reliable delivery with Transient Local durability |
| Best Effort QoS | `qos/best_effort_pubsub.py` | Best effort for high-frequency data |
| Zero-Copy | `pubsub/zero_copy/` | Efficient large message publishing |
| Service | `services/set_bool/` | Request-response pattern |
| Trigger Service | `services/trigger/` | Empty-request services for triggering actions |
| Action | `actions/` | Long-running tasks with feedback |
| Parameters | `parameters/` | Node parameter declaration and access |
| Guard Condition | `guard_condition/` | Thread signaling and synchronization |

### Node Patterns

| Pattern | Example | Description |
|---------|---------|-------------|
| Comprehensive Node | `node/comprehensive_node_demo.py` | Full node feature demonstration |
| Class-based Node | `node/class_based_node.py` | Recommended pattern for larger projects |
| Multiple Nodes | `executor/multiple_nodes.py` | Running multiple nodes in one process |

### New/Enhanced Features

| Feature | Example | Description |
|---------|---------|-------------|
| Clock & Time | `clock/clock_time_duration_demo.py` | ROS Time, Sim Time, time arithmetic |
| Simulated Time | `clock/sim_time_demo.py` | Time override for testing |
| Duration | `duration/duration_demo.py` | Duration math and comparisons |
| Async/Future | `async/async_future_demo.py` | asyncio integration with Future |
| Logging | `logging/logging_demo.py` | Log levels, child loggers, throttling |
| Callback Groups | `callback_groups/callback_groups_demo.py` | Mutual exclusion vs reentrant |
| SingleThreadedExecutor | `executor/single_threaded_demo.py` | Basic executor usage |
| MultiThreadedExecutor | `executor/multithreaded_executor_demo.py` | Multi-threaded execution |
| Context | `context/context_demo.py` | Domain ID, multiple contexts |
| Timer Features | `timers/timer_features_demo.py` | Drift compensation, call count |
| Smart Publisher | `pubsub/smart_publisher.py` | Subscription count, liveliness |
| MessageInfo | `pubsub/message_info_demo.py` | Message metadata access |
| Advanced Client | `services/advanced_client.py` | Async service calls with timeout |
| Advanced Action | `actions/advanced_action_client.py` | Action cancellation and multiple goals |

---

## 📋 QoS Profiles

lwrclpy supports all standard ROS 2 QoS profiles:

| Profile | Use Case |
|---------|----------|
| `qos_profile_sensor_data` | High-frequency sensor data (Best Effort) |
| `qos_profile_services_default` | Service requests/responses |
| `qos_profile_parameters` | Parameter services |
| `qos_profile_system_default` | Default DDS settings |
| `qos_profile_action_status_default` | Action status updates |

Custom QoS options:
- **Deadline**: Maximum time between messages
- **Lifespan**: Message expiration time
- **Liveliness**: Publisher alive detection (AUTOMATIC, MANUAL_BY_PARTICIPANT, MANUAL_BY_TOPIC)

---

## ⚡ Zero-Copy Publishing

Use `loan_message()` to avoid copying for large messages:

```python
with publisher.loan_message() as loaned_msg:
    loaned_msg.data = large_data
    # Message is auto-published on context exit
```

---

## ⏰ Simulated Time

Override ROS Time for testing:

```python
from lwrclpy.clock import Clock, ClockType, Time

clock = Clock(clock_type=ClockType.ROS_TIME)
clock.set_ros_time_override(Time(seconds=1000))
# clock.now() returns simulated time
```

---

## 🔒 Thread Safety

When using `MultiThreadedExecutor`:

1. Use `MutuallyExclusiveCallbackGroup` for callbacks that must not run concurrently
2. Use `ReentrantCallbackGroup` for callbacks that can run in parallel
3. Protect shared state with locks

---

## 📝 Common Patterns

### Wait for Subscribers

```python
while publisher.get_subscription_count() < 1:
    time.sleep(0.1)
# Now safe to publish
```

### Graceful Shutdown

```python
try:
    rclpy.init()
    node = rclpy.create_node('my_node')
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    rclpy.shutdown()
```

### Async Service Call

```python
future = client.call_async(request)
while not future.done():
    rclpy.spin_once(node, timeout_sec=0.1)
response = future.result()
```

---

## 📨 Message Type Examples

The `pubsub/typed_messages/` directory contains examples for common ROS message types:

| Message Type | Publisher | Subscriber |
|--------------|-----------|------------|
| `geometry_msgs` | `geometry_publisher.py` | `geometry_subscriber.py` |
| `sensor_msgs` | `sensor_publisher.py` | `sensor_subscriber.py` |
| `nav_msgs` | `navigation_demo.py` | - |

### Geometry Messages
- `Point`, `Pose`, `PoseStamped`, `Twist`, `Vector3`, `Quaternion`

### Sensor Messages
- `LaserScan`, `Imu`, `Range`, `Temperature`

### Navigation Messages
- `Odometry`, `Path`

---

## 🔧 Service Types

| Service Type | Example |
|--------------|---------|
| `std_srvs/SetBool` | `services/set_bool/` |
| `std_srvs/Trigger` | `services/trigger/` |

---

## ⚡ Quick Start Examples

### Minimal Publisher

```python
#!/usr/bin/env python3
import rclpy
from std_msgs.msg import String

rclpy.init()
node = rclpy.create_node('minimal_pub')
pub = node.create_publisher(String, 'topic', 10)

msg = String()
msg.data = 'Hello!'
pub.publish(msg)

node.destroy_node()
rclpy.shutdown()
```

### Minimal Subscriber

```python
#!/usr/bin/env python3
import rclpy
from std_msgs.msg import String

def callback(msg):
    print(f'Received: {msg.data}')

rclpy.init()
node = rclpy.create_node('minimal_sub')
sub = node.create_subscription(String, 'topic', callback, 10)
rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
```

### Minimal Service Server

```python
#!/usr/bin/env python3
import rclpy
from std_srvs.srv import Trigger

def handle(request, response):
    response.success = True
    response.message = 'Done!'
    return response

rclpy.init()
node = rclpy.create_node('minimal_srv')
srv = node.create_service(Trigger, 'service', handle)
rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
```
