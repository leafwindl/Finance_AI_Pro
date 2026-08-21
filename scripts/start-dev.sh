#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="$project_root/.runtime"
mkdir -p "$runtime_dir/logs" "$runtime_dir/pids"

start_service() {
  local name="$1" workdir="$2" command="$3" port="$4"
  local pid_file="$runtime_dir/pids/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(<"$pid_file")" 2>/dev/null; then
    echo "$name 已运行，PID $(<"$pid_file")"
    return
  fi
  if command -v ss >/dev/null && ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "端口 $port 已被占用，无法启动 $name" >&2
    exit 1
  fi
  (cd "$workdir" && nohup bash -c "exec $command" >"$runtime_dir/logs/$name.log" 2>&1 & echo $! >"$pid_file")
  echo "已启动 $name，日志：.runtime/logs/$name.log"
}

start_service knowledge-base "$project_root/Finance_AI_KnowledgeBase" ".venv/bin/python -m uvicorn searcher.kb_search_server:app --host 127.0.0.1 --port 8002" 8002
start_service agent "$project_root/Finance_Agent" ".venv/bin/python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8101" 8101
start_service gateway "$project_root/Finance_AI_FASTAPI" "env PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000" 8000
start_service frontend "$project_root/Finance_AI_Vue" "npm run dev -- --host 0.0.0.0" 5173

echo "服务启动中；运行 ./scripts/healthcheck.sh 检查状态。"
