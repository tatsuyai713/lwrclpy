#!/usr/bin/env python3
"""Overlay current Python sources into an existing wheel and refresh RECORD."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import tempfile
import zipfile


PACKAGE_DIRS = (
    "lwrclpy",
    "rclpy",
    "tf2_py",
    "tf2_ros",
    "launch",
    "launch_ros",
)


def _hash_record(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}", str(len(data))


def _format_record(rows: list[tuple[str, str, str]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _source_files(source_root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for package in PACKAGE_DIRS:
        root = source_root / package
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(source_root).as_posix()
            files[rel] = path
    return files


def overlay_wheel(wheel: Path, source_root: Path) -> None:
    source_by_name = _source_files(source_root)
    with zipfile.ZipFile(wheel, "r") as zin:
        entries = {info.filename: zin.read(info.filename) for info in zin.infolist() if not info.is_dir()}
        record_names = [name for name in entries if name.endswith(".dist-info/RECORD")]
        if len(record_names) != 1:
            raise RuntimeError(f"Expected exactly one RECORD in {wheel}, found {record_names}")
        record_name = record_names[0]

    for name, path in source_by_name.items():
        if name in entries:
            entries[name] = path.read_bytes()

    rows: list[tuple[str, str, str]] = []
    for name in sorted(n for n in entries if n != record_name):
        digest, size = _hash_record(entries[name])
        rows.append((name, digest, size))
    rows.append((record_name, "", ""))
    entries[record_name] = _format_record(rows)

    fd, tmp_name = tempfile.mkstemp(prefix=wheel.name, suffix=".tmp", dir=str(wheel.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in sorted(entries):
                zout.writestr(name, entries[name])
        tmp_path.replace(wheel)
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheels", nargs="+", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    for wheel in args.wheels:
        overlay_wheel(wheel.resolve(), source_root)
        print(f"[OK] overlaid Python sources into {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
