# lwrclpy サンプル集

このディレクトリには、lwrclpy の rclpy 互換 API と、lwrclpy 独自の高速化機能を確認するためのサンプルが含まれています。

[English](README_EN.md)

---

## 基本方針

lwrclpy は既存の rclpy コードがそのまま動くことを重視しています。通常の Publisher / Subscriber / Service / Action / Timer / Executor は、基本的に `import rclpy` と標準の ROS 2 API で書きます。

一方で、lwrclpy には rclpy にはない追加機能があります。代表例は以下です。

- Fast DDS DataSharing / loaned samples を使った自動ゼロコピー最適化
- 同一ホスト向け CPU SharedMemory サイドチャネル
- 同一ホスト向け CUDA IPC サイドチャネル
- 大きな sequence field を効率よく扱う `data_buffer()` / `sequence_buffer()`
- 詳細な `performance_stats`

これらは rclpy 互換 API を壊さない追加機能です。通常は `create_publisher()` / `publish(msg)` のまま使え、必要な場合だけ lwrclpy 独自 API を明示的に使います。

---

## ディレクトリ構成

```text
examples/
├── actions/                 # Action サーバー/クライアント
├── async/                   # asyncio 統合と Future
├── callback_groups/         # MutuallyExclusive/Reentrant callback group
├── clock/                   # Clock, Time, ROS time
├── context/                 # Context と Domain ID
├── cuda_ipc/                # lwrclpy 独自: CUDA IPC サイドチャネル
├── duration/                # Duration
├── executor/                # SingleThreaded/MultiThreaded Executor
├── guard_condition/         # Guard Condition
├── launch/                  # ROS 2 launch 互換サンプル
├── logging/                 # Logging
├── lwrclpy_extensions/      # lwrclpy 独自拡張、ゼロコピー検証
├── node/                    # Node 使用パターン
├── parameters/              # Parameter
├── pubsub/                  # Publisher/Subscriber
│   ├── string/
│   ├── sensor_qos/
│   ├── zero_copy/
│   ├── typed_messages/
│   └── ml/
├── qos/                     # QoS
├── services/                # Service
├── shared_memory/           # lwrclpy 独自: CPU SharedMemory サイドチャネル
├── timers/                  # Timer
└── video/                   # Video/YOLO examples
```

---

## 実行方法

単体サンプル:

```bash
python examples/<category>/<example>.py
```

Publisher/Subscriber や Server/Client のペアは、通常 2 つのターミナルで実行します。

```bash
# terminal 1
python examples/pubsub/string/listener.py

# terminal 2
python examples/pubsub/string/talker.py
```

CI と同じ example runner をローカルで実行する場合:

```bash
LWRCLPY_TEST_TIMEOUT_SCALE=2.0 python -u test/test_examples_mac.py
```

---

## rclpy 互換サンプル

| 機能 | サンプル | 説明 |
|---|---|---|
| 基本 Pub/Sub | `pubsub/string/` | `std_msgs/String` の送受信 |
| Sensor QoS | `pubsub/sensor_qos/` | Best Effort などセンサーデータ向け QoS |
| 型付きメッセージ | `pubsub/typed_messages/` | `geometry_msgs`, `sensor_msgs`, `nav_msgs` |
| Service | `services/set_bool/`, `services/trigger/` | 同期/非同期サービス呼び出し |
| Action | `actions/` | Fibonacci action と advanced client |
| Timer | `timers/` | periodic / oneshot / wall timer |
| Executor | `executor/` | single-threaded / multi-threaded / multiple nodes |
| Callback Group | `callback_groups/` | 排他/再入可能 callback group |
| Parameter | `parameters/` | parameter 宣言、更新、event |
| QoS | `qos/` | reliability, durability, deadline など |
| Clock/Duration | `clock/`, `duration/` | time, ROS time, duration |
| Launch | `launch/` | ROS 2 launch 互換 |

最小 Publisher:

```python
import rclpy
from std_msgs.msg import String

rclpy.init()
node = rclpy.create_node("minimal_pub")
pub = node.create_publisher(String, "topic", 10)

msg = String()
msg.data = "Hello"
pub.publish(msg)

node.destroy_node()
rclpy.shutdown()
```

最小 Subscriber:

