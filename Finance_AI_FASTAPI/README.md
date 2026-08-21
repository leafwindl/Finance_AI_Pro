# Finance AI FastAPI Gateway

Finance AI 的统一后端入口。Gateway 接收 Vue 请求，负责登录鉴权、文件和会话持久化，并根据稳定的 `agent_id` 调用独立 LangGraph Agent。运行时不再使用 Dify。

## 调用链

```text
Vue -> FastAPI Gateway -> LangGraph Agent -> KnowledgeBase
                    \-> knowledge_agent PostgreSQL
```

浏览器只访问 Gateway `/api/v1/*`，不直接访问 Agent、数据库或知识库。

## 快速启动

要求 Python 3.11+、uv 和 PostgreSQL。数据库迁移文件随项目存放在 `database/`。

```powershell
Copy-Item .env.example .env
uv sync --extra dev
uv run python -m scripts.apply_migrations
uv run uvicorn app.main:app --reload --port 8000
```

配置详情见 [后端使用说明](docs/backend.md)。

## 接口文档

- 后端权威契约：[Gateway 接口契约](docs/gateway-api.md)
- Swagger：`http://127.0.0.1:8000/docs`
- 存活检查：`GET /api/v1/health`
- 依赖检查：`GET /api/v1/readiness`

主要业务接口：

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `GET /api/v1/agents`
- `POST /api/v1/files/upload`
- `POST /api/v1/chat`
- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `DELETE /api/v1/conversations/{conversation_id}`

聊天 SSE 事件固定为 `progress`、`delta`、`completed`、`error`。

## 测试

```powershell
uv run pytest -q
```

`tests/` 只存放可由 pytest 自动收集的测试；需要真实服务的手工联调脚本位于 `scripts/manual/`。

## 历史资料

[第一版 Dify 架构](docs/architecture-v1.md) 仅用于迁移追溯，不代表当前运行实现。
