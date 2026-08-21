#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pid_dir="$project_root/.runtime/pids"

for name in frontend gateway agent knowledge-base; do
  pid_file="$pid_dir/$name.pid"
  [[ -f "$pid_file" ]] || continue
  pid="$(<"$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "已停止 $name（PID $pid）"
  fi
  rm -f "$pid_file"
done
