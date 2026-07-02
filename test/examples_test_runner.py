#!/usr/bin/env python3
"""
Shared example test runner.

Runs all example scripts with sane timeouts, pairing publishers/listeners and
servers/clients where required. Optional examples (video, ML) are skipped
unless dependencies and assets are available.
"""

from __future__ import annotations

import os
import sys
import time
import signal
import threading
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
EXAMPLES_ROOT = PROJECT_ROOT / "examples"
ROS2_EXAMPLES_ROOT = PROJECT_ROOT / "third_party" / "ros2_examples" / "rclpy"

DEFAULT_PAIR_TIMEOUT = 20.0
DEFAULT_CLIENT_TIMEOUT = 45.0
DEFAULT_STANDALONE_TIMEOUT = 45.0
DDS_DISCOVERY_DELAY = 3.0
SERVER_READY_TIMEOUT = 20.0
ROS2_SERVER_READY_TIMEOUT = 30.0
LAUNCH_TIMEOUT = 20.0
LONG_RUNNING_SMOKE_TIMEOUT = 15.0
PROCESS_TERMINATE_GRACE = 5.0
PROCESS_KILL_GRACE = 2.0
ERROR_DETAIL_LIMIT = 4000


def _timeout_scale() -> float:
    raw = os.environ.get("LWRCLPY_TEST_TIMEOUT_SCALE", "1.0")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 1.0


def _timeout(seconds: float) -> float:
    return float(seconds) * _timeout_scale()


def _sleep(seconds: float) -> None:
    time.sleep(_timeout(seconds))


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}\n")


def print_test_start(name: str) -> None:
    print(f"\n{Colors.BOLD}Testing: {name}{Colors.RESET}")
    print("-" * 70)


def _display_symbol(symbol: str, fallback: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        symbol.encode(encoding)
        return symbol
    except UnicodeEncodeError:
        return fallback


def print_success(message: str) -> None:
    symbol = _display_symbol("✓", "OK")
    print(f"{Colors.GREEN}{symbol} {message}{Colors.RESET}")


def print_error(message: str) -> None:
    symbol = _display_symbol("✗", "X")
    print(f"{Colors.RED}{symbol} {message}{Colors.RESET}")


def print_warning(message: str) -> None:
    symbol = _display_symbol("⚠", "!")
    print(f"{Colors.YELLOW}{symbol} {message}{Colors.RESET}")


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _env_with_project() -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("LWRCLPY_AUTO_SHM_THRESHOLD", "1024")
    if env.get("LWRCLPY_TEST_USE_INSTALLED") == "1":
        return env
    pythonpath = env.get("PYTHONPATH", "")
    project_path = str(PROJECT_ROOT)
    if project_path not in pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = project_path + (os.pathsep + pythonpath if pythonpath else "")
    return env


class ProcessCapture:
    def __init__(self, command: Sequence[str], cwd: Optional[str] = None) -> None:
        if cwd is None:
            cwd = str(EXAMPLES_ROOT)
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.proc = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=_env_with_project(),
            bufsize=1,
            creationflags=creationflags,
        )
        self.stdout_lines: List[str] = []
        self.stderr_lines: List[str] = []
        self._output_lock = threading.Lock()
        self._stdout_thread = threading.Thread(
            target=self._read_stream, args=(self.proc.stdout, self.stdout_lines), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stream, args=(self.proc.stderr, self.stderr_lines), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _read_stream(self, stream, sink: List[str], limit: int = 2000) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                with self._output_lock:
                    sink.append(line)
                    if len(sink) > limit:
                        sink.pop(0)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def output(self) -> str:
        with self._output_lock:
            return "".join(self.stdout_lines + self.stderr_lines)

    def join_output(self, timeout: float = 1.0) -> None:
        for thread in (self._stdout_thread, self._stderr_thread):
            thread.join(timeout=timeout)

    def terminate(self, grace: float = PROCESS_TERMINATE_GRACE) -> None:
        if self.proc.poll() is not None:
            self.join_output(timeout=0.5)
            return
        try:
            if os.name == "nt":
                try:
                    self.proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    self.proc.terminate()
            else:
                self.proc.send_signal(signal.SIGINT)
        except Exception:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=_timeout(1.0 if os.name == "nt" else grace))
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=_timeout(PROCESS_KILL_GRACE))
            except subprocess.TimeoutExpired:
                pass
        self.join_output(timeout=0.5)


