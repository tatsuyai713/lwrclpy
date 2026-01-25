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


def print_success(message: str) -> None:
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message: str) -> None:
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def print_warning(message: str) -> None:
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _env_with_project() -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    pythonpath = env.get("PYTHONPATH", "")
    project_path = str(PROJECT_ROOT)
    if project_path not in pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = project_path + (os.pathsep + pythonpath if pythonpath else "")
    return env


class ProcessCapture:
    def __init__(self, command: Sequence[str], cwd: str = "/tmp") -> None:
        self.proc = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=_env_with_project(),
            bufsize=1,
        )
        self.stdout_lines: List[str] = []
        self.stderr_lines: List[str] = []
        self._stdout_thread = threading.Thread(
            target=self._read_stream, args=(self.proc.stdout, self.stdout_lines), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stream, args=(self.proc.stderr, self.stderr_lines), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    @staticmethod
    def _read_stream(stream, sink: List[str], limit: int = 2000) -> None:
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            sink.append(line)
            if len(sink) > limit:
                sink.pop(0)

    def output(self) -> str:
        return "".join(self.stdout_lines + self.stderr_lines)

    def terminate(self, grace: float = 2.0) -> None:
        if self.proc.poll() is not None:
            return
        try:
            self.proc.send_signal(signal.SIGINT)
        except Exception:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass


def _contains_error(output: str) -> bool:
    if "Traceback" in output:
        return True
    for marker in ("ModuleNotFoundError", "ImportError", "AttributeError", "SyntaxError"):
        if marker in output:
            return True
    return False


def _wait_for_keywords(proc: ProcessCapture, keywords: Sequence[str], timeout: float) -> bool:
    start = time.monotonic()
    while (time.monotonic() - start) < timeout:
        output = proc.output()
        if any(keyword in output for keyword in keywords):
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
            time.sleep(timeout)
        early_exit = proc.proc.poll() is not None and proc.proc.returncode not in (0, None)
        output = proc.output()
        proc.terminate()
        if early_exit or _contains_error(output):
            return False, output[:500]
        if expect_output and not matched:
            return False, f"Expected output {list(expect_output)} not found"
        return True, output[:300] if output else "OK"

    try:
        proc.proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        output = proc.output()
        proc.terminate()
        return False, "Timeout"

    output = proc.output()
    if _contains_error(output):
        return False, output[:500]
    if expect_output and not any(k in output for k in expect_output):
        return False, f"Expected output {list(expect_output)} not found"
    return True, output[:300] if output else "OK"


def _run_pair(
    name: str,
    publisher: Path,
    subscriber: Path,
    subscriber_expect: Sequence[str],
    publisher_timeout: float = 10.0,
    subscriber_timeout: float = 10.0,
    publisher_args: Optional[Sequence[str]] = None,
    subscriber_args: Optional[Sequence[str]] = None,
) -> Tuple[bool, str]:
    print_test_start(name)
    sub = ProcessCapture([sys.executable, str(subscriber)] + list(subscriber_args or []))
    # Allow DDS discovery time between separate processes
    time.sleep(1.5)
    pub = ProcessCapture([sys.executable, str(publisher)] + list(publisher_args or []))

    pub_done = False
    try:
        pub.proc.wait(timeout=publisher_timeout)
        pub_done = True
    except subprocess.TimeoutExpired:
        pass

    matched = _wait_for_keywords(sub, subscriber_expect, subscriber_timeout)
    sub_output = sub.output()
    pub_output = pub.output()

    pub.terminate()
    sub.terminate()

    if _contains_error(pub_output) or _contains_error(sub_output):
        return False, (pub_output + sub_output)[:500]
    if not matched:
        return False, f"Subscriber output did not include {list(subscriber_expect)}"
    if not pub_done:
        # publisher is allowed to be long-running; not a failure
        return True, "Publisher running; subscriber received messages"
    return True, "OK"


@dataclass(frozen=True)
class PairSpec:
    name: str
    publisher: str
    subscriber: str
    subscriber_expect: Tuple[str, ...]
    publisher_timeout: float = 10.0
    subscriber_timeout: float = 10.0
    publisher_args: Tuple[str, ...] = ()
    subscriber_args: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ServerClientSpec:
    name: str
    server: str
    clients: Tuple[str, ...]
    client_expect: Tuple[str, ...]
    client_timeout: float = 15.0
    server_ready: Tuple[str, ...] = ()


def _skip_reason(script: Path) -> Optional[str]:
    rel = script.relative_to(PROJECT_ROOT)
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
            publisher_timeout=8.0,
            subscriber_timeout=8.0,
        ),
        PairSpec(
            name="Pub/Sub sensor_qos",
            publisher="examples/pubsub/sensor_qos/talker.py",
            subscriber="examples/pubsub/sensor_qos/listener.py",
            subscriber_expect=("[recv]",),
            publisher_timeout=6.0,
            subscriber_timeout=6.0,
        ),
        PairSpec(
            name="Pub/Sub zero_copy",
            publisher="examples/pubsub/zero_copy/loan_message_publisher.py",
            subscriber="examples/pubsub/zero_copy/polling_subscriber.py",
            subscriber_expect=("Polling Subscription", "take()"),
            publisher_timeout=8.0,
            subscriber_timeout=8.0,
        ),
        PairSpec(
            name="Typed messages (geometry)",
            publisher="examples/pubsub/typed_messages/geometry_publisher.py",
            subscriber="examples/pubsub/typed_messages/geometry_subscriber.py",
            subscriber_expect=("[Point]", "[Pose]", "[Twist]", "[PoseStamped]"),
            publisher_timeout=8.0,
            subscriber_timeout=8.0,
        ),
        PairSpec(
            name="Typed messages (sensor)",
            publisher="examples/pubsub/typed_messages/sensor_publisher.py",
            subscriber="examples/pubsub/typed_messages/sensor_subscriber.py",
            subscriber_expect=("[LaserScan]", "[IMU]", "[Range]", "[Temperature]"),
            publisher_timeout=8.0,
            subscriber_timeout=8.0,
        ),
        PairSpec(
            name="Timers (wall_timer)",
            publisher="examples/timers/wall_timer.py",
            subscriber="examples/timers/wall_timer_listener.py",
            subscriber_expect=("[timer recv]",),
            publisher_timeout=8.0,
            subscriber_timeout=8.0,
        ),
        PairSpec(
            name="Timers (oneshot + periodic)",
            publisher="examples/timers/oneshot_and_periodic.py",
            subscriber="examples/timers/oneshot_and_periodic_listener.py",
            subscriber_expect=("[combo recv]",),
            publisher_timeout=8.0,
            subscriber_timeout=8.0,
        ),
    )

    ml_pair = PairSpec(
        name="Pub/Sub ML",
        publisher="examples/pubsub/ml/talker.py",
        subscriber="examples/pubsub/ml/listener.py",
        subscriber_expect=("[recv]", "score="),
        publisher_timeout=10.0,
        subscriber_timeout=10.0,
    )

    server_client_specs = (
        ServerClientSpec(
            name="Service SetBool",
            server="examples/services/set_bool/server.py",
            clients=("examples/services/set_bool/client.py",),
            client_expect=("response", "success="),
            client_timeout=20.0,
            server_ready=("Starting SetBool server",),
        ),
        ServerClientSpec(
            name="Service Trigger",
            server="examples/services/trigger/trigger_server.py",
            clients=("examples/services/trigger/trigger_client.py",),
            client_expect=("Demo Complete", "Result:"),
            client_timeout=60.0,
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
            client_timeout=45.0,
            server_ready=("Action Server", "action server"),
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

    # Server/client tests
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
            _wait_for_keywords(server_proc, spec.server_ready, timeout=5.0)
        else:
            time.sleep(5.0)

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
    long_running = {
        PROJECT_ROOT / "examples/executor/multithreaded_spin.py",
        PROJECT_ROOT / "examples/pubsub/multi_pubsub.py",
        PROJECT_ROOT / "examples/pubsub/typed_messages/navigation_demo.py",
        PROJECT_ROOT / "examples/node/class_based_node.py",
        PROJECT_ROOT / "examples/services/advanced_client.py",
    }

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
            ok, output = _run_script(script, timeout=6.0, allow_timeout=True)
        else:
            ok, output = _run_script(script, timeout=20.0)

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