```python
import rclpy
from std_msgs.msg import String

def callback(msg):
    print(msg.data)

rclpy.init()
node = rclpy.create_node("minimal_sub")
node.create_subscription(String, "topic", callback, 10)
rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
```

---

## lwrclpy 独自機能: 自動ゼロコピー最適化

### 標準 `publish(msg)` のまま使う

lwrclpy は、可能な場合に Fast DDS DataSharing や loaned samples を内部で有効化します。ユーザーコードは通常の rclpy と同じです。

```python
msg = SomeMessage()
msg.data = payload
publisher.publish(msg)
```

確認用サンプル:

```bash
python examples/lwrclpy_extensions/zero_copy_extension_publisher.py
python examples/lwrclpy_extensions/zero_copy_extension_publisher.py --require-zero-copy
python examples/lwrclpy_extensions/zero_copy_extension_publisher.py --require-complete-zero-copy
```

大きな固定長メッセージでの benchmark:

```bash
python examples/lwrclpy_extensions/large_payload_zero_copy_benchmark.py --samples 10
```

### 何が自動化されるか

- 同じホストで Fast DDS DataSharing が使える型では、DDS の shared-memory transport を優先します。
- 固定サイズ/plain type で middleware loan が使える場合、内部的に loaned sample を使います。
- 失敗した場合は通常の DDS publish にフォールバックします。
- `publisher.performance_stats` で DataSharing や fallback 状態を確認できます。

```python
print(publisher.performance_stats)
```

主な項目:

- `data_sharing_enabled`
- `can_loan_messages`
- `automatic_loaned_publish_enabled`
- `auto_loan_publish_count`
- `zero_copy_fallback_count`
- `last_zero_copy_fallback_reason`

### 明示的な loaned message

rclpy にはない lwrclpy 独自 API です。middleware loan が使える環境で、メッセージを借りて直接フィールドを書きます。

```python
with publisher.borrow_loaned_message(require_zero_copy=True) as msg:
    msg.data = 42
# with を抜けると publish されます
```

失敗時に通常 publish へ落としたい場合は、標準 `publish(msg)` を使ってください。`require_zero_copy=True` は「ゼロコピーでなければ失敗させたい」検証向けです。

---

## lwrclpy 独自機能: CPU SharedMemory サイドチャネル

CPU SharedMemory は、大きな可変長 payload を同一ホスト内で高速に渡すための lwrclpy 独自機能です。DDS では小さな metadata と通常メッセージだけを流し、実データは Python の `multiprocessing.shared_memory` に置きます。

対象例:

```bash
# terminal 1
python examples/shared_memory/image_shared_memory_subscriber.py --read-byte

# terminal 2
python examples/shared_memory/image_shared_memory_publisher.py --width 640 --height 480 --rate 10
```

Subscriber 側に以下のような出力が出れば SharedMemory 経由です。

```text
[recv] 640x480 shared_memory=True nbytes=921600 name=...
```

### 自動切り替え

`node.create_publisher()` / `node.create_subscription()` を使うだけで、lwrclpy は hidden metadata topic を自動的に作成します。

同一ホストに lwrclpy subscriber がいる場合:

- payload が閾値以上なら SharedMemory metadata を publish
- subscriber は通常どおり `msg.data` で payload を読めます
- local lwrclpy subscriber だけなら、DDS の大きな payload は空にして小さな signal message を送ります

別ホストや通常DDS subscriberが混在する場合:

- SharedMemory metadata だけでは届かないため、通常の ROS payload も publish します
- つまり同一ホスト lwrclpy subscriber は SharedMemory、別ホスト/通常 subscriber は DDS payload という形で自動フォールバックします

### Publisher 側: 標準 publish で自動 SharedMemory

通常は標準 `publish(msg)` だけで十分です。

通常の rclpy と同じ代入でも publish できます。

```python
msg = Image()
msg.height = 480
msg.width = 640
msg.encoding = "bgr8"
msg.step = 640 * 3
msg.data = frame
publisher.publish(msg)
```

この場合も、生成 binding が field から buffer view を公開でき、payload サイズが閾値以上で、同一ホストに
lwrclpy subscriber がいれば自動 SharedMemory の対象になります。ただし、`msg.data = frame` の時点で
生成 binding 側の setter がコピーを行うことがあります。