def _contains_error(output: str) -> bool:
    if "Traceback" in output:
        return True
    for marker in (
        "ModuleNotFoundError",
        "ImportError",
        "AttributeError",
        "SyntaxError",
        "RuntimeError",
        "ValueError",
        "TypeError",
        "Segmentation fault",
        "Aborted",
        "core dumped",
    ):
        if marker in output:
            return True
    return False


def _wait_for_keywords(proc: ProcessCapture, keywords: Sequence[str], timeout: float) -> bool:
    start = time.monotonic()
    effective_timeout = _timeout(timeout)
    required = tuple(keywords)
    while (time.monotonic() - start) < effective_timeout:
        output = proc.output()
        if all(keyword in output for keyword in required):
            return True
        if proc.proc.poll() is not None:
            return False
        time.sleep(0.05)
    return False


def _run_script(
    script: Path,
    timeout: float,
    expect_output: Optional[Sequence[str]] = None,
    allow_timeout: bool = False,
    args: Optional[Sequence[str]] = None,
) -> Tuple[bool, str]:
    command = [sys.executable, str(script)]
    if args:
        command.extend(args)
    proc = ProcessCapture(command)

    if allow_timeout:
        matched = True
        if expect_output:
            matched = _wait_for_keywords(proc, expect_output, timeout)
        else:
            _sleep(timeout)
        early_exit = proc.proc.poll() is not None and proc.proc.returncode not in (0, None)
        output = proc.output()
        proc.terminate()
        if early_exit or _contains_error(output):
            return False, output[:ERROR_DETAIL_LIMIT]
        if expect_output and not matched:
            return False, f"Expected output {list(expect_output)} not found"
        return True, output[:300] if output else "OK"

    try:
        proc.proc.wait(timeout=_timeout(timeout))
    except subprocess.TimeoutExpired:
        output = proc.output()
        proc.terminate()
        detail = output[:ERROR_DETAIL_LIMIT]
        return False, f"Timeout after {_timeout(timeout):.1f}s" + (f"\n{detail}" if detail else "")

    output = proc.output()
    if proc.proc.returncode not in (0, None):
        return False, output[:ERROR_DETAIL_LIMIT] or f"Process exited with code {proc.proc.returncode}"
    if _contains_error(output):
        return False, output[:ERROR_DETAIL_LIMIT]
    if expect_output and not any(k in output for k in expect_output):
        return False, f"Expected output {list(expect_output)} not found"
    return True, output[:300] if output else "OK"


def _run_pair(
    name: str,
    publisher: Path,
    subscriber: Path,
    subscriber_expect: Sequence[str],
    publisher_timeout: float = DEFAULT_PAIR_TIMEOUT,
    subscriber_timeout: float = DEFAULT_PAIR_TIMEOUT,
    publisher_args: Optional[Sequence[str]] = None,
    subscriber_args: Optional[Sequence[str]] = None,
) -> Tuple[bool, str]:
    print_test_start(name)
    sub = ProcessCapture([sys.executable, str(subscriber)] + list(subscriber_args or []))
    # Allow DDS discovery time between separate processes
    _sleep(DDS_DISCOVERY_DELAY)
    pub = ProcessCapture([sys.executable, str(publisher)] + list(publisher_args or []))

    matched = _wait_for_keywords(sub, subscriber_expect, subscriber_timeout)
    if sub.proc.poll() is not None:
        sub.join_output(timeout=1.0)
    if pub.proc.poll() is not None:
        pub.join_output(timeout=1.0)
    sub_output = sub.output()
    pub_output = pub.output()
    pub_returncode = pub.proc.poll()
    sub_returncode = sub.proc.poll()

    pub.terminate()
    sub.terminate()

    if _contains_error(pub_output) or _contains_error(sub_output):
        return False, (pub_output + sub_output)[:ERROR_DETAIL_LIMIT]
    if pub_returncode not in (0, None):
        return False, pub_output[:ERROR_DETAIL_LIMIT] or f"Publisher exited with code {pub_returncode}"
    if not matched:
        detail = (
            f"Subscriber output did not include {list(subscriber_expect)}\n"
            f"Publisher return code: {pub_returncode}\n"
            f"Subscriber return code: {sub_returncode}\n"
            f"Publisher output:\n{pub_output or '<empty>'}\n"
            f"Subscriber output:\n{sub_output or '<empty>'}"
        )
        return False, detail[:ERROR_DETAIL_LIMIT]
    return True, "OK"


