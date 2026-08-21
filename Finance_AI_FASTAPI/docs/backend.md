# FastAPI Gateway 后端

本服务是 Vue 的唯一后端入口，负责 Cookie Session 鉴权、Agent 路由、SSE 归一化、文件文本提取，以及会话和消息持久化。运行时不依赖 Dify。

## 请求链路

```text
Vue :5173
  -> FastAPI Gateway :8000
     -> Agent Platform :8101
        -> 四个 agent_id 对应的工作流
        -> KB Retrieval :8002
     -> PostgreSQL knowledge_agent
```

四个 Agent 均由一个 Agent Platform 承载，使用统一的 `/v1/agent/chat` SSE 协议并按显式 `agent_id` 路由。

## 安装与启动

要求 Python 3.11+、uv 和可连接的 PostgreSQL。

```powershell
Copy-Item .env.example .env
uv sync --extra dev
uv run python -m scripts.apply_migrations
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

默认迁移目录为项目根目录下的 `database/`。如需使用其他目录，请在 `.env` 中设置 `MIGRATIONS_DIR`。

Swagger：`http://127.0.0.1:8000/docs`

## 配置

完整模板见 `.env.example`。主要配置分为：

- `AGENT_*_URL`：各 LangGraph Agent 服务地址；
- `AGENT_*_TIMEOUT_SECONDS`：连接与读取超时；
- `DB_*`：业务数据库 `knowledge_agent`；
- `MIGRATIONS_DIR`：SQL 迁移目录，默认为 `database`；
- `SESSION_*`：Cookie 名称、有效期和 Secure 属性；
- `UPLOAD_*`：上传目录、大小与有效期；
- `EXTRACTED_TEXT_MAX_CHARS`：单文件文本提取上限；
- `REQUEST_ATTACHMENTS_MAX_CHARS`：单次请求附件文本总上限。

生产环境使用 HTTPS 时必须设置：

```dotenv
SESSION_COOKIE_SECURE=true
```

真实 `.env`、数据库密码和 Agent 密钥不得提交到 Git。

## 接口与数据边界

完整公共接口、SSE 事件、错误码及 Gateway → Agent 内部协议见 [`gateway-api.md`](gateway-api.md)。

会话由首次聊天自动创建。前端不能手工写入 assistant 消息，也不能引用其他用户的会话或文件。

支持提取文本的文件格式：

```text
.pdf .docx .xlsx .md .txt .csv .json
```

文件记录按 `UPLOAD_TTL_SECONDS` 过期；过期文件不会再被聊天接口接受。物理文件定期清理属于后续运维任务。

## 测试

自动化测试：

```powershell
uv run pytest -q
```

需要已启动全链路的手工脚本位于 `scripts/manual/`，不会被 pytest 收集：

```powershell
uv run python -m scripts.manual.auth_flow

$env:MANUAL_TEST_USER='your-user'
$env:MANUAL_TEST_PASSWORD='your-password'
uv run python -m scripts.manual.chat_stream
```
