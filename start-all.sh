#!/usr/bin/env bash
# ============================================================================
# start-all.sh — 一键拉起全部服务 + SSH 分类隧道
#
# 用法（在 Git Bash 中）:
#   ./start-all.sh
#
# 行为:
#   - 已运行且健康的服务自动跳过
#   - 服务启动后逐个健康检查（含 ES 就绪检查）
#   - 任一服务失败: 在项目根目录生成「启动失败报告.md」，列出哪个服务没起来、
#     日志尾部与排查建议
#   - 日志目录: .runtime/logs/<服务名>.log
#
# 服务清单（端口）:
#   5432/9200/7687  基础设施 PG / ES / Neo4j（只检查，不管理 Docker 容器）
#   8002  知识库检索   searcher.kb_search_server
#   8200  知识库入库   writer/kb_ingest_server
#   8101  Agent 平台  src.api.server
#   8000  Gateway     app.main
#   5173  前端        Vite (npm run dev)
#   8001  分类隧道    scripts/classify_tunnel.py (SSH → 远程分类推理服务)
# ============================================================================
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$PROJECT_ROOT/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

REPORT_FILE="$PROJECT_ROOT/启动失败报告.md"

KB_ROOT="$PROJECT_ROOT/Finance_Knowledge-main/Finance_ai_team_KnowledgeBase"
KB_PY="$KB_ROOT/.venv/Scripts/python.exe"
AGENT_ROOT="$PROJECT_ROOT/Finance_Agent"
AGENT_PY="$AGENT_ROOT/.venv/Scripts/python.exe"
GW_ROOT="$PROJECT_ROOT/Finance_AI_FASTAPI"
GW_PY="$GW_ROOT/.venv/Scripts/python.exe"
VUE_ROOT="$PROJECT_ROOT/Finance_Vue-main"

# SSH 隧道密码: 优先取环境变量 REMOTE_SSH_PASS，
# 其次读本地文件 .runtime/ssh-pass.txt（已被 .gitignore 排除，不入库）
SSH_PASS="${REMOTE_SSH_PASS:-}"
if [ -z "$SSH_PASS" ] && [ -f "$RUNTIME_DIR/ssh-pass.txt" ]; then
  SSH_PASS="$(cat "$RUNTIME_DIR/ssh-pass.txt" | tr -d '\r\n')"
fi

FAILURES=()          # 失败的服务名
FAILURE_HINTS=()     # 每个失败的排查建议

port_listening() {
  netstat -ano | grep LISTENING | grep -q ":$1 "
}

log_tail() {  # <name> <行数>
  echo "## $1"
  echo
  echo '```'
  tail -n "$2" "$LOG_DIR/$1.log" 2>/dev/null || echo "(无日志文件)"
  echo '```'
}

# ============================================================================
# 1. 基础设施检查（只检查，不启动；有问题提示 docker 启动命令）
# ============================================================================
echo "═══ 1/7 基础设施检查 ═══"

if port_listening 5432; then
  echo "  [OK] PostgreSQL 5432"
else
  FAILURES+=("PostgreSQL(5432)")
  FAILURE_HINTS+=("PostgreSQL 未监听 5432。Docker 容器名 docker-db_postgres-1，可执行: docker start docker-db_postgres-1")
fi

if curl -s -o /dev/null -m 5 -u elastic:elastic http://localhost:9200/; then
  echo "  [OK] Elasticsearch 9200 (elastic:elastic)"
else
  FAILURES+=("Elasticsearch(9200)")
  FAILURE_HINTS+=("Elasticsearch 未就绪或认证失败。Docker 容器名 elasticsearch，可执行: docker start elasticsearch；凭证应为 elastic:elastic")
fi

if port_listening 7687; then
  echo "  [OK] Neo4j 7687（可选，未开不影响主链路）"
else
  echo "  [提示] Neo4j 7687 未监听（图谱功能可选，不影响上传/检索主链路）"
fi

