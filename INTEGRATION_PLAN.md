# Finance AI 四模块整合方案

## 1. 文档目的

本文档是以下四个模块的统一集成基线：

- `Finance_AI_Vue`：Web 前端；
- `Finance_AI_FASTAPI`：统一业务 Gateway；
- `Finance_Agent`：四智能体统一运行平台；
- `Finance_AI_KnowledgeBase`：知识解析、入库和检索服务。

第一阶段保持四个独立 Git 仓库，不做源码仓库合并。整合的重点是统一运行拓扑、服务边界、端口、环境变量和接口协议。

## 2. 目标架构

```text
Browser
   |
   | HTTP / SSE
   v
Finance_AI_Vue :5173（开发）/ :80（生产）
   |
   | /api/v1/*
   v
Finance_AI_FASTAPI :8000
   |-- PostgreSQL: knowledge_agent（用户、会话、消息、附件）
   |
   | POST /v1/agent/chat
   | POST /v1/agent/approve
   v
Finance_Agent :8101
   |-- requirement-pre-review
   |-- ai-test-analysis
   |-- accounting-expert
   |-- business-analyst
   |
   | POST /api/v1/search
   v
Finance_AI_KnowledgeBase :8002
   |-- PostgreSQL: knowledge_base（知识元数据）
   |-- Elasticsearch（文本与向量检索）
   `-- Neo4j（图谱扩展，可选）
