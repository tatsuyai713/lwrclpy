# lwrclpy サンプル集

このディレクトリには、lwrclpyの各機能を実演するサンプルコードが含まれています。

[English](README_EN.md)

---

## 📁 ディレクトリ構成

```
examples/
├── actions/              # Actionサーバー/クライアント
│   ├── fibonacci_action_server.py
│   ├── fibonacci_action_client.py
│   └── advanced_action_client.py
├── async/                # asyncio統合とFuture
│   └── async_future_demo.py
├── callback_groups/      # MutuallyExclusive/Reentrantコールバック
│   └── callback_groups_demo.py
├── clock/                # Clock, Time, Duration
│   ├── clock_time_duration_demo.py
│   └── sim_time_demo.py
├── context/              # Context管理とDomain ID
│   └── context_demo.py
├── duration/             # Duration演算と比較
│   └── duration_demo.py
├── executor/             # Single/MultiThreaded Executor
│   ├── single_threaded_demo.py
│   ├── multithreaded_executor_demo.py
│   └── multiple_nodes.py
├── guard_condition/      # Guard Conditionトリガー
│   ├── trigger_guard_condition.py
│   └── guard_condition_advanced.py
├── logging/              # ロギングレベルとパターン
│   └── logging_demo.py
├── node/                 # 包括的なノード使用例
│   ├── comprehensive_node_demo.py
│   └── class_based_node.py
├── parameters/           # ノードパラメータ
│   ├── logger_and_params.py
│   └── parameter_events.py
├── pubsub/               # Publisher/Subscriberパターン
│   ├── string/           # 基本的な文字列メッセージ
│   ├── sensor_qos/       # センサー最適化QoS
│   ├── ml/               # 機械学習統合
│   ├── zero_copy/        # loan_messageによるゼロコピー
│   ├── typed_messages/   # Geometry, Sensor, Navメッセージ
│   ├── rate_publisher.py
│   ├── multi_pubsub.py
│   ├── smart_publisher.py
│   └── message_info_demo.py
├── qos/                  # QoSプロファイルとポリシー
│   ├── qos_profiles_demo.py
│   ├── reliable_pubsub.py
│   └── best_effort_pubsub.py
├── services/             # Serviceサーバー/クライアント
│   ├── set_bool/
│   ├── trigger/
│   └── advanced_client.py
├── timers/               # Timer機能
│   ├── wall_timer.py
│   ├── oneshot_and_periodic.py
│   └── timer_features_demo.py
└── video/                # ビデオストリーミング
```

---

## 🚀 サンプルの実行方法

すべてのサンプルはPythonで直接実行できます：

```bash
python examples/<category>/<example_name>.py
```

多くのサンプルは2つのターミナルで実行する必要があります（Publisher/Subscriber、Server/Clientなど）。

---

## 📚 機能別サンプル一覧

### コア機能

| 機能 | サンプル | 説明 |
|------|---------|------|
| 基本的なPub/Sub | `pubsub/string/` | シンプルな文字列メッセージの送受信 |
| 型付きメッセージ | `pubsub/typed_messages/` | Geometry, Sensor, Navメッセージ |
| レート制御Publishing | `pubsub/rate_publisher.py` | `create_rate()`による固定周波数送信 |
| 複数Pub/Sub | `pubsub/multi_pubsub.py` | 1ノードで複数のPublisher/Subscriber |
| QoSプロファイル | `qos/qos_profiles_demo.py` | Deadline, Lifespan, Liveliness含む全QoS |
| Reliable QoS | `qos/reliable_pubsub.py` | Transient Local durabilityでの確実な配信 |
| Best Effort QoS | `qos/best_effort_pubsub.py` | 高周波データ向けBest Effort |
| ゼロコピー | `pubsub/zero_copy/` | 大きなメッセージの効率的な送信 |
| Service | `services/set_bool/` | リクエスト-レスポンスパターン |
| Trigger Service | `services/trigger/` | 空リクエストによるアクション起動 |
| Action | `actions/` | フィードバック付き長時間実行タスク |
| Parameter | `parameters/` | ノードパラメータの宣言とアクセス |
| Guard Condition | `guard_condition/` | スレッド間シグナリングと同期 |

### ノードパターン

| パターン | サンプル | 説明 |
|----------|---------|------|
| 包括的ノード | `node/comprehensive_node_demo.py` | ノードの全機能デモ |
| クラスベースノード | `node/class_based_node.py` | 大規模プロジェクト向け推奨パターン |
| 複数ノード | `executor/multiple_nodes.py` | 1プロセスで複数ノード実行 |

### 新機能/強化機能