```python
from lwrclpy import data_buffer
from sensor_msgs.msg import Image

msg = Image()
msg.height = 480
msg.width = 640
msg.encoding = "bgr8"
msg.step = 640 * 3

frame = b"\xff" * (640 * 480 * 3)
data_buffer(msg).assign(frame)
publisher.publish(msg)
```

`data_buffer(msg).assign(frame)` は `sensor_msgs/Image.data` のような大きな sequence field に効率よく bytes-like object を入れるためのヘルパーです。rclpy 互換 API ではありませんが、代入時の Python list 化や余分なコピーを避けたい大容量 payload ではこちらを推奨します。

### Publisher 側: 明示的に SharedMemory を使う

rclpy にはない lwrclpy 独自 API です。payload を明示的に SharedMemory 化します。

```python
used = publisher.publish_shared_memory(
    msg,
    frame,
    field="data",
    publish_ros_payload=True,
)
```

`publish_ros_payload=True`:

- DDS payload も送るため、通常 ROS 2 subscriber と互換です。
- 同一ホスト lwrclpy subscriber は SharedMemory を優先できます。

`publish_ros_payload=False`:

- DDS 側の対象 field は空 payload になります。
- 同一ホスト lwrclpy subscriber 専用の高速経路です。
- 通常 ROS 2 subscriber や別ホスト subscriber は実 payload を受け取れません。

### Subscriber 側: 通常の rclpy と同じ形で読む

```python
def on_image(msg):
    data = msg.data
    print(msg.width, msg.height, len(data), data[0] if data else None)
```

重要:

- SharedMemory 経由かを確認したい場合は `getattr(msg.data, "is_shared_memory", False)` を見ます。
- 明示的な buffer 管理が必要な高度な用途では `lwrclpy.get_shared_memory_buffer(msg, "data")` も利用できます。
- SharedMemory は同一ホスト限定です。metadata の `host_id` が違う場合は subscriber 側で無視されます。

### 自動 SharedMemory の環境変数

| 環境変数 | デフォルト | 説明 |
|---|---:|---|
| `LWRCLPY_AUTO_SHM_THRESHOLD` | `262144` | 自動 SharedMemory 化する payload サイズ閾値。`0` で無効化 |
| `LWRCLPY_AUTO_SHM_FIELDS` | `data` | 自動 SharedMemory 対象 field。カンマ区切り |
| `LWRCLPY_SHM_KEEPALIVE` | `32` | publisher が保持する SharedMemory allocation 数 |
| `LWRCLPY_SHM_SUBSCRIBER_COUNT_TTL` | `0.05` | local subscriber 数キャッシュ秒数 |

例:

```bash
LWRCLPY_AUTO_SHM_THRESHOLD=65536 \
LWRCLPY_AUTO_SHM_FIELDS=data \
python examples/shared_memory/image_shared_memory_publisher.py
```

---

## lwrclpy 独自機能: CUDA IPC サイドチャネル

CUDA IPC は GPU memory を同一ホストの別プロセスへ渡すためのサイドチャネルです。CUDA 環境と CuPy または cuda-python が必要です。

```bash
# terminal 1
python examples/cuda_ipc/image_cuda_ipc_subscriber.py --open-cupy

# terminal 2
python examples/cuda_ipc/image_cuda_ipc_publisher.py --metadata-only
```

Publisher 側:

```python
used = publisher.publish_cuda(
    msg,
    cuda_array,
    field="data",
    publish_ros_payload=True,
)
```

Subscriber 側:

```python
def on_image(msg):
    data = msg.data
    if getattr(data, "is_cuda_ipc", False):
        arr = data.open_cupy()
    else:
        arr = msg.data
```

注意:

- CUDA IPC は同一ホスト・CUDA対応環境専用です。
- `publish_ros_payload=True` なら通常 DDS payload も送ります。
- `publish_ros_payload=False` または example の `--metadata-only` は lwrclpy CUDA IPC subscriber 専用です。
- CUDA IPC metadata publish に失敗した場合は通常 publish へフォールバックします。

関連README:

```bash
cat examples/cuda_ipc/README.md
```

---

## 大きな sequence field の扱い

