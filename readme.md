# lwrclpy — rclpy-Compatible API Without ROS 2 (Fast DDS v3)

[![CI](https://github.com/tatsuyai713/lwrclpy/actions/workflows/ci.yml/badge.svg)](https://github.com/tatsuyai713/lwrclpy/actions/workflows/ci.yml)

[English](README_EN.md)

**lwrclpy**（Lightweight rclpy）は、Fast DDS v3上に直接構築したrclpy互換のPythonライブラリです。ROS 2をインストールせずに、rclpyと同じAPIでロボットアプリケーションを開発できます。

---

## 🎯 lwrclpyとは？

lwrclpyは、ROS 2のPythonクライアントライブラリ「rclpy」のAPIを、Fast DDS v3上で再実装したライブラリです。ROS 2の複雑なビルドシステムや依存関係を避けながら、馴染みのあるrclpy APIをそのまま使用できます。

### 💡 こんな時に便利

- **macOSでROS 2アプリを開発したい** — ROS 2はmacOSを公式サポートしていません
- **ROS 2のフルインストールを避けたい** — 単一のpipパッケージで完結
- **既存のrclpyコードを移植したい** — API互換なのでコード変更最小限
- **軽量な環境でロボット通信したい** — 必要なのはPythonとFast DDSだけ
- **ROS 2ノードと相互通信したい** — 同じDDS/RTPSネットワークで動作

---

## 📊 rclpyとの比較

### 機能比較表

| 機能 | lwrclpy | rclpy (ROS 2) | 備考 |
|------|---------|---------------|------|
| **インストール** | `pip install` のみ | ROS 2フルインストール必要 | lwrclpyは依存関係が少ない |
| **macOSサポート** | ✅ 完全対応 | ⚠️ 非公式/困難 | lwrclpyはApple Silicon対応 |
| **Ubuntu/Linuxサポート** | ✅ 完全対応 | ✅ 完全対応 | 両方問題なし |
| **Windowsサポート** | 🚧 開発中 | ✅ 対応 | - |
| **ROS 2との相互運用** | ✅ DDS経由で通信可能 | - | 同じドメインIDで接続 |
| **Publisher/Subscriber** | ✅ | ✅ | API互換 |
| **Service Server/Client** | ✅ | ✅ | API互換 |
| **Action Server/Client** | ✅ | ✅ | API互換 |
| **Timer** | ✅ | ✅ | OneShot/Periodic対応 |
| **Parameters** | ✅ | ✅ | 基本機能対応 |
| **Executor** | ✅ | ✅ | Single/MultiThreaded対応 |
| **Callback Groups** | ✅ | ✅ | MutuallyExclusive/Reentrant |
| **Guard Conditions** | ✅ | ✅ | スレッド間同期 |
| **QoS Profiles** | ✅ | ✅ | 主要ポリシー対応 |
| **ゼロコピー通信** | ✅ DataSharing/loan/SharedMemoryを内部利用 | ⚠️ rmw実装依存、rclpy公開loan APIなし | アプリ側は標準 `publish(msg)` のまま利用可能 |
| **CPU SharedMemoryサイドチャネル** | ✅ 同一ホストで自動利用 | ❌ | lwrclpy独自拡張。別ホスト/通常DDS subscriberにはDDS payloadでフォールバック |
| **CUDA IPCサイドチャネル** | ✅ 対応環境で利用可能 | ❌ | lwrclpy独自拡張。GPU memoryを同一ホストの別プロセスへ渡す |
| **大容量sequence buffer API** | ✅ `data_buffer()` / `sequence_buffer()` | ❌ | `Image.data`などをPython list化せず扱う |
| **Clock/Time/Duration** | ✅ | ✅ | ROS Time/Sim Time対応 |
| **Logging** | ✅ | ✅ | レベル/スロットリング対応 |
| **Context/Domain ID** | ✅ | ✅ | 複数コンテキスト対応 |
| **Launch System** | ✅ | ✅ | launch/launch_ros API互換 |
| **Lifecycle Nodes** | ❌ 未対応 | ✅ | 将来対応予定 |
| **Component Nodes** | ❌ 未対応 | ✅ | 将来対応予定 |
| **ros2 CLI** | ❌ 不要 | ✅ | lwrclpyはCLI不要 |

### パフォーマンス特性

| 項目 | lwrclpy | rclpy | 備考 |
|------|---------|-------|------|
| **起動時間** | ⚡ 高速 | 🐢 やや遅い | ROS 2ミドルウェア層がない |
| **メモリ使用量** | 📉 少ない | 📈 多い | 最小限の依存関係 |
| **ゼロコピー** | ✅ Fast DDS DataSharing / loaned samples / SharedMemory | ⚠️ rmw依存、rclpy loan APIなし | アプリコードを変えずに大型メッセージで効果 |
| **レイテンシ** | ⚡ 低い | ⚡ 低い | 同等（同じDDS基盤） |

### 動作確認済み環境

| OS | バージョン | Python | 状態 |
|----|-----------|--------|------|
| **Ubuntu** | 24.04 LTS | 3.12 | ✅ 完全対応 |
| **macOS** | Sonoma 14+ | 3.11 | ✅ 完全対応（Apple Silicon） |

---

## 📦 クイックスタート

### 事前ビルド済みホイールがある場合

```bash
# 1) venvを作成して有効化（推奨）
python3 -m venv venv
source venv/bin/activate

# 2) ホイールをインストール
pip install dist/lwrclpy-*.whl

# 3) サンプルを実行（2つのターミナルで）
# ターミナルA（受信側）
python3 examples/pubsub/string/listener.py

# ターミナルB（送信側）
python3 examples/pubsub/string/talker.py
```

### インストール確認

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

## 🔧 ビルド方法

### Ubuntu

```bash
# 1) サブモジュール取得
git submodule update --init --recursive

# 2) Fast DDS v3ツールチェーンをインストール
bash scripts/install_fastdds_v3_colcon.sh

# 3) venv作成
python3 -m venv venv
source venv/bin/activate
pip install setuptools

# 4) ROS DataTypesを生成・インストール
bash scripts/install_ros_data_types.sh

# 5) ランタイム同梱ホイールをビルド
bash scripts/make_pip_package_with_runtime.sh

# 6) インストール
pip install dist/lwrclpy-*.whl
```

### macOS (Apple Silicon / Intel)

```bash
# 1) Homebrewで依存関係をインストール
brew install cmake ninja git pkg-config tinyxml2 wget curl swig gradle openssl@3 python@3.11

# 2) サブモジュール取得
git submodule update --init --recursive

# 3) Fast DDS v3をビルド
bash scripts/mac/mac_install_fastdds_v3_colcon.sh

# 4) venv作成
python3 -m venv venv
source venv/bin/activate
pip install setuptools

# 5) ROS DataTypesを生成・インストール
bash scripts/mac/mac_install_ros_data_types.sh

# 6) ランタイム同梱ホイールをビルド
bash scripts/mac/mac_make_pip_package_with_runtime.sh

# 7) インストール
pip install dist/lwrclpy-*-macosx*.whl
```

---

## 📚 基本的な使い方

### Publisher / Subscriber

```python
#!/usr/bin/env python3
import rclpy
from std_msgs.msg import String

# 初期化
rclpy.init()
node = rclpy.create_node('example_node')

# Publisher作成
pub = node.create_publisher(String, 'chatter', 10)

# Subscriber作成
def callback(msg):
    print(f'受信: {msg.data}')

sub = node.create_subscription(String, 'chatter', callback, 10)

# メッセージ送信
msg = String()
msg.data = 'Hello, lwrclpy!'
pub.publish(msg)

# スピン（コールバック処理）
rclpy.spin(node)

# 終了処理
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

# サービスサーバー
def handle_service(request, response):
    response.success = request.data
    response.message = 'OK' if request.data else 'NG'
    return response

server = node.create_service(SetBool, 'set_bool', handle_service)

# サービスクライアント
client = node.create_client(SetBool, 'set_bool')
client.wait_for_service()

request = SetBool.Request()
request.data = True
future = client.call_async(request)

rclpy.spin_until_future_complete(node, future)
print(f'結果: {future.result().message}')

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
    print(f'タイマー発火: {count}回目')

# 1秒周期のタイマー
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

# Actionクライアント
action_client = ActionClient(node, Fibonacci, 'fibonacci')
action_client.wait_for_server()

# Goal送信
goal = Fibonacci.Goal()
goal.order = 10

future = action_client.send_goal_async(goal)
rclpy.spin_until_future_complete(node, future)

goal_handle = future.result()
result_future = goal_handle.get_result_async()
rclpy.spin_until_future_complete(node, result_future)

print(f'結果: {result_future.result().result.sequence}')

node.destroy_node()
rclpy.shutdown()
```

---

## 🚀 高度な機能

lwrclpyの最重要方針はrclpy互換です。通常のアプリケーションは、ROS 2 rclpyと同じ
`create_publisher()` / `create_subscription()` / `publish(msg)` で書けます。

一方で、lwrclpyにはROS 2 rclpyにはない高速化機能があります。これらは互換APIを壊さない追加機能です。
標準APIのまま自動で使われるものと、必要な場合だけ明示的に使うAPIがあります。

### 自動ゼロコピー最適化

標準のrclpy互換コードでは、通常通り `publish(msg)` を使います。

```python
msg = Image()
msg.data = large_data
publisher.publish(msg)
```

lwrclpyは可能な場合に、内部で以下を自動利用します。

- Fast DDS DataSharing
- middleware loaned samples
- 同一ホスト向けCPU SharedMemoryサイドチャネル

固定サイズ/plain typeでloanが使える場合は、通常の`publish(msg)`とsubscription callbackのまま
loaned sample経路を利用します。`sensor_msgs/Image`や`std_msgs/String`のような可変長payloadでは、
loaned sampleが使えないため、同一ホストではSharedMemoryサイドチャネル、別ホストでは通常DDS payloadへ
自動的に切り替わります。

現在の環境でゼロコピー経路を確認するには、次を実行します。

```bash
python3 examples/lwrclpy_extensions/zero_copy_extension_publisher.py --require-complete-zero-copy
python3 examples/lwrclpy_extensions/large_payload_zero_copy_benchmark.py --samples 10
```

実行時の状態は `performance_stats` で確認できます。

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

明示的にloaned messageを使いたい場合は、lwrclpy独自APIを使用できます。

```python
with publisher.borrow_loaned_message(require_zero_copy=True) as msg:
    msg.data = 42
# withを抜けるとpublishされます
```

移植性を優先するコードでは、標準の`publish(msg)`を使ってください。
`require_zero_copy=True`は「ゼロコピーでなければ失敗させたい」検証向けです。

### CPU SharedMemoryサイドチャネル

CPU SharedMemoryは、大きな可変長payloadを同一ホスト内で高速に渡すためのlwrclpy独自機能です。
DDSには小さなmetadataと通常メッセージを流し、実データはPythonの
`multiprocessing.shared_memory`に置きます。

サンプル:

```bash
# terminal 1
python3 examples/shared_memory/image_shared_memory_subscriber.py --read-byte

# terminal 2
python3 examples/shared_memory/image_shared_memory_publisher.py --width 640 --height 480 --rate 10
```

Subscriber側に次のような出力が出ればSharedMemory経由です。

```text
[recv] 640x480 shared_memory=True nbytes=921600 name=...
```

#### 自動切り替え

`node.create_publisher()` / `node.create_subscription()` を使うだけで、lwrclpyはhidden metadata topicを
自動的に作成します。

同一ホストにlwrclpy subscriberがいる場合:

- payloadが閾値以上ならSharedMemory metadataをpublishします
- subscriberは`get_shared_memory_buffer(msg, "data")`でSharedMemoryを取得できます
- local lwrclpy subscriberだけなら、DDSの大きなpayloadは空にして小さなsignal messageを送ります

別ホストや通常DDS subscriberが混在する場合:

- SharedMemory metadataだけでは届かないため、通常のDDS payloadもpublishします
- 同一ホストlwrclpy subscriberはSharedMemory、別ホスト/通常subscriberはDDS payloadを受け取ります
- ユーザーコードは標準の`publish(msg)`のままで動作します

#### Publisher側

通常のrclpyと同じ書き方でもpublishできます。

```python
msg = Image()
msg.height = 480
msg.width = 640
msg.encoding = "bgr8"
msg.step = 640 * 3
msg.data = frame
publisher.publish(msg)
```

この場合も、生成bindingがfieldからbuffer viewを公開でき、payloadサイズが閾値以上で、同一ホストに
lwrclpy subscriberがいれば自動SharedMemoryの対象になります。ただし、`msg.data = frame` の時点で
生成binding側のsetterがコピーを行うことがあります。

標準`publish(msg)`で自動SharedMemoryを使う例:

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

`data_buffer(msg).assign(frame)` は、`sensor_msgs/Image.data` のような大きなsequence fieldへ
bytes-like objectを効率よく入れるためのヘルパーです。rclpy互換APIではありませんが、代入時の
Python list化や余分なコピーを避けたい大容量payloadではこちらを推奨します。

明示的にSharedMemory化したい場合:

```python
used = publisher.publish_shared_memory(
    msg,
    frame,
    field="data",
    publish_ros_payload=True,
)
```

`publish_ros_payload=True`なら、通常ROS 2 subscriberや別ホストsubscriberにもDDS payloadが届きます。
`publish_ros_payload=False`は同一ホストlwrclpy subscriber専用の高速経路で、DDS側の対象fieldは空になります。

#### Subscriber側

```python
from lwrclpy import get_shared_memory_buffer

def on_image(msg):
    shm = get_shared_memory_buffer(msg, "data")
    if shm is None:
        # 通常DDS payload
        data = msg.data
        return

    view = shm.open_memoryview()
    try:
        first = view[0]
        nbytes = shm.nbytes
        print(first, nbytes)
    finally:
        release = getattr(view, "release", None)
        if callable(release):
            release()
        shm.close()
```

注意点:

- `open_memoryview()`で得たmemoryviewが残っている間は、`SharedMemory.close()`が`BufferError`になることがあります
- `bytes(view)`や`shm.tobytes()`はPython bytesへコピーします。ゼロコピーで処理する場合はmemoryviewを直接使います
- SharedMemoryは同一ホスト限定です。metadataの`host_id`が違う場合はsubscriber側で無視されます

#### 環境変数

| 環境変数 | デフォルト | 説明 |
|---|---:|---|
| `LWRCLPY_AUTO_SHM_THRESHOLD` | `262144` | 自動SharedMemory化するpayloadサイズ閾値。`0`で無効化 |
| `LWRCLPY_AUTO_SHM_FIELDS` | `data` | 自動SharedMemory対象field。カンマ区切り |
| `LWRCLPY_SHM_KEEPALIVE` | `32` | publisherが保持するSharedMemory allocation数 |
| `LWRCLPY_SHM_SUBSCRIBER_COUNT_TTL` | `0.05` | local subscriber数キャッシュ秒数 |

例:

```bash
LWRCLPY_AUTO_SHM_THRESHOLD=65536 \
LWRCLPY_AUTO_SHM_FIELDS=data \
python3 examples/shared_memory/image_shared_memory_publisher.py
```

### CUDA IPCサイドチャネル

CUDA IPCは、GPU memoryを同一ホストの別プロセスへ渡すためのlwrclpy独自機能です。
CUDA環境とCuPyまたはcuda-pythonが必要です。

```bash
# terminal 1
python3 examples/cuda_ipc/image_cuda_ipc_subscriber.py --read-byte

# terminal 2
python3 examples/cuda_ipc/image_cuda_ipc_publisher.py --metadata-only
```

Publisher側:

```python
used = publisher.publish_cuda(
    msg,
    cuda_array,
    field="data",
    publish_ros_payload=True,
)
```

Subscriber側:

```python
from lwrclpy import get_cuda_buffer

def on_image(msg):
    cuda_buf = get_cuda_buffer(msg, "data")
    if cuda_buf is None:
        return
    arr = cuda_buf.open_cupy()
```

`publish_ros_payload=True`なら通常DDS payloadも送ります。`publish_ros_payload=False`や
exampleの`--metadata-only`は、同一ホストのlwrclpy CUDA IPC subscriber専用です。

### 大きなsequence fieldの扱い

`sensor_msgs/Image.data`や`PointCloud2.data`のような大きなsequence fieldは、Python listに変換すると
大きなコストになります。lwrclpyでは次のヘルパーを使えます。

```python
from lwrclpy import data_buffer, sequence_buffer

data_buffer(msg).assign(frame_bytes)
view = data_buffer(msg).memoryview()
```

Publisherから直接payloadを入れて送る場合:

```python
publisher.publish_buffer(frame_bytes, field="data", msg=msg)
publisher.publish_buffers({"data": frame_bytes}, msg=msg)
```

### QoSプロファイル

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

# カスタムQoS
qos = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL
)

pub = node.create_publisher(String, 'topic', qos)
```

### マルチスレッドExecutor

```python
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

# コールバックグループ
group = MutuallyExclusiveCallbackGroup()

# タイマーにグループを指定
timer = node.create_timer(1.0, callback, callback_group=group)

# マルチスレッド実行
executor = MultiThreadedExecutor(num_threads=4)
executor.add_node(node)
executor.spin()
```

### Context と Domain ID

```python
from rclpy.context import Context

# カスタムDomain IDでコンテキスト作成
context = Context()
rclpy.init(context=context, domain_id=42)

node = rclpy.create_node('isolated_node', context=context)
```

### Launch システム

ROS 2と同じLaunch APIを使用して、複数のプロセスやノードを起動できます。

**探索ディレクトリについて（重要）**  
`launch_ros.actions.Node` は **カレントディレクトリ配下のみ** を探索します。  
`executable` は相対パス/絶対パスで指定するか、起動時のカレントを調整してください。

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
        # 引数の宣言
        DeclareLaunchArgument('verbose', default_value='true'),
        
        # 条件付きログ出力
        LogInfo(
            condition=IfCondition(LaunchConfiguration('verbose')),
            msg='Starting application...'
        ),
        
        # Publisherノードの起動
        Node(
            package='pubsub/string',
            executable='talker',
            name='talker',
            parameters=[{'rate': 1.0}],
        ),

        # Subscriberノードの起動
        Node(
            package='pubsub/string',
            executable='listener',
            name='listener',
        ),
    ])

if __name__ == '__main__':
    from launch import LaunchService
    ls = LaunchService()
    ls.include_launch_description(generate_launch_description())
    ls.run()
```

**実行方法:**
```bash
# 基本実行（カレントディレクトリ配下から探索）
python3 my_launch.py

# 引数を指定して実行
python3 my_launch.py verbose:=false
```

---

## 🔗 ROS 2との相互運用

lwrclpyノードはROS 2ノードと同じDDS/RTPSネットワーク上で通信できます。

### 設定

```bash
# Domain IDを一致させる
export ROS_DOMAIN_ID=0      # ROS 2側
export LWRCL_DOMAIN_ID=0    # lwrclpy側
```

### 通信例

```bash
# ターミナルA: ROS 2 リスナー
ros2 run demo_nodes_cpp listener

# ターミナルB: lwrclpy トーカー
python3 examples/pubsub/string/talker.py
```

### 注意点

- **トピック名/型**: 完全に一致させる必要があります
- **QoS**: 互換性のある設定にする（特にReliability/Durability）
- **Discovery時間**: DDSディスカバリには数秒かかることがあります

---

## 📖 サンプル一覧

詳細は [examples/README.md](examples/README.md) を参照してください。

| カテゴリ | サンプル | 説明 |
|----------|---------|------|
| **Pub/Sub** | `pubsub/string/` | 基本的な文字列メッセージ |
| **Pub/Sub** | `pubsub/typed_messages/` | 各種ROS型メッセージ |
| **Pub/Sub** | `pubsub/zero_copy/` | 標準rclpy APIでのゼロコピー向けPublishing |
| **SharedMemory** | `shared_memory/` | 同一ホスト向けCPU SharedMemoryサイドチャネル |
| **CUDA IPC** | `cuda_ipc/` | GPU memoryを同一ホストの別プロセスへ渡すサイドチャネル |
| **lwrclpy拡張** | `lwrclpy_extensions/` | DataSharing/loaned message/大容量payloadベンチマーク |
| **Service** | `services/set_bool/` | SetBoolサービス |
| **Service** | `services/trigger/` | Triggerサービス |
| **Action** | `actions/` | Fibonacciアクション |
| **Timer** | `timers/` | 周期/ワンショットタイマー |
| **Executor** | `executor/` | Single/MultiThreaded |
| **QoS** | `qos/` | 各種QoSプロファイル |
| **Parameters** | `parameters/` | ノードパラメータ |
| **Launch** | `launch/` | ROS 2互換Launchシステム |
| **Logging** | `logging/` | ログレベル設定 |
| **Clock** | `clock/` | ROS Time/Sim Time |
| **Context** | `context/` | Domain ID設定 |
| **Guard Condition** | `guard_condition/` | スレッド間同期 |

---

## 🧪 テスト

```bash
# Ubuntu
python3 test/test_examples_ubuntu.py

# macOS
python3 test/test_examples_mac.py
```

---

## 🐛 トラブルシューティング

### `ModuleNotFoundError: std_msgs`

ランタイム同梱ホイールを使用するか、`bash scripts/install_ros_data_types.sh`を実行してください。

### `ImportError: libXxx.so`（ソースビルド時）

`LD_LIBRARY_PATH`に`/opt/fast-dds-v3-libs/lib`が含まれているか確認してください。

### DDSディスカバリに失敗する

- Domain IDが一致しているか確認
- ファイアウォールでUDPポート7400以降がブロックされていないか確認
- 同一ネットワーク上にいるか確認

### macOSで起動が遅い

macOSでは初回のDDSディスカバリに数秒かかることがあります。プロセス間通信の場合は、`time.sleep(1.0)`などで待機してください。

---

## 📄 ライセンス

- 本リポジトリ: Apache-2.0
- 生成コードにはeProsima Fast-DDSのテンプレートが含まれます
- rclpy互換レイヤーはApache-2.0（詳細は`rclpy/LICENSE`参照）

---

## 🙏 謝辞

- [eProsima Fast DDS](https://github.com/eProsima/Fast-DDS) - 高性能DDSミドルウェア
- [ROS 2](https://ros.org/) - ロボット開発フレームワーク
- [rclpy](https://github.com/ros2/rclpy) - 公式ROS 2 Pythonクライアントライブラリ