@dataclass(frozen=True)
class PairSpec:
    name: str
    publisher: str
    subscriber: str
    subscriber_expect: Tuple[str, ...]
    publisher_timeout: float = DEFAULT_PAIR_TIMEOUT
    subscriber_timeout: float = DEFAULT_PAIR_TIMEOUT
    publisher_args: Tuple[str, ...] = ()
    subscriber_args: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ServerClientSpec:
    name: str
    server: str
    clients: Tuple[str, ...]
    client_expect: Tuple[str, ...]
    client_timeout: float = DEFAULT_CLIENT_TIMEOUT
    server_ready: Tuple[str, ...] = ()
    attempts: int = 1


def _skip_reason(script: Path) -> Optional[str]:
    rel = script.relative_to(PROJECT_ROOT)
    if rel.name.endswith("_benchmark.py") and os.environ.get("LWRCLPY_TEST_BENCHMARKS") != "1":
        return "benchmark examples disabled (set LWRCLPY_TEST_BENCHMARKS=1 to run)"
    if rel.parts[:2] == ("examples", "cuda_ipc"):
        if os.environ.get("LWRCLPY_TEST_CUDA_IPC") != "1":
            return "CUDA IPC examples disabled (set LWRCLPY_TEST_CUDA_IPC=1 on CUDA hosts)"
        if not (_module_available("cupy") or _module_available("cuda")):
            return "CUDA IPC examples require CuPy or cuda-python"
    if rel.parts[:2] == ("examples", "video"):
        if os.environ.get("LWRCLPY_TEST_VIDEO") != "1":
            return "video examples disabled (set LWRCLPY_TEST_VIDEO=1 and provide assets)"
        if not _module_available("cv2") or not _module_available("numpy"):
            return "video examples require cv2 and numpy"
        video_file = os.environ.get("LWRCLPY_TEST_VIDEO_FILE")
        if not video_file or not Path(video_file).exists():
            return "video examples require LWRCLPY_TEST_VIDEO_FILE pointing to a readable file"
        if rel.name in {"video_yolo.py", "video_yolo_detector.py"}:
            if not _module_available("ultralytics"):
                return "YOLO examples require ultralytics"
            if not _module_available("torch"):
                return "YOLO examples require torch"
        return None
    if rel.parts[:3] == ("examples", "pubsub", "ml"):
        if not _module_available("torch"):
            return "ML examples require torch"
    return None