```

浏览器只允许访问 Vue 和 Gateway。浏览器不得直接调用 Agent、KnowledgeBase 或数据库。

## 3. 统一端口

| 服务 | 开发端口 | 对外暴露 | 说明 |
|---|---:|:---:|---|
| Vue | 5173 | 是 | Vite 开发服务；生产环境建议使用 80/443 |
| FastAPI Gateway | 8000 | 是 | 浏览器唯一后端入口 |
| Agent Platform | 8101 | 否 | 一个进程承载四个智能体 |
| KnowledgeBase Search | 8002 | 否 | Agent 使用的稳定检索接口 |
| KnowledgeBase Parse | 8201 | 否 | 可选的离线/管理服务 |
| KnowledgeBase Classify | 8202 | 否 | 可选的离线/管理服务 |
| KnowledgeBase Ingest | 8203 | 否 | 可选的离线/管理服务 |
| PostgreSQL | 5432 | 否 | `knowledge_agent` 与 `knowledge_base` 使用不同 database |
| Elasticsearch | 9200 | 否 | 知识检索基础设施 |
| Neo4j HTTP/Bolt | 7474/7687 | 否 | 可选图谱能力 |

禁止 Agent 使用 8000，以免与 Gateway 冲突。运行时不再给四个 Agent 分配 8101～8104 四个固定端口；四个 Agent 通过请求中的 `agent_id` 在 8101 服务内部路由。

## 4. 模块职责

### 4.1 Finance_AI_Vue

负责：

- 登录、注册和退出交互；
- Agent 能力展示；
- 会话、消息和附件 UI；
- 消费 Gateway 返回的 SSE；
- 展示审批卡片并提交审批结果。

不负责：

- 保存权威会话数据；
- 判断 Agent 实际服务地址；
- 直接访问数据库或知识库；
- 根据问题内容猜测应该调用哪个 Agent。

### 4.2 Finance_AI_FASTAPI

负责：

- Cookie Session 鉴权；
- 用户、会话、消息和附件持久化；
- 校验 `agent_id`、会话所有权和附件所有权；
- 提取附件文本；
- 调用 Agent 内部接口；
- 将 Agent SSE 归一化并转发给 Vue；
- 记录请求状态、错误状态和 Agent 输出。

不负责：

- 执行 LangGraph；
- 执行知识检索；
- 根据用户输入关键词重新选择 Agent。

### 4.3 Finance_Agent

负责：

- 根据显式 `agent_id` 选择对应 LangGraph；
- 执行需求预评审、测试分析、用例评审和步骤生成；
- 通过 `thread_id` 维护多轮状态；
- 需要知识时调用 KnowledgeBase；
- 输出统一 SSE 事件；
- 处理需要恢复图状态的审批请求。

不负责：

- 用户登录和权限；
- 浏览器上传文件；
- 业务会话和消息的永久存储；
- 向前端暴露模型或知识库连接信息。

### 4.4 Finance_AI_KnowledgeBase

负责：

- 文档解析、分类、切片和入库；
- PostgreSQL、Elasticsearch、Neo4j 的知识数据维护；
- 提供稳定的 `/api/v1/search` 检索接口；
- 按 `kb_codes` 限定检索范围；
- 返回统一的知识片段、评分和来源元数据。

不负责：

- 用户聊天会话；
- Agent 业务路由；
- 直接向 Vue 返回业务回答。

## 5. Agent ID 统一定义

以下 ID 是跨 Vue、Gateway、Agent 和数据库使用的稳定标识，不允许各模块自行改名：

| agent_id | Agent 内部实现 | 中文名称 | 是否有状态 |
|---|---|---|:---:|
| `requirement-pre-review` | `requirement_review` | 需求预评审智能体 | 是 |
| `ai-test-analysis` | `requirement_analysis` | 需求 AI 测试分析智能体 | 否 |
| `accounting-expert` | `test_case_review` | 测试用例评审智能体 | 否 |
| `business-analyst` | `test_step_generator` | 测试步骤生成智能体 | 否 |

现有 ID 虽然部分名称不够贴合业务，但第一阶段不修改，避免同时迁移前端、数据库和接口。后续如要重命名，必须通过版本化迁移统一处理。

## 6. Vue → Gateway 公共接口

公共接口统一使用 `/api/v1` 前缀。

### 6.1 发送聊天请求

```http
POST /api/v1/chat
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "query": "请评审这份登录测试用例",
  "conversation_id": null,
  "agent_id": "accounting-expert",
  "file_ids": ["file_xxx"],
  "client_message_id": "browser-generated-uuid"
}
```

约束：

- `agent_id` 必须来自统一能力清单；
- 新会话的 `conversation_id` 为 `null`；
- 后续消息必须复用 Gateway 返回的 `conversation_id`；
- 一个会话创建后不允许切换 `agent_id`；
- `client_message_id` 用于防止浏览器重复提交。

### 6.2 公共 SSE 事件

Gateway 对 Vue 只输出以下事件：

#### progress

```text
event: progress
data: {"request_id":"req_xxx","conversation_id":"conv_xxx","node":"retrieval","message":"正在检索知识库..."}
```

#### delta

```text
event: delta
data: {"request_id":"req_xxx","conversation_id":"conv_xxx","text":"增量文本"}
```

#### approval_required

```text
event: approval_required
data: {"request_id":"req_xxx","conversation_id":"conv_xxx","approval_id":"approval_xxx","answer":"请确认以上需求摘要","options":["approve","reject","revise"]}
```

#### completed

```text
event: completed
data: {"request_id":"req_xxx","conversation_id":"conv_xxx","message_id":123,"answer":"完整回答","metadata":{}}
```

#### error

```text
event: error
data: {"request_id":"req_xxx","conversation_id":"conv_xxx","code":"knowledge_base_unavailable","message":"知识库检索服务暂不可用","retryable":true}
```

终止规则：

- `completed`、`approval_required`、`error` 都是本次 SSE 的终止事件；
- 一次请求只能出现其中一个终止事件；
- `completed.answer` 是最终权威文本；
- `delta` 只用于流式展示。

### 6.3 审批请求

```http
POST /api/v1/chat/approve
Content-Type: application/json
```

```json
{
  "conversation_id": "conv_xxx",
  "approval_id": "approval_xxx",
  "decision": "approve",
  "reason": "确认无误"
}
```

`decision` 只能是：

- `approve`：确认并继续；
- `reject`：拒绝并结束；
- `revise`：结合 `reason` 修改后重新确认。

Gateway 必须校验会话所有权，再转发给 Agent。不得吞掉 Agent 审批请求失败；上游失败必须向 Vue 返回明确错误。

## 7. Gateway → Agent 内部接口

### 7.1 发送 Agent 请求

```http
POST /v1/agent/chat
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "request_id": "req_xxx",
  "thread_id": "conv_xxx",
  "user_id": "user_xxx",
  "agent_id": "accounting-expert",
  "query": "请评审这份登录测试用例",
  "attachments": [
    {
      "file_id": "file_xxx",
      "filename": "login-cases.xlsx",
      "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "text": "Gateway 提取后的文本"
    }
  ]
}
```

必须调整：

1. Gateway 转发请求时增加 `agent_id`；
2. Agent 的 `InternalChatRequest` 增加相同的 Literal/Enum 字段；
3. Agent 只能根据 `agent_id` 精确路由；
4. 删除基于 `thread_id` 前缀和 query 关键词的主路由逻辑；
5. 旧关键词路由如需保留，只能放在明确标记的兼容接口中。

Agent 内部 SSE 至少支持：

- `progress`；
- `delta`；
- `approval_required`；
- `completed`；
- `error`。

Gateway 负责补充公共响应中的 `conversation_id` 和数据库 `message_id`。

### 7.2 Agent 审批恢复

```http
POST /v1/agent/approve
Content-Type: application/json
```

```json
{
  "request_id": "req_xxx",
  "thread_id": "conv_xxx",
  "user_id": "user_xxx",
  "agent_id": "requirement-pre-review",
  "approval_id": "approval_xxx",
  "decision": "approve",
  "reason": "确认无误"
}
```

审批接口必须验证：

- `thread_id` 对应的图状态存在；
- 状态正在等待审批；
- `approval_id` 与当前等待项一致；
- 重复审批返回幂等结果或明确的 `approval_already_resolved`；
- 用户和 Agent 与原请求一致。

审批后的继续执行建议仍返回 SSE，以便 Vue 展示后续进度。若第一阶段暂时返回 JSON，则 Gateway 需要再自动发起一次恢复流请求，但不推荐这种额外跳转。

## 8. Agent → KnowledgeBase 接口

### 8.1 检索请求

```http
POST /api/v1/search
Content-Type: application/json
```

```json
{
  "query": "登录失败次数限制和账户锁定规则",
  "kb_codes": ["KB01", "KB03"],
  "top_k": 6,
  "expand_k": 3,
  "request_id": "req_xxx"
}
```

其中 `request_id` 建议增加，用于跨服务日志追踪；服务端第一阶段可设为可选字段。

### 8.2 检索响应

```json
{
  "query": "登录失败次数限制和账户锁定规则",
  "results": [
    {
      "content": "知识片段正文",
      "score": 0.87,
      "metadata": {
        "kb_code": "KB01",
        "title": "登录安全规范",
        "heading": "账户锁定",
        "doc_id": "doc_xxx",
        "chunk_id": "chunk_xxx",
        "source_file": "登录安全规范.md",
        "version": 1
      }
    }
  ],
  "trace": {
    "expanded_keywords": ["登录失败", "账户锁定"],
    "result_count": 1,
    "bm25_count": 1,
    "vector_count": 1
  }
}
```

KnowledgeBase 必须调整：

1. `kb_codes` 为空时搜索全部；不为空时必须真正过滤；
2. `metadata.kb_code` 必须来自知识库编码，不能使用 `doc_id` 代替；
3. `doc_id`、`chunk_id`、`source_file` 保持各自独立语义；
4. 检索失败统一返回 `knowledge_base_unavailable`；
5. 无结果是正常的 200 响应，返回空 `results`，不能当作服务失败。

## 9. 错误码基线

| code | HTTP/SSE | retryable | 含义 |
|---|---:|:---:|---|
| `authentication_required` | 401 | 否 | 用户未登录 |
| `permission_denied` | 403 | 否 | 无权访问会话或文件 |
| `conversation_not_found` | 404 | 否 | 会话不存在 |
| `conversation_agent_mismatch` | 409 | 否 | 会话与 Agent 不匹配 |
| `message_duplicate` | 409 | 否 | 重复提交相同客户端消息 |
| `approval_not_pending` | 409 | 否 | 当前没有待处理审批 |
| `approval_already_resolved` | 409/200 | 否 | 审批已处理 |
| `invalid_attachment` | 400 | 否 | 附件无效或解析失败 |
| `agent_unavailable` | 503/SSE | 是 | Agent 无法连接 |
| `agent_timeout` | 504/SSE | 是 | Agent 超时 |
| `agent_invalid_response` | 502/SSE | 视情况 | Agent 返回违反契约 |
| `knowledge_base_unavailable` | 502/SSE | 是 | 知识库不可用 |
| `model_authentication_failed` | 502/SSE | 否 | 模型鉴权失败 |
| `agent_execution_failed` | 500/SSE | 视情况 | Agent 执行失败 |

所有错误对用户返回安全信息；详细异常堆栈只写服务端日志。

## 10. 健康检查

### Gateway

```http
GET /api/v1/health
```

只表示 Gateway 进程存活，不能检查外部依赖。

```http
GET /api/v1/readiness
```

建议响应：

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "agent-platform": "ok"
  }
}
```

