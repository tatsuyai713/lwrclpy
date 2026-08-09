#!/usr/bin/env bash
set -euo pipefail

platform="${1:?platform is required}"
repository="${2:?repository is required}"
current_run_id="${3:-}"

case "$platform" in
  ubuntu)
    build_prefix="build-ubuntu-wheels / Build Ubuntu "
    test_prefix="test-ubuntu-wheels / Test Ubuntu "
    expected_builds=8
    expected_tests=8
    ;;
  macos)
    build_prefix="build-macos-wheels / Build macOS Wheel "
    test_prefix="test-macos-wheels / Test macOS "
    expected_builds=4
    expected_tests=4
    ;;
  windows)
    build_prefix="build-windows-wheels / Build Windows "
    test_prefix="test-windows-wheels / Test Windows "
    expected_builds=9
    expected_tests=9
    ;;
  *)
    echo "Unsupported platform: $platform" >&2
    exit 2
    ;;
esac

run_ids="$({
  gh api --method GET "repos/${repository}/actions/workflows/ci.yml/runs" \
    -f branch=main \
    -f per_page=30 \
    --jq '.workflow_runs[].id'
} 2>/dev/null || true)"

while IFS= read -r run_id; do
  [[ -n "$run_id" && "$run_id" != "$current_run_id" ]] || continue

  jobs_json="$(gh api --paginate "repos/${repository}/actions/runs/${run_id}/jobs?per_page=100" 2>/dev/null || true)"
  [[ -n "$jobs_json" ]] || continue

  successful_builds="$(jq -s \
    --arg prefix "$build_prefix" \
    '[.[].jobs[] | select((.name | startswith($prefix)) and .conclusion == "success")] | length' \
    <<<"$jobs_json")"
  successful_tests="$(jq -s \
    --arg prefix "$test_prefix" \
    '[.[].jobs[] | select((.name | startswith($prefix)) and .conclusion == "success")] | length' \
    <<<"$jobs_json")"
  [[ "$successful_builds" -eq "$expected_builds" && "$successful_tests" -eq "$expected_tests" ]] || continue

  artifact_names="$(gh api --paginate "repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100" \
    --jq '.artifacts[] | select(.expired == false) | .name' 2>/dev/null || true)"
  wheel_count="$(grep -c "^wheel-${platform}" <<<"$artifact_names" || true)"
  log_count="$(grep -c "^test-log-${platform}" <<<"$artifact_names" || true)"
  [[ "$wheel_count" -eq "$expected_builds" && "$log_count" -eq "$expected_tests" ]] || continue

  printf '%s\n' "$run_id"
  exit 0
done <<<"$run_ids"

# No output means that the caller must perform a clean build and test.
exit 0
