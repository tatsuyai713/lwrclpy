#!/usr/bin/env bash
set -euo pipefail

run_all=false
run_ubuntu=false
run_macos=false
run_windows=false

if [[ "${1:-}" == "--all" ]]; then
  run_all=true
  shift
elif [[ "$#" -eq 0 ]]; then
  # An empty or unavailable diff must never suppress CI.
  run_all=true
fi

for path in "$@"; do
  case "$path" in
    .github/workflows/build-windows.yml|.github/workflows/test-windows.yml|scripts/windows/*)
      run_windows=true
      ;;
    .github/workflows/build-macos.yml|.github/workflows/test-macos.yml|scripts/mac/*)
      run_macos=true
      ;;
    .github/workflows/build-ubuntu.yml|.github/workflows/test-ubuntu.yml)
      run_ubuntu=true
      ;;
    *)
      # Shared code, the top-level workflow, and unknown paths can affect every wheel.
      run_all=true
      ;;
  esac
done

if [[ "$run_all" == "true" ]]; then
  run_ubuntu=true
  run_macos=true
  run_windows=true
fi

printf 'all=%s\n' "$run_all"
printf 'ubuntu=%s\n' "$run_ubuntu"
printf 'macos=%s\n' "$run_macos"
printf 'windows=%s\n' "$run_windows"