### Agent

```http
GET /health
```

表示 Agent 进程存活。

```http
GET /readiness
```

建议检查模型配置和 KnowledgeBase：

```json
{
  "status": "ok",
  "checks": {
    "model": "ok",
    "knowledge-base": "ok"
  }
}
```

### KnowledgeBase

```http
GET /health
GET /readiness
```

`readiness` 应分别报告 PostgreSQL、Elasticsearch 和 Neo4j。Neo4j 如果配置为可选能力，可以返回 `disabled` 而不是使整个服务失败。

## 11. 环境变量

### Finance_AI_Vue/.env

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

### Finance_AI_FASTAPI/.env

```dotenv
AGENT_PLATFORM_URL=http://127.0.0.1:8101

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=knowledge_agent
DB_USER=postgres
DB_PASSWORD=change-me

MIGRATIONS_DIR=database
SESSION_COOKIE_SECURE=false
```

Gateway 应逐步使用单一 `AGENT_PLATFORM_URL` 取代四个重复的 `AGENT_*_URL`。迁移期间可以兼容旧变量，但最终配置只保留一个 Agent 地址。

### Finance_Agent/.env

```dotenv
API_HOST=127.0.0.1
API_PORT=8101

KB_BASE_URL=http://127.0.0.1:8002
KB_TIMEOUT_SECONDS=30
ALLOW_LOCAL_KB_FALLBACK=false

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:32b-q8_0
```

