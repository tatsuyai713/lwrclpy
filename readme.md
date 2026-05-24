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
| **ゼロコピー通信** | ✅ DataSharing/SHMを内部利用 | ⚠️ Python公開loan APIなし | アプリ側は標準 `publish(msg)` を使用 |
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
| **ゼロコピー** | ✅ Fast DDS DataSharing | ⚠️ rmw依存、rclpy loan APIなし | アプリコードを変えずに大型メッセージで効果 |
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

### ゼロコピー向け通信

移植可能なrclpy互換コードでは、標準のpublish APIを使います。

```python
msg = Image()
msg.data = large_data
publisher.publish(msg)
```

lwrclpyは利用可能な場合にFast DDS DataSharing/SHMを内部で有効化します。ROS 2
`rclpy`には公開された`loan_message()` APIがないため、移植可能なコードでは標準の
`publish(msg)` APIを使います。

### lwrclpy拡張: DataSharing Zero-Copyの検証

lwrclpyは、Fast DDS Python APIが対応している場合にwriter/reader QoSのDataSharingを
明示的にONにします。lwrclpyに依存してよいコードでは、`zero_copy_enabled`拡張
プロパティでその状態を検証できます。

```python
assert publisher.zero_copy_enabled
assert subscription.zero_copy_enabled

msg = Image()
msg.data = large_data
publisher.publish(msg)
```

publish/subscribe APIはrclpy互換のままで、`zero_copy_enabled`だけがlwrclpy独自の
検証用フックです。ビルド済みwheelで対応済みのzero-copy経路はDataSharing/SHMです。

`Publisher.loan_message(require_zero_copy=True)`も実験的なlwrclpy拡張として実装しています。
これはFast-DDS-pythonを`scripts/patch_fastdds_python_loan_helpers.py`適用後に再ビルドし、
生成メッセージbindingを`scripts/patch_fastdds_swig_v3.py`適用後に再生成した場合に有効になります。
これらのpatchは`loan_sample(void*&)`用のaddress helperと、addressから型付きメッセージwrapperへ
戻すhelperを追加します。再ビルド済みhelperがない場合、`can_loan_messages`は`False`のままで、
loaned sampleが使えるようには見せません。

現在の環境で拡張APIが使えるか確認するには、次を実行します。

```bash
python3 examples/lwrclpy_extensions/zero_copy_extension_publisher.py --require-zero-copy
```

Fast-DDS-pythonと生成メッセージbindingをloan helper patch込みで再ビルドした後は、
実験的なloaned-message経路を次のように確認できます。

```bash
python3 examples/lwrclpy_extensions/zero_copy_extension_publisher.py --require-zero-copy --require-loaned-message
```

Fast DDS DataSharingを有効化できない場合、このコマンドはzero-copy使用を装わずに失敗します。

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
