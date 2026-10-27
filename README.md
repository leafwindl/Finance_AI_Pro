# Finance AI 智能测试全流程平台

Finance AI 是一个覆盖“需求预评审 → 六维测试分析 → 测试用例评审 → 测试步骤生成”的智能测试全流程平台。项目采用单仓库管理，浏览器只访问 Vue 和 Gateway，模型、知识库与数据库均通过服务端内部接口调用。

## 1. 项目结构

| 目录 | 职责 | 默认端口 |
|---|---|---:|
| `Finance_AI_Vue` | 页面、人工审批、SSE 进度展示 | 5173 |
| `Finance_AI_FASTAPI` | 鉴权、会话持久化、统一 API、Agent 转发 | 8000 |
| `Finance_Agent` | 四个 LangGraph 智能体 | 8101 |
| `Finance_AI_KnowledgeBase` | 文档入库与知识检索 | 8002 |
| `infra` | 本地 PostgreSQL/Elasticsearch 初始化 | — |
| `scripts` | 安装、启动、停止和健康检查脚本 | — |

```text
Browser -> Vue -> FastAPI Gateway -> Agent Platform -> KnowledgeBase
                    |                      |
                    v                      v
                PostgreSQL              Ollama
```

## 2. 环境要求

- Linux、macOS 或 WSL2；
- Python 3.11～3.13；
- Node.js 20+ 与 npm；
- Docker Engine 与 Docker Compose；
- Ollama，以及能够运行 `qwen3:32b-q8_0` 的模型服务器。

模型很大，本仓库不包含 Ollama 模型权重。显存不足时可在 `.env` 中换成较小的兼容模型，但输出质量可能变化。

## 3. 第一次安装

```bash
git clone git@github.com:leafwindl/Finance_AI_Team.git
cd Finance_AI_Team
./scripts/bootstrap.sh
```

`bootstrap.sh` 会完成：

1. 创建各 Python 模块的 `.venv` 并安装依赖；
2. 使用 `npm ci` 安装前端依赖；
3. 从每个 `.env.example` 创建缺失的 `.env`；
4. 启动 PostgreSQL 和 Elasticsearch；
5. 执行 Gateway SQL 迁移；
6. 使用 `Finance_Agent/docs` 中的 Markdown 重建开发知识库。

默认开发数据库密码为 `finance_ai_dev`，仅适用于本地开发。公网部署前必须修改 `docker-compose.yml` 和两个后端模块的 `.env`。

## 4. 配置与 Ollama

### 本机 Ollama

```bash
ollama pull qwen3:32b-q8_0
ollama serve
curl http://127.0.0.1:11434/api/tags
```

保持 `Finance_Agent/.env` 中：

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:32b-q8_0
OLLAMA_REASONING=false
```

### 远程 Ollama（SSH 隧道）

先确保远程服务器上的 Ollama 正在监听 `127.0.0.1:11434`。Windows PowerShell 使用单行命令：

```powershell
ssh -N -L 127.0.0.1:11435:127.0.0.1:11434 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 root@REMOTE_HOST -p SSH_PORT
```

再将 `Finance_Agent/.env` 改为：

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11435
```

验证隧道：

```bash
curl http://127.0.0.1:11435/api/tags
```

不要把服务器地址、SSH 密码或 API Key 提交到 Git。

## 5. 启动整体服务

确认 Docker 基础设施和 Ollama 已启动后执行：

```bash
./scripts/start-dev.sh
./scripts/healthcheck.sh
```

访问地址：

- 前端：http://127.0.0.1:5173
- Gateway 文档：http://127.0.0.1:8000/docs
- Agent 文档：http://127.0.0.1:8101/docs
- KnowledgeBase 文档：http://127.0.0.1:8002/docs

运行日志位于 `.runtime/logs`。停止应用服务：

```bash
./scripts/stop-dev.sh
docker compose down
```

保留数据库数据时只执行 `stop-dev.sh`；彻底删除开发数据库和 ES 数据时使用 `docker compose down -v`。

## 6. 手动启动

需要分别观察日志时可打开四个终端：

```bash(Linux/Mac)
cd Finance_AI_KnowledgeBase
.venv/bin/python -m uvicorn searcher.kb_search_server:app --host 127.0.0.1 --port 8002

```bash(window)
cd .\Finance_AI_Team\Finance_AI_KnowledgeBase
.\.venv\Scripts\python.exe -m uvicorn searcher.kb_search_server:app --host 127.0.0.1 --port 8002
.................................................................

```bash(Linux/Mac)
cd Finance_Agent
.venv/bin/python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8101

```bash(win)
cd Finance_AI_Team\Finance_Agent
.venv\Scripts\python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8101
...................................................................

```bash(Linux/Mac)
cd Finance_AI_FASTAPI
PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

```bash(win)
cd Finance_AI_Team\Finance_AI_FASTAPI
$env:PYTHONPATH="."
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
....................................................................

```bash(Linux/Mac)
cd Finance_AI_Vue
npm run dev -- --host 0.0.0.0
```bash(win)
cd Finance_AI_Team\Finance_AI_Vue
npm run dev -- --host 0.0.0.0

启动顺序建议为：基础设施 → KnowledgeBase → Agent → Gateway → Vue。

## 7. 数据库与知识库重建

```bash
docker compose up -d postgres elasticsearch
cd Finance_AI_FASTAPI
PYTHONPATH=. .venv/bin/python scripts/apply_migrations.py
cd ../Finance_AI_KnowledgeBase
.venv/bin/python scripts/rebuild_knowledge_base.py
```

知识库重建会清空 `knowledge_base` 的开发知识表和 `knowledge_chunks*` 索引，然后从仓库文档重新入库，请勿对生产数据库执行。

## 8. 测试与构建

```bash
cd Finance_AI_FASTAPI && PYTHONPATH=. .venv/bin/python -m pytest -q
cd ../Finance_Agent && PYTHONPATH=. .venv/bin/python -m pytest -q
cd ../Finance_AI_KnowledgeBase && PYTHONPATH=. .venv/bin/python -m pytest -q
cd ../Finance_AI_Vue && npm run build
```

测试用例流程使用专用 SSE 接口：

- `POST /api/v1/test-cases/review`：Agent 3 测试用例评审；
- `POST /api/v1/test-cases/generate-steps`：Agent 4 测试步骤生成。

需求流程分为两个独立阶段：需求预评审完成并人工通过后，才进入六维测试分析。更完整的模块边界和接口约定参见 [INTEGRATION_PLAN.md](./INTEGRATION_PLAN.md)。

## 9. 公网部署提示

开发服务器只适合联调。公网环境应使用 Nginx/Caddy 提供 HTTPS 和静态文件，并反向代理 `/api` 到 Gateway；PostgreSQL、Elasticsearch、KnowledgeBase、Agent 和 Ollama 不应直接暴露公网。生产环境还应设置安全 Cookie、强数据库密码、访问限流和日志轮转。