生产环境不得在源码中保留固定模型 IP 或默认密钥。所有 Agent 的模型客户端必须读取统一配置。

### Finance_AI_KnowledgeBase/.env

```dotenv
API_HOST=127.0.0.1
SEARCH_API_PORT=8002

PG_HOST=127.0.0.1
PG_PORT=5432
PG_DBNAME=knowledge_base
PG_USER=postgres
PG_PASSWORD=change-me

ES_HOST=http://127.0.0.1:9200
ES_INDEX=knowledge_chunks
NEO4J_URI=bolt://127.0.0.1:7687
```

## 12. 数据库边界

同一个 PostgreSQL 实例可以承载两个 database，但禁止混用表：

```text
knowledge_agent
  users
  sessions
  conversations
  messages
  uploads
  schema_migrations

knowledge_base
  documents
  chunks
  knowledge metadata
  rebuild flags
```

`Finance_AI_FASTAPI/database/*.sql` 只管理 `knowledge_agent`。

KnowledgeBase 的数据库结构由 `Finance_AI_KnowledgeBase` 自己管理，不允许 Gateway 的迁移脚本跨库修改。

## 13. 日志追踪

跨服务统一透传：

- `request_id`：一次用户请求；
- `conversation_id/thread_id`：一次业务会话；
- `user_id`：内部用户标识；
- `agent_id`：实际选择的智能体。

Gateway 生成 `request_id`，Agent 和 KnowledgeBase 原样记录。日志不得记录 Cookie、密码、模型密钥或完整敏感附件内容。

建议日志格式：

```text
request_id=req_xxx conversation_id=conv_xxx agent_id=accounting-expert event=agent_completed duration_ms=1234
```

## 14. 开发启动顺序

### 14.1 基础设施

```text
1. PostgreSQL
2. Elasticsearch
3. Neo4j（启用图谱时）
4. Ollama 或其他模型服务
```

### 14.2 KnowledgeBase

```bash
cd Finance_AI_KnowledgeBase
python main.py serve search --host 127.0.0.1 --port 8002
```

### 14.3 Agent

```bash
cd Finance_Agent
python -m src.api.server
```

Agent 必须通过 `.env` 使用 8101。

### 14.4 Gateway

