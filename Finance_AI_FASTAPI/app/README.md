# Gateway 应用结构

```text
app/
├── api/                 # HTTP/SSE 接口：认证、会话、文件与工作流
├── agent_gateway/       # Agent 注册、SSE 解析与上游客户端
├── data_gateway/        # PostgreSQL 连接池及 repository
├── knowledge_gateway/   # 上传文件文本提取
├── schemas/             # API 请求/响应模型
├── core/                # 配置和公共异常
└── main.py              # FastAPI 组装与生命周期
```

依赖方向保持单向：`api → gateway/repository → core`。业务代码只使用
`agent_gateway`、`data_gateway` 和 `knowledge_gateway`，不再维护旧目录别名。

常用命令：

```bash
uv run python -m scripts.apply_migrations
PYTHONPATH=. uv run pytest -q
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```