# ============================================================================
# 2. 应用服务启动
# ============================================================================
start_py() {  # <name> <workdir> <python> <args...>
  local name="$1" workdir="$2" py="$3"; shift 3
  local pidfile="$PID_DIR/$name.pid"
  if port_listening "${port_of[$name]:-0}"; then
    return 0  # 端口已监听，由后续健康检查判定
  fi
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "  [跳过] $name 已运行 (PID $(cat "$pidfile"))"
    return 0
  fi
  (cd "$workdir" && nohup "$py" "$@" > "$LOG_DIR/$name.log" 2>&1 & echo $! > "$pidfile")
  echo "  [启动] $name → .runtime/logs/$name.log"
}

declare -A port_of=(
  [knowledge-search]=8002
  [kb-ingest]=8200
  [agent]=8101
  [gateway]=8000
  [frontend]=5173
  [classify-tunnel]=8001
)

wait_http() {  # <name> <url> <timeout_sec> <额外grep(可选)>
  local name="$1" url="$2" t="$3" grep_pat="${4:-}" i=0
  while [ $i -lt $t ]; do
    local resp
    # 启动即崩溃快速失败：刚拉起的进程已退出且端口未监听（旧 pidfile 且端口在听时不受影响）
    local pidfile="$PID_DIR/$name.pid"
    if [ -f "$pidfile" ] && ! kill -0 "$(cat "$pidfile")" 2>/dev/null \
       && ! port_listening "${port_of[$name]:-0}"; then
      echo "  [失败] $name 进程已退出（启动即崩溃），详见日志"
      FAILURES+=("$name($url)")
      return 1
    fi
    resp=$(curl -s -m 4 "$url" 2>/dev/null)
    if [ -n "$resp" ] && { [ -z "$grep_pat" ] || echo "$resp" | grep -q "$grep_pat"; }; then
      echo "  [OK] $name 健康"
      return 0
    fi
    sleep 2; i=$((i + 2))
  done
  FAILURES+=("$name($url)")
  return 1
}

echo "═══ 2/7 知识库检索 8002 ═══"
if port_listening 8002; then
  echo "  [跳过] 端口已监听，直接健康检查"
else
  start_py knowledge-search "$KB_ROOT" "$KB_PY" -m uvicorn searcher.kb_search_server:app --host 127.0.0.1 --port 8002
fi
wait_http knowledge-search http://127.0.0.1:8002/readiness 180 '"elasticsearch":"healthy"' \
  || FAILURE_HINTS+=("8002 未就绪。若 readiness 显示 elasticsearch unhealthy：检查 ES 容器与 .env 的 ES_USER/ES_PASSWORD；向量模式启动需预加载嵌入模型（约 1-3 分钟）；日志见 .runtime/logs/knowledge-search.log")

echo "═══ 3/7 知识库入库 8200 ═══"
if port_listening 8200; then
  echo "  [跳过] 端口已监听，直接健康检查"
else
  start_py kb-ingest "$KB_ROOT/writer" "$KB_PY" kb_ingest_server.py --host 127.0.0.1 --port 8200
fi
wait_http kb-ingest http://127.0.0.1:8200/health 180 \
  || FAILURE_HINTS+=("8200 未就绪。向量模式（ENABLE_VECTOR_SEARCH=true）下启动需预加载 2.2GB 嵌入模型（约 1-3 分钟），请稍候重试；日志见 .runtime/logs/kb-ingest.log")

echo "═══ 4/7 Agent 平台 8101 ═══"
if port_listening 8101; then
  echo "  [跳过] 端口已监听，直接健康检查"
else
  # 注: 必须用 python -m src.api.server 启动（不能用 -m uvicorn）：
  # server.py 在导入期设置 Windows SelectorEventLoop 策略（psycopg 异步 /
  # PostgresSaver 多轮记忆依赖），-m uvicorn 会先建 ProactorEventLoop 导致挂载失败。
  start_py agent "$AGENT_ROOT" "$AGENT_PY" -m src.api.server
fi
wait_http agent http://127.0.0.1:8101/health 45 \
  || FAILURE_HINTS+=("8101 未就绪。日志见 .runtime/logs/agent.log")

echo "═══ 5/7 Gateway 8000 ═══"
if port_listening 8000; then
  echo "  [跳过] 端口已监听，直接健康检查"