`sensor_msgs/Image.data` や `PointCloud2.data` のような大きな sequence field は、Python list に変換すると大きなコストになります。lwrclpy では以下を使います。

```python
from lwrclpy import data_buffer, sequence_buffer

data_buffer(msg).assign(frame_bytes)
view = data_buffer(msg).memoryview()
```

`publisher.publish_buffer()` も使用できます。

```python
publisher.publish_buffer(frame_bytes, field="data", msg=msg)
```

複数 field をまとめて入れる場合:

```python
publisher.publish_buffers({"data": frame_bytes}, msg=msg)
```

---

## QoS

標準 rclpy と同様に `QoSProfile` と QoS policy enum を使います。

```python
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy

qos = QoSProfile(
    depth=10,
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    history=QoSHistoryPolicy.KEEP_LAST,
)
```

サンプル:

- `qos/qos_profiles_demo.py`
- `qos/reliable_pubsub.py`
- `qos/best_effort_pubsub.py`

---

## メッセージ型サンプル

| メッセージ型 | Publisher | Subscriber |
|---|---|---|
| `geometry_msgs` | `pubsub/typed_messages/geometry_publisher.py` | `pubsub/typed_messages/geometry_subscriber.py` |
| `sensor_msgs` | `pubsub/typed_messages/sensor_publisher.py` | `pubsub/typed_messages/sensor_subscriber.py` |
| `nav_msgs` | `pubsub/typed_messages/navigation_demo.py` | - |
| `sensor_msgs/Image` + SharedMemory | `shared_memory/image_shared_memory_publisher.py` | `shared_memory/image_shared_memory_subscriber.py` |
| `sensor_msgs/Image` + CUDA IPC | `cuda_ipc/image_cuda_ipc_publisher.py` | `cuda_ipc/image_cuda_ipc_subscriber.py` |

---

## スレッドセーフティ

`MultiThreadedExecutor` 使用時は、標準 rclpy と同様に callback group を使って排他制御します。

```python
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

exclusive = MutuallyExclusiveCallbackGroup()
reentrant = ReentrantCallbackGroup()

node.create_subscription(Msg, "topic", callback, 10, callback_group=exclusive)
```

共有状態は Python の `threading.Lock` などで保護してください。

---

## トラブルシュート

### SharedMemory が使われず DDS payload になる

- payload が `LWRCLPY_AUTO_SHM_THRESHOLD` より小さい可能性があります。
- subscriber が同一ホストで起動していない可能性があります。
- 通常 ROS 2 subscriber や別ホスト subscriber が混在すると、互換性のため DDS payload も送られます。
- `getattr(msg.data, "is_shared_memory", False)` が `False` の場合は通常 DDS payload として処理してください。

### ゼロコピーが使われているか確認したい

```python
print(pub.performance_stats)
```

または:

```bash
python examples/lwrclpy_extensions/zero_copy_extension_publisher.py --require-complete-zero-copy
```

### DataSharing を無効化したい

```bash
LWRCLPY_NO_DATASHARING=1 python examples/pubsub/zero_copy/zero_copy_publisher.py
```

### DataSharing のディレクトリを指定したい

```bash
LWRCLPY_DATASHARING_DIR=/dev/shm/lwrclpy python your_app.py
```

### fallback 理由をログに出したい

```bash
LWRCLPY_LOG_ZERO_COPY_FALLBACK=1 python your_app.py
```

---

## 追加依存が必要なサンプル

| サンプル | 追加依存 |
|---|---|
| `pubsub/ml/` | `torch` |
| `video/` | `opencv-python`, `numpy`, optional `ultralytics`, `torch` |
| `cuda_ipc/` | CUDA runtime, CuPy または cuda-python |

---

## CIで実行される範囲

`test/examples_test_runner.py` が多くの examples を実行します。CUDA、動画、benchmark、ML など環境依存のものは、対応する環境変数を有効にした場合だけ実行されます。

```bash
LWRCLPY_TEST_CUDA_IPC=1 python -u test/test_examples_mac.py
LWRCLPY_TEST_VIDEO=1 LWRCLPY_TEST_VIDEO_FILE=/path/to/video.mp4 python -u test/test_examples_mac.py
LWRCLPY_TEST_BENCHMARKS=1 python -u test/test_examples_mac.py
```