| 機能 | サンプル | 説明 |
|------|---------|------|
| Clock & Time | `clock/clock_time_duration_demo.py` | ROS Time, Sim Time, 時間演算 |
| シミュレーション時間 | `clock/sim_time_demo.py` | テスト用時間オーバーライド |
| Duration | `duration/duration_demo.py` | Duration演算と比較 |
| Async/Future | `async/async_future_demo.py` | asyncioとFutureの統合 |
| Logging | `logging/logging_demo.py` | ログレベル、子ロガー、スロットリング |
| Callback Groups | `callback_groups/callback_groups_demo.py` | 排他制御 vs 再入可能 |
| SingleThreadedExecutor | `executor/single_threaded_demo.py` | 基本的なExecutor使用法 |
| MultiThreadedExecutor | `executor/multithreaded_executor_demo.py` | マルチスレッド実行 |
| Context | `context/context_demo.py` | Domain ID、複数コンテキスト |
| Timer機能 | `timers/timer_features_demo.py` | ドリフト補正、呼び出し回数 |
| Smart Publisher | `pubsub/smart_publisher.py` | Subscriber数、Liveliness |
| MessageInfo | `pubsub/message_info_demo.py` | メッセージメタデータアクセス |
| Advanced Client | `services/advanced_client.py` | タイムアウト付き非同期サービス呼び出し |
| Advanced Action | `actions/advanced_action_client.py` | Actionキャンセルと複数Goal |

---

## 📋 QoSプロファイル

lwrclpyは標準的なROS 2 QoSプロファイルをすべてサポート：

| プロファイル | 用途 |
|--------------|------|
| `qos_profile_sensor_data` | 高周波センサーデータ（Best Effort） |
| `qos_profile_services_default` | サービスのリクエスト/レスポンス |
| `qos_profile_parameters` | パラメータサービス |
| `qos_profile_system_default` | デフォルトDDS設定 |
| `qos_profile_action_status_default` | Actionステータス更新 |

カスタムQoSオプション：
- **Deadline**: メッセージ間の最大時間
- **Lifespan**: メッセージ有効期限
- **Liveliness**: Publisher生存検出（AUTOMATIC, MANUAL_BY_PARTICIPANT, MANUAL_BY_TOPIC）

---

## ⚡ ゼロコピーPublishing

大きなメッセージには`loan_message()`でコピーを回避：

```python
with publisher.loan_message() as loaned_msg:
    loaned_msg.data = large_data
    # コンテキスト終了時にメッセージが自動publish
```

---

## ⏰ シミュレーション時間

テスト用にROS Timeをオーバーライド：

```python
from lwrclpy.clock import Clock, ClockType, Time

clock = Clock(clock_type=ClockType.ROS_TIME)
clock.set_ros_time_override(Time(seconds=1000))
# clock.now()がシミュレーション時間を返す
```

---

## 🔒 スレッドセーフティ

`MultiThreadedExecutor`使用時：

1. 同時実行を避けたいコールバックには`MutuallyExclusiveCallbackGroup`を使用
2. 並列実行可能なコールバックには`ReentrantCallbackGroup`を使用
3. 共有状態はロックで保護

---

## 📝 よく使うパターン

### Subscriberを待つ

```python
while publisher.get_subscription_count() < 1:
    time.sleep(0.1)
# publishしても安全
```

### グレースフルシャットダウン

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

### 非同期サービス呼び出し

```python
future = client.call_async(request)
while not future.done():
    rclpy.spin_once(node, timeout_sec=0.1)
response = future.result()
```

---

## 📨 メッセージ型サンプル

`pubsub/typed_messages/`ディレクトリに一般的なROSメッセージ型のサンプル：

| メッセージ型 | Publisher | Subscriber |
|--------------|-----------|------------|
| `geometry_msgs` | `geometry_publisher.py` | `geometry_subscriber.py` |
| `sensor_msgs` | `sensor_publisher.py` | `sensor_subscriber.py` |
| `nav_msgs` | `navigation_demo.py` | - |

### Geometryメッセージ
- `Point`, `Pose`, `PoseStamped`, `Twist`, `Vector3`, `Quaternion`

### Sensorメッセージ
- `LaserScan`, `Imu`, `Range`, `Temperature`

### Navigationメッセージ
- `Odometry`, `Path`

---

## 🔧 サービス型

| サービス型 | サンプル |
|------------|---------|
| `std_srvs/SetBool` | `services/set_bool/` |
| `std_srvs/Trigger` | `services/trigger/` |

---

## ⚡ クイックスタートサンプル

### 最小Publisher

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

### 最小Subscriber

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

### 最小Serviceサーバー

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