else
  # 注: gateway 需 PYTHONPATH 指向自身目录才能 import app
  (cd "$GW_ROOT" && nohup env PYTHONPATH=. "$GW_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$LOG_DIR/gateway.log" 2>&1 & echo $! > "$PID_DIR/gateway.pid")
  echo "  [启动] gateway → .runtime/logs/gateway.log"
fi
wait_http gateway http://127.0.0.1:8000/api/v1/health 45 \
  || FAILURE_HINTS+=("8000 未就绪。日志见 .runtime/logs/gateway.log")

echo "═══ 6/7 前端 5173 ═══"
if port_listening 5173; then
  echo "  [跳过] 端口已监听，直接健康检查"
else
  (cd "$VUE_ROOT" && nohup npm run dev -- --host 0.0.0.0 > "$LOG_DIR/frontend.log" 2>&1 & echo $! > "$PID_DIR/frontend.pid")
  echo "  [启动] frontend → .runtime/logs/frontend.log"
fi
wait_http frontend http://127.0.0.1:5173/ 60 \
  || FAILURE_HINTS+=("5173 未就绪。前端依赖 npm install（node_modules）；日志见 .runtime/logs/frontend.log")

echo "═══ 7/7 分类 SSH 隧道 8001 ═══"
if port_listening 8001; then
  echo "  [跳过] 端口已监听，直接健康检查"
else
  (cd "$GW_ROOT" && nohup env REMOTE_SSH_PASS="$SSH_PASS" python scripts/classify_tunnel.py > "$LOG_DIR/classify-tunnel.log" 2>&1 & echo $! > "$PID_DIR/classify-tunnel.pid")
  echo "  [启动] classify-tunnel → .runtime/logs/classify-tunnel.log"
fi
wait_http classify-tunnel http://127.0.0.1:8001/health 30 \
  || FAILURE_HINTS+=("8001 隧道未就绪。分类隧道需系统 Python（含 paramiko）且能 SSH 到 172.22.121.55:50009；密码可通过环境变量 REMOTE_SSH_PASS 覆盖；日志见 .runtime/logs/classify-tunnel.log")

# ============================================================================
# 3. 汇总 & 失败报告
# ============================================================================
echo
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "════════════════════════════════════════"
  echo " ✅ 全部服务启动成功，健康检查通过"
  echo "════════════════════════════════════════"
  exit 0
fi

echo "════════════════════════════════════════"
echo " ⚠️  ${#FAILURES[@]} 个服务未就绪，详见报告"
echo "════════════════════════════════════════"

# 生成失败报告文档
{
  echo "# 启动失败报告"
  echo
  echo "> 生成时间：$(date '+%Y-%m-%d %H:%M:%S')"
  echo "> 由 start-all.sh 自动生成"
  echo
  echo "## 未挂起的服务"
  echo
  i=0
  for name in "${FAILURES[@]}"; do
    echo "- **$name**"
    if [ -n "${FAILURE_HINTS[$i]:-}" ]; then
      echo "  - 排查建议：${FAILURE_HINTS[$i]}"
    fi
    i=$((i + 1))
  done
  echo
  echo "## 失败服务日志（尾部）"
  echo
  for name in "${FAILURES[@]}"; do
    case "$name" in
      knowledge-search*)    log_tail knowledge-search 15 ;;
      kb-ingest*)           log_tail kb-ingest 15 ;;
      agent*)               log_tail agent 15 ;;
      gateway*)             log_tail gateway 15 ;;
      frontend*)            log_tail frontend 15 ;;
      classify-tunnel*)     log_tail classify-tunnel 15 ;;
      PostgreSQL*)          echo "## PostgreSQL" ; echo; echo '```'; echo "端口 5432 未监听（docker start docker-db_postgres-1）"; echo '```' ;;
      Elasticsearch*)       echo "## Elasticsearch" ; echo; echo '```'; echo "端口 9200 未就绪（docker start elasticsearch）"; echo '```' ;;
    esac
  done
} > "$REPORT_FILE"

echo "已生成失败报告: $REPORT_FILE"
exit 1