def run_all_examples(platform_name: str) -> bool:
    print_header(f"lwrclpy Examples Test Suite ({platform_name})")
    print(f"Python: {sys.version}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Timeout scale: {_timeout_scale():.1f}x")
    print(f"Working directory: /tmp\n")

    results: List[Tuple[str, bool, str]] = []
    skipped: List[Tuple[str, str]] = []
    skipped_paths: set[Path] = set()
    handled: set[Path] = set()

    # Basic import test
    print_test_start("Import Test")
    try:
        import lwrclpy  # noqa: F401
        from std_msgs.msg import String  # noqa: F401
        from sensor_msgs.msg import Image  # noqa: F401
        from geometry_msgs.msg import Pose  # noqa: F401
        print_success("lwrclpy and message types imported successfully")
        results.append(("import_test", True, "OK"))
    except Exception as exc:
        print_error(f"Import failed: {exc}")
        results.append(("import_test", False, str(exc)))
        return False

    pair_specs = (
        PairSpec(
            name="Pub/Sub string",
            publisher="examples/pubsub/string/talker.py",
            subscriber="examples/pubsub/string/listener.py",
            subscriber_expect=("[recv]",),
        ),
        PairSpec(
            name="Pub/Sub sensor_qos",
            publisher="examples/pubsub/sensor_qos/talker.py",
            subscriber="examples/pubsub/sensor_qos/listener.py",
            subscriber_expect=("[recv]",),
        ),
        PairSpec(
            name="Pub/Sub zero_copy",
            publisher="examples/pubsub/zero_copy/zero_copy_publisher.py",
            subscriber="examples/pubsub/zero_copy/callback_subscriber.py",
            subscriber_expect=("Callback Subscription Demo", "Message"),
        ),
        PairSpec(
            name="Shared memory image",
            publisher="examples/shared_memory/image_shared_memory_publisher.py",
            subscriber="examples/shared_memory/image_shared_memory_subscriber.py",
            subscriber_expect=("[recv]", "shared_memory=True"),
            publisher_args=("--width", "64", "--height", "48", "--rate", "20"),
            subscriber_args=("--read-byte",),
        ),
        PairSpec(
            name="Shared memory image (data_buffer)",
            publisher="examples/shared_memory/image_shared_memory_publisher.py",
            subscriber="examples/shared_memory/image_shared_memory_subscriber.py",
            subscriber_expect=("[recv]", "shared_memory=True"),
            publisher_args=("--width", "64", "--height", "48", "--rate", "20", "--data-buffer"),
            subscriber_args=("--read-byte",),
        ),
        PairSpec(
            name="Typed messages (geometry)",
            publisher="examples/pubsub/typed_messages/geometry_publisher.py",
            subscriber="examples/pubsub/typed_messages/geometry_subscriber.py",
            subscriber_expect=("[Point]", "[Pose]", "[Twist]", "[PoseStamped]"),
        ),
        PairSpec(
            name="Typed messages (sensor)",
            publisher="examples/pubsub/typed_messages/sensor_publisher.py",
            subscriber="examples/pubsub/typed_messages/sensor_subscriber.py",
            subscriber_expect=("[LaserScan]", "[IMU]", "[Range]", "[Temperature]"),
        ),
        PairSpec(
            name="Timers (wall_timer)",
            publisher="examples/timers/wall_timer.py",
            subscriber="examples/timers/wall_timer_listener.py",
            subscriber_expect=("[timer recv]",),
        ),
        PairSpec(
            name="Timers (oneshot + periodic)",
            publisher="examples/timers/oneshot_and_periodic.py",
            subscriber="examples/timers/oneshot_and_periodic_listener.py",
            subscriber_expect=("[combo recv]",),
        ),
    )

    ml_pair = PairSpec(
        name="Pub/Sub ML",
        publisher="examples/pubsub/ml/talker.py",
        subscriber="examples/pubsub/ml/listener.py",
        subscriber_expect=("[recv]", "score="),
    )

    server_client_specs = (
        ServerClientSpec(
            name="Service SetBool",
            server="examples/services/set_bool/server.py",
            clients=("examples/services/set_bool/client.py",),
            client_expect=("response", "success="),
            server_ready=("Starting SetBool server",),
        ),
        ServerClientSpec(
            name="Service Trigger",
            server="examples/services/trigger/trigger_server.py",
            clients=("examples/services/trigger/trigger_client.py",),
            client_expect=("Demo Complete", "Result:"),
            client_timeout=90.0,
            server_ready=("Services available",),
        ),
        ServerClientSpec(
            name="Actions (Fibonacci + Advanced)",
            server="examples/actions/fibonacci_action_server.py",
            clients=(
                "examples/actions/fibonacci_action_client.py",
                "examples/actions/advanced_action_client.py",
            ),
            client_expect=("Result:", "Demo Complete"),
            client_timeout=90.0,
            server_ready=("Action Server", "action server"),
        ),
    )

    # ROS 2 official examples (third_party/ros2_examples)
    ros2_pair_specs = (
        PairSpec(
            name="ROS2 Minimal Pub/Sub (member_function)",
            publisher="third_party/ros2_examples/rclpy/topics/minimal_publisher/examples_rclpy_minimal_publisher/publisher_member_function.py",
            subscriber="third_party/ros2_examples/rclpy/topics/minimal_subscriber/examples_rclpy_minimal_subscriber/subscriber_member_function.py",
            subscriber_expect=("I heard:",),
        ),
        PairSpec(
            name="ROS2 Minimal Pub/Sub (old_school)",
            publisher="third_party/ros2_examples/rclpy/topics/minimal_publisher/examples_rclpy_minimal_publisher/publisher_old_school.py",
            subscriber="third_party/ros2_examples/rclpy/topics/minimal_subscriber/examples_rclpy_minimal_subscriber/subscriber_old_school.py",
            subscriber_expect=("I heard:",),
        ),
        PairSpec(
            name="ROS2 Minimal Pub/Sub (local_function)",
            publisher="third_party/ros2_examples/rclpy/topics/minimal_publisher/examples_rclpy_minimal_publisher/publisher_local_function.py",
            subscriber="third_party/ros2_examples/rclpy/topics/minimal_subscriber/examples_rclpy_minimal_subscriber/subscriber_lambda.py",
            subscriber_expect=("I heard:",),
        ),
    )

    ros2_server_client_specs = (
        ServerClientSpec(
            name="ROS2 Minimal Service (AddTwoInts)",
            server="third_party/ros2_examples/rclpy/services/minimal_service/examples_rclpy_minimal_service/service_member_function.py",
            clients=("third_party/ros2_examples/rclpy/services/minimal_client/examples_rclpy_minimal_client/client_async_member_function.py",),
            client_expect=("Result of add_two_ints:", "42"),
            server_ready=(),
        ),
        ServerClientSpec(
            name="ROS2 Minimal Action (Fibonacci)",
            server="third_party/ros2_examples/rclpy/actions/minimal_action_server/examples_rclpy_minimal_action_server/server.py",
            clients=("third_party/ros2_examples/rclpy/actions/minimal_action_client/examples_rclpy_minimal_action_client/client.py",),
            client_expect=("Goal succeeded!", "Result:"),
            client_timeout=300.0,
            server_ready=(),
            attempts=2,
        ),
    )

    # Pair tests
    for spec in pair_specs:
        pub = PROJECT_ROOT / spec.publisher
        sub = PROJECT_ROOT / spec.subscriber
        handled.update({pub, sub})
        skip_reason = _skip_reason(pub) or _skip_reason(sub)
        if skip_reason:
            skipped.append((spec.name, skip_reason))
            skipped_paths.update({pub, sub})
            print_warning(f"{spec.name} skipped: {skip_reason}")
            continue
        success, output = _run_pair(
            name=spec.name,
            publisher=pub,
            subscriber=sub,
            subscriber_expect=spec.subscriber_expect,
            publisher_timeout=spec.publisher_timeout,
            subscriber_timeout=spec.subscriber_timeout,
            publisher_args=spec.publisher_args,
            subscriber_args=spec.subscriber_args,
        )
        results.append((spec.name, success, output))
        if success:
            print_success(f"{spec.name} - OK")
        else:
            print_error(f"{spec.name} - FAILED")
            print(f"  {output}")

    # Optional ML pair
    ml_pub = PROJECT_ROOT / ml_pair.publisher
    ml_sub = PROJECT_ROOT / ml_pair.subscriber
    handled.update({ml_pub, ml_sub})
    ml_skip = _skip_reason(ml_pub) or _skip_reason(ml_sub)
    if ml_skip:
        skipped.append((ml_pair.name, ml_skip))
        skipped_paths.update({ml_pub, ml_sub})
        print_warning(f"{ml_pair.name} skipped: {ml_skip}")
    else:
        success, output = _run_pair(
            name=ml_pair.name,
            publisher=ml_pub,
            subscriber=ml_sub,
            subscriber_expect=ml_pair.subscriber_expect,
            publisher_timeout=ml_pair.publisher_timeout,
            subscriber_timeout=ml_pair.subscriber_timeout,
        )
        results.append((ml_pair.name, success, output))
        if success:
            print_success(f"{ml_pair.name} - OK")
        else:
            print_error(f"{ml_pair.name} - FAILED")
            print(f"  {output}")

    # ROS 2 official examples - Pair tests
    print_header("ROS 2 Official Examples (third_party/ros2_examples)")
    for spec in ros2_pair_specs:
        pub = PROJECT_ROOT / spec.publisher
        sub = PROJECT_ROOT / spec.subscriber
        handled.update({pub, sub})
        if not pub.exists() or not sub.exists():
            skipped.append((spec.name, "ROS 2 example files not found"))
            print_warning(f"{spec.name} skipped: files not found")
            continue
        success, output = _run_pair(
            name=spec.name,
            publisher=pub,
            subscriber=sub,
            subscriber_expect=spec.subscriber_expect,
            publisher_timeout=spec.publisher_timeout,
            subscriber_timeout=spec.subscriber_timeout,
            publisher_args=spec.publisher_args,
            subscriber_args=spec.subscriber_args,
        )
        results.append((spec.name, success, output))
        if success:
            print_success(f"{spec.name} - OK")
        else:
            print_error(f"{spec.name} - FAILED")
            print(f"  {output}")

    # ROS 2 official examples - Server/client tests
    for spec in ros2_server_client_specs:
        server_path = PROJECT_ROOT / spec.server
        handled.add(server_path)
        client_paths = [PROJECT_ROOT / c for c in spec.clients]
        handled.update(client_paths)
        if not server_path.exists():
            skipped.append((spec.name, "ROS 2 server file not found"))
            print_warning(f"{spec.name} skipped: server not found")
            continue

        print_test_start(spec.name)
        server_output = ""
        overall_ok = False
        for attempt in range(1, max(1, spec.attempts) + 1):
            if attempt > 1:
                print_warning(f"{spec.name} retrying attempt {attempt}/{spec.attempts}")
            server_proc = ProcessCapture([sys.executable, str(server_path)])
            # Allow DDS discovery time between separate processes
            if spec.server_ready:
                _wait_for_keywords(server_proc, spec.server_ready, timeout=ROS2_SERVER_READY_TIMEOUT)
            else:
                _sleep(DDS_DISCOVERY_DELAY)

            attempt_output = ""
            attempt_ok = True
            for client_path in client_paths:
                if not client_path.exists():
                    skipped.append((client_path.relative_to(PROJECT_ROOT).as_posix(), "file not found"))
                    print_warning(f"{client_path} skipped: not found")
                    continue
                ok, output = _run_script(
                    client_path,
                    timeout=spec.client_timeout,
                    expect_output=spec.client_expect,
                )
                if not ok:
                    attempt_ok = False
                    attempt_output = output
                    break

            server_proc.terminate()
            attempt_output = (attempt_output + server_proc.output())[:500]
            if _contains_error(attempt_output):
                server_output = attempt_output
                overall_ok = False
                break
            if attempt_ok:
                server_output = attempt_output or "OK"
                overall_ok = True
                break
            server_output = attempt_output
        results.append((spec.name, overall_ok, server_output or "OK"))
        if overall_ok:
            print_success(f"{spec.name} - OK")
        else:
            print_error(f"{spec.name} - FAILED")
            print(f"  {server_output}")

    # Server/client tests (original lwrclpy examples)
    for spec in server_client_specs:
        server_path = PROJECT_ROOT / spec.server
        handled.add(server_path)
        client_paths = [PROJECT_ROOT / c for c in spec.clients]
        handled.update(client_paths)
        skip_reason = _skip_reason(server_path)
        if skip_reason:
            skipped.append((spec.name, skip_reason))
            skipped_paths.add(server_path)
            print_warning(f"{spec.name} skipped: {skip_reason}")
            continue

        print_test_start(spec.name)
        server_proc = ProcessCapture([sys.executable, str(server_path)])
        # Allow DDS discovery time between separate processes
        if spec.server_ready:
            _wait_for_keywords(server_proc, spec.server_ready, timeout=SERVER_READY_TIMEOUT)
        else:
            _sleep(DDS_DISCOVERY_DELAY)

        server_output = ""
        overall_ok = True
        for client_path in client_paths:
            client_skip = _skip_reason(client_path)
            if client_skip:
                skipped.append((client_path.relative_to(PROJECT_ROOT).as_posix(), client_skip))
                skipped_paths.add(client_path)
                print_warning(f"{client_path} skipped: {client_skip}")
                continue
            ok, output = _run_script(
                client_path,
                timeout=spec.client_timeout,
                expect_output=spec.client_expect,
            )
            if not ok:
                overall_ok = False
                server_output = output
                break

        server_proc.terminate()
        server_output = (server_output + server_proc.output())[:500]
        if _contains_error(server_output):
            overall_ok = False
        results.append((spec.name, overall_ok, server_output or "OK"))
        if overall_ok:
            print_success(f"{spec.name} - OK")
        else:
            print_error(f"{spec.name} - FAILED")
            print(f"  {server_output}")

    # Standalone examples (everything else)
    platform_key = platform_name.lower()
    is_macos = platform_key.startswith("mac") or sys.platform == "darwin"
    standalone_timeouts: dict[Path, float] = {}
    if is_macos:
        # macOS can take longer for service discovery in this example.
        standalone_timeouts[PROJECT_ROOT / "examples/services/trigger_bridge/bridge.py"] = 90.0

    long_running = {
        PROJECT_ROOT / "examples/executor/multithreaded_spin.py",
        PROJECT_ROOT / "examples/pubsub/multi_pubsub.py",
        PROJECT_ROOT / "examples/pubsub/typed_messages/navigation_demo.py",
        PROJECT_ROOT / "examples/node/class_based_node.py",
        PROJECT_ROOT / "examples/services/advanced_client.py",
        PROJECT_ROOT / "examples/executor/multithreaded_executor_demo.py",
    }
    long_running_expectations = {
        PROJECT_ROOT / "examples/executor/multithreaded_executor_demo.py": ("Received:",),
    }

    # Launch examples - these are self-terminating
    launch_specs = (
        ("Launch: minimal_pubsub", "examples/launch/minimal_pubsub.launch.py", ("process started",)),
        ("Launch: node_with_params", "examples/launch/node_with_params.launch.py", ("process started",)),
        ("Launch: substitutions", "examples/launch/substitutions.launch.py", ("Robot name:", "robot1")),
        ("Launch: conditional (default)", "examples/launch/conditional.launch.py", ("Debug mode enabled", "REAL mode")),
        ("Launch: environment", "examples/launch/environment.launch.py", ("Log level:",)),
        ("Launch: opaque_function", "examples/launch/opaque_function.launch.py", ("Creating", "robots")),
        ("Launch: include_launch", "examples/launch/include_launch.launch.py", ("Including", "process started")),
        ("Launch: timer_action", "examples/launch/timer_action.launch.py", ("process started",)),
        ("Launch: multi_robot", "examples/launch/multi_robot.launch.py", ("Multi-robot", "robot0", "robot1")),
    )

    print_header("Launch Examples")
    for name, script_path, expect in launch_specs:
        script = PROJECT_ROOT / script_path
        handled.add(script)
        if not script.exists():
            skipped.append((name, "file not found"))
            print_warning(f"{name} skipped: file not found")
            continue
        print_test_start(name)
        # Launch files run indefinitely, so use allow_timeout=True
        ok, output = _run_script(script, timeout=LAUNCH_TIMEOUT, expect_output=expect, allow_timeout=True)
        results.append((name, ok, output))
        if ok:
            print_success(f"{name} - OK")
        else:
            print_error(f"{name} - FAILED")
            print(f"  {output}")

    for script in sorted(EXAMPLES_ROOT.rglob("*.py")):
        if script in handled:
            continue
        skip_reason = _skip_reason(script)
        rel = script.relative_to(PROJECT_ROOT)
        if skip_reason:
            skipped.append((rel.as_posix(), skip_reason))
            skipped_paths.add(script)
            print_warning(f"{rel} skipped: {skip_reason}")
            continue

        handled.add(script)
        print_test_start(rel.as_posix())

        if script in long_running:
            ok, output = _run_script(
                script,
                timeout=LONG_RUNNING_SMOKE_TIMEOUT,
                expect_output=long_running_expectations.get(script),
                allow_timeout=True,
            )
        else:
            timeout = standalone_timeouts.get(script, DEFAULT_STANDALONE_TIMEOUT)
            ok, output = _run_script(script, timeout=timeout)

        results.append((rel.as_posix(), ok, output))
        if ok:
            print_success(f"{rel} - OK")
        else:
            print_error(f"{rel} - FAILED")
            print(f"  {output}")

    # Ensure we covered all examples (even if skipped)
    all_examples = set(EXAMPLES_ROOT.rglob("*.py"))
    uncovered = all_examples - handled - skipped_paths
    if uncovered:
        for script in sorted(uncovered):
            rel = script.relative_to(PROJECT_ROOT)
            results.append((rel.as_posix(), False, "Not covered by test runner"))
            print_error(f"{rel} - NOT COVERED")

    # Summary
    print_header("Test Summary")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    print(f"Total tests: {total}")
    print(f"{Colors.GREEN}Passed: {passed}{Colors.RESET}")
    print(f"{Colors.RED}Failed: {failed}{Colors.RESET}")
    print(f"Success rate: {passed / total * 100:.1f}%\n")

    if skipped:
        print(f"{Colors.YELLOW}Skipped examples:{Colors.RESET}")
        for name, reason in skipped:
            print(f"  - {name}: {reason}")
        print()

    if failed > 0:
        print(f"{Colors.RED}Failed tests:{Colors.RESET}")
        for name, ok, _ in results:
            if not ok:
                print(f"  - {name}")
        print()
        return False

    print_success("All tests passed! ✨")
    return True


def main(platform_name: str) -> int:
    ok = run_all_examples(platform_name)
    return 0 if ok else 1
