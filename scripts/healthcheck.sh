#!/usr/bin/env bash
set -euo pipefail

check() {
  local name="$1" url="$2"
  if curl -fsS --max-time 5 "$url" >/dev/null; then
    echo "[OK] $name $url"
  else
    echo "[FAIL] $name $url" >&2
    return 1
  fi
}

status=0
check PostgreSQL-via-Gateway http://127.0.0.1:8000/api/v1/health || status=1
check KnowledgeBase http://127.0.0.1:8002/health || status=1
check Agent http://127.0.0.1:8101/health || status=1
check Frontend http://127.0.0.1:5173/ || status=1
exit "$status"