```bash
cd Finance_AI_FASTAPI
uv sync --extra dev
uv run python -m scripts.apply_migrations
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 14.5 Vue

```bash
cd Finance_AI_Vue
npm install
npm run dev
```

## 15. 分阶段实施计划

### 阶段一：打通主聊天链路（P0）

- [ ] Gateway 内部请求增加 `agent_id`；
- [ ] Agent 请求模型增加 `agent_id`；
- [ ] Agent 改为按 `agent_id` 精确路由；
- [ ] Agent 固定运行于 8101；
- [ ] Gateway 改用单一 `AGENT_PLATFORM_URL`；
- [ ] 补充四个 Agent 的路由契约测试；
- [ ] 完成 Vue → Gateway → Agent 的四条冒烟测试。

验收标准：四个相同问题分别选择四个 Agent 时，必须稳定进入四个不同工作流，不得依赖关键词猜测。

### 阶段二：打通知识库（P0/P1）

- [ ] Agent 的 `KB_BASE_URL` 默认指向 8002；
- [ ] KnowledgeBase 真正执行 `kb_codes` 过滤；
- [ ] 修正 `metadata.kb_code`；
- [ ] 增加无结果、过滤结果和服务异常测试；
- [ ] 增加 Agent → KnowledgeBase 契约测试。

验收标准：指定 `KB01` 时不得返回其他知识库数据；知识库不可用时前端收到 `knowledge_base_unavailable`。

### 阶段三：审批闭环（P1）

- [ ] Agent 引入持久化/可恢复的 LangGraph checkpointer；
- [ ] Agent 输出 `approval_required`；
- [ ] Agent 实现 `/v1/agent/approve`；
- [ ] Gateway 审批接口按统一契约转发；
- [ ] Vue 展示审批卡片并处理三种 decision；
- [ ] 增加重复审批、越权审批和状态丢失测试。

验收标准：服务等待审批时可以结束当前 SSE；用户审批后从同一个 `thread_id` 恢复，而不是从头执行。

### 阶段四：运行与部署统一（P1）

- [ ] 为四模块补充统一的 `.env.example`；
- [ ] 增加根目录开发启动脚本或 Docker Compose；
- [ ] 增加 `/readiness` 依赖检查；
- [ ] 增加统一 request_id 日志；
- [ ] 建立 CI 契约测试和端到端测试。

验收标准：新环境按 README 配置后，可以用一条编排命令启动完整链路并通过 readiness。

## 16. 必须具备的集成测试

### 公共主链路

1. 注册并登录；
2. 获取四个 Agent 能力清单；
3. 上传 TXT/PDF/DOCX/XLSX 文件；
4. 分别向四个 Agent 发送消息；
5. 验证 `progress → delta → completed`；
6. 刷新页面并恢复会话历史；
7. 删除会话并验证所有权隔离。

### 异常链路

1. Agent 停止时返回 `agent_unavailable`；
2. KnowledgeBase 停止时返回 `knowledge_base_unavailable`；
3. 重复 `client_message_id` 被拒绝；
4. 用户不能引用其他用户附件；
5. 会话不能切换 Agent；
6. SSE 中途断开时消息被标记失败；
7. 无效 Agent 输出被 Gateway 转换为 `agent_invalid_response`。

### 审批链路

1. 需求评审产生 `approval_required`；
2. `approve` 后从断点继续；
3. `revise` 后重新生成确认内容；
4. `reject` 后正常结束；
5. 重复或越权审批被拒绝。

## 17. 当前已知差异

在开始实施前，各模块负责人需要确认以下现状：

1. Gateway 已选择明确 `agent_id`，但当前没有将其传给 Agent；
2. Agent 当前使用 thread 前缀或关键词猜测路由；
3. Gateway 配置为四个 Agent 地址，但 Agent 实际是统一服务；
4. Gateway 会调用 Agent `/chat/approve`，但 Agent 当前没有对应闭环；
5. Vue 尚未完整消费 `approval_required`；
6. KnowledgeBase 接收 `kb_codes`，但当前检索实现未真正应用过滤；
7. KnowledgeBase 当前把部分 `doc_id` 数据写入了 `metadata.kb_code`；
8. KnowledgeBase 的解析、分类和搜索服务文档中存在端口重复，需要按本文档端口统一；
9. Agent 源码中仍存在固定模型地址，应迁移到统一环境变量。

## 18. 对齐结论

四个模块不需要合并成一个 Python/Node 工程。推荐继续保持独立仓库，通过以下三个稳定边界完成整合：

```text
Vue --公共 API--> Gateway --内部 Agent API--> Agent --知识检索 API--> KnowledgeBase
```

第一优先级不是增加新功能，而是完成：

1. 显式 `agent_id` 路由；
2. 单 Agent 平台端口统一；
3. Gateway、Agent、Vue 的审批协议闭环；
4. KnowledgeBase 的 `kb_codes` 真实过滤和元数据修正。

所有后续实现和接口评审均以本文档为基线。如果代码与本文档冲突，应先更新并评审本文档，再修改各模块实现。
