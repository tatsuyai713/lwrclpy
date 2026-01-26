# Launch Examples

ROS 2 style launch file examples.
API compatible with ROS 2 launch framework.

## Examples

| File | Description |
|------|-------------|
| [minimal_pubsub.launch.py](minimal_pubsub.launch.py) | Minimal pub/sub |
| [node_with_params.launch.py](node_with_params.launch.py) | Node with parameters |
| [conditional.launch.py](conditional.launch.py) | Conditional launch |
| [substitutions.launch.py](substitutions.launch.py) | Various substitutions |
| [environment.launch.py](environment.launch.py) | Environment variables |
| [opaque_function.launch.py](opaque_function.launch.py) | Dynamic configuration |
| [include_launch.launch.py](include_launch.launch.py) | Including other launch files |
| [timer_action.launch.py](timer_action.launch.py) | Delayed launch |
| [multi_robot.launch.py](multi_robot.launch.py) | Multi-robot (namespaces) |

## Usage

```bash
# Minimal example
python3 examples/launch/minimal_pubsub.launch.py

# With arguments
python3 examples/launch/minimal_pubsub.launch.py topic:=/my_topic

# Conditional
python3 examples/launch/conditional.launch.py use_sim:=true

# Multi-robot
python3 examples/launch/multi_robot.launch.py num_robots:=3
```

## ROS 2 Compatible API

### Supported Actions

| Action | Description |
|--------|-------------|
| `Node` | Launch a node |
| `DeclareLaunchArgument` | Declare an argument |
| `ExecuteProcess` | Execute a process |
| `GroupAction` | Group actions |
| `IncludeLaunchDescription` | Include another launch file |
| `LogInfo` | Log output |
| `SetEnvironmentVariable` | Set environment variable |
| `TimerAction` | Delayed execution |
| `OpaqueFunction` | Dynamic action generation |
| `SetLaunchConfiguration` | Set launch configuration |
| `Shutdown` | Shutdown |
| `PushRosNamespace` | Push namespace |
| `SetParameter` | Set parameter |

### Supported Substitutions

| Substitution | Description |
|--------------|-------------|
| `LaunchConfiguration` | Reference launch argument |
| `EnvironmentVariable` | Reference environment variable |
| `TextSubstitution` | Fixed text |
| `PathJoinSubstitution` | Join paths |
| `PythonExpression` | Evaluate Python expression |
| `FindExecutable` | Find executable |
| `Command` | Command output |
| `ThisLaunchFile` / `ThisLaunchFileDir` | Current launch file |

### Supported Conditions

| Condition | Description |
|-----------|-------------|
| `IfCondition` | Execute if true |
| `UnlessCondition` | Execute if false |
| `LaunchConfigurationEquals` | Value equality |
| `LaunchConfigurationNotEquals` | Value inequality |

## ROS 2 Compatibility

lwrclpy's Launch system is API compatible with ROS 2's launch framework.
Launch files written for ROS 2 work with minimal or no modifications.

**Note**: The following features are not yet supported:
- `launch_testing` framework
- `ComposableNodeContainer` (component nodes)
- Full event system (partial support)
