#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

command -v python3 >/dev/null || { echo "缺少 python3" >&2; exit 1; }
command -v npm >/dev/null || { echo "缺少 npm" >&2; exit 1; }
command -v docker >/dev/null || { echo "缺少 Docker" >&2; exit 1; }
docker compose version >/dev/null || { echo "缺少 Docker Compose" >&2; exit 1; }

for module in Finance_AI_FASTAPI Finance_Agent Finance_AI_KnowledgeBase; do
  if [[ ! -d "$module/.venv" ]]; then
    python3 -m venv "$module/.venv"
  fi
done

Finance_AI_FASTAPI/.venv/bin/python -m pip install --upgrade pip
Finance_AI_FASTAPI/.venv/bin/pip install -e 'Finance_AI_FASTAPI[dev]'
Finance_Agent/.venv/bin/python -m pip install --upgrade pip
Finance_Agent/.venv/bin/pip install -r Finance_Agent/requirements.txt pytest
Finance_AI_KnowledgeBase/.venv/bin/python -m pip install --upgrade pip
Finance_AI_KnowledgeBase/.venv/bin/pip install -r Finance_AI_KnowledgeBase/requirements.txt pytest
npm --prefix Finance_AI_Vue ci

for module in Finance_AI_FASTAPI Finance_Agent Finance_AI_KnowledgeBase Finance_AI_Vue; do
  if [[ ! -f "$module/.env" ]]; then
    cp "$module/.env.example" "$module/.env"
    echo "created $module/.env"
  fi
done

docker compose up -d postgres elasticsearch
echo "等待 PostgreSQL 和 Elasticsearch 就绪..."
for attempt in {1..60}; do
  pg_status="$(docker inspect --format='{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null || true)"
  es_status="$(docker inspect --format='{{.State.Health.Status}}' "$(docker compose ps -q elasticsearch)" 2>/dev/null || true)"
  [[ "$pg_status" == healthy && "$es_status" == healthy ]] && break
  [[ "$attempt" == 60 ]] && { echo "基础设施启动超时，请运行 docker compose logs" >&2; exit 1; }
  sleep 2
done

(cd Finance_AI_FASTAPI && PYTHONPATH=. .venv/bin/python scripts/apply_migrations.py)
(cd Finance_AI_KnowledgeBase && .venv/bin/python scripts/rebuild_knowledge_base.py)

echo "初始化完成。请确认 Ollama 可用，然后运行 ./scripts/start-dev.sh"
