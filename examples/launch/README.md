# Launch Examples

ROS 2スタイルのLaunchファイルの例です。
ROS 2のLaunchフレームワークとAPI互換になっています。

## 例の一覧

| ファイル | 説明 |
|---------|------|
| [minimal_pubsub.launch.py](minimal_pubsub.launch.py) | 最小限のpub/sub |
| [node_with_params.launch.py](node_with_params.launch.py) | パラメータ付きノード |
| [conditional.launch.py](conditional.launch.py) | 条件付き起動 |
| [substitutions.launch.py](substitutions.launch.py) | 各種Substitution |
| [environment.launch.py](environment.launch.py) | 環境変数 |
| [opaque_function.launch.py](opaque_function.launch.py) | 動的構成 |
| [include_launch.launch.py](include_launch.launch.py) | 他のlaunchファイルのinclude |
| [timer_action.launch.py](timer_action.launch.py) | 遅延起動 |
| [multi_robot.launch.py](multi_robot.launch.py) | 複数ロボット（名前空間） |

## 使用方法

```bash
# 最小限の例
python3 examples/launch/minimal_pubsub.launch.py

# 引数付き
python3 examples/launch/minimal_pubsub.launch.py topic:=/my_topic

# 条件付き
python3 examples/launch/conditional.launch.py use_sim:=true

# 複数ロボット
python3 examples/launch/multi_robot.launch.py num_robots:=3
```

## ROS 2互換API

### サポートされているActions

| Action | 説明 |
|--------|------|
| `Node` | ノードの起動 |
| `DeclareLaunchArgument` | 引数の宣言 |
| `ExecuteProcess` | プロセスの実行 |
| `GroupAction` | アクションのグループ化 |
| `IncludeLaunchDescription` | 他のlaunchファイルの読み込み |
| `LogInfo` | ログ出力 |
| `SetEnvironmentVariable` | 環境変数の設定 |
| `TimerAction` | 遅延実行 |
| `OpaqueFunction` | 動的アクション生成 |
| `SetLaunchConfiguration` | launch configの設定 |
| `Shutdown` | シャットダウン |
| `PushRosNamespace` | 名前空間のプッシュ |
| `SetParameter` | パラメータの設定 |

### サポートされているSubstitutions

| Substitution | 説明 |
|--------------|------|
| `LaunchConfiguration` | launch引数の参照 |
| `EnvironmentVariable` | 環境変数の参照 |
| `TextSubstitution` | 固定テキスト |
| `PathJoinSubstitution` | パスの結合 |
| `PythonExpression` | Python式の評価 |
| `FindExecutable` | 実行ファイルの検索 |
| `Command` | コマンド実行結果 |
| `ThisLaunchFile` / `ThisLaunchFileDir` | 現在のlaunchファイル |

### サポートされているConditions

| Condition | 説明 |
|-----------|------|
| `IfCondition` | 真の場合に実行 |
| `UnlessCondition` | 偽の場合に実行 |
| `LaunchConfigurationEquals` | 値の一致判定 |
| `LaunchConfigurationNotEquals` | 値の不一致判定 |

## ROS 2との互換性

lwrclpyのLaunchシステムはROS 2のLaunchフレームワークとAPI互換です。
ROS 2用に書かれたLaunchファイルは、ほとんど変更なしで動作します。

**注意**: 以下の機能は未サポートです：
- `launch_testing` フレームワーク
- `ComposableNodeContainer` (コンポーネントノード)
- 完全なイベントシステム（部分サポート）
