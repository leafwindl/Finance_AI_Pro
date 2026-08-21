# Gateway 接口契约

> 版本：v1.0
> 状态：已联调
> 前端实现：`src/services/api.js`、`src/services/api/auth.js`、`src/services/api/conversations.js`

## 1. 调用边界

浏览器只访问 FastAPI Gateway，不直接访问 Agent、知识库、Elasticsearch、Neo4j 或 PostgreSQL。

开发环境默认配置：

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

Vite 将 `/api/*` 代理到 Gateway。除注册、登录和健康检查外，业务接口均要求有效的 Session Cookie。前端所有 `fetch` 请求必须使用：

```js
credentials: 'include'
```

Session Cookie 为 HttpOnly，前端不能也不需要读取或保存 token。

## 2. 通用约定

- 请求和普通响应使用 UTF-8 JSON。
- 流式聊天响应使用 `text/event-stream`。
- 时间字段为带时区的 ISO 8601 字符串。
- 首次聊天时 `conversation_id` 传 `null`，由 Gateway 创建会话。
- 前端不能主动写入 assistant 消息；Gateway 在 Agent 成功完成后统一落库。
- 所有会话和文件都按当前 Cookie 对应的用户进行所有权校验。

常见非流式错误：

```json
{ "detail": "会话不存在" }
```

或：

```json
{
  "detail": {
    "code": "agent_unavailable",
    "message": "智能体服务当前不可用"
  }
}
```

上游服务错误可能返回：

```json
{
  "error": {
    "code": "agent_unavailable",
    "message": "无法连接智能体服务",
    "retryable": true
  }
}
```

## 3. 鉴权接口

### 3.1 注册

```http
POST /api/v1/auth/register
Content-Type: application/json
```

```json
{
  "name": "zhangsan",
  "email": "zhangsan@example.com",
  "password": "123456"
}
```

成功响应 `201`，并由响应设置 Session Cookie：

```json
{
  "user": {
    "user_id": "4af5c21b583743da",
    "name": "zhangsan",
    "email": "zhangsan@example.com"
  }
}
```

### 3.2 登录

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "name": "zhangsan",
  "password": "123456"
}
```

成功响应 `200`，响应体中的 `user` 与注册接口一致，同时设置 Session Cookie。

### 3.3 获取当前用户

```http
GET /api/v1/auth/me
```

成功响应：

```json
{
  "user_id": "4af5c21b583743da",
  "name": "zhangsan",
  "email": "zhangsan@example.com"
}
```

无有效 Session 时返回 `401`。

### 3.4 退出

```http
POST /api/v1/auth/logout
```

```json
{ "ok": true }
```

## 4. 智能体能力

```http
GET /api/v1/agents
```

成功响应：

```json
{
  "agents": [
    {
      "agent_id": "requirement-pre-review",
      "name": "需求预评审智能体",
      "enabled": true,
      "stateful": true
    },
    {
      "agent_id": "accounting-expert",
      "name": "测试用例评审智能体",
      "enabled": true,
      "stateful": false
    }
  ]
}
```

前端以 Gateway 返回的 `enabled` 为准。当前稳定 ID：

| `agent_id` | 状态 |
|---|---|
| `requirement-pre-review` | 已接入 |
| `ai-test-analysis` | 已接入 |
| `accounting-expert` | 已接入 |
| `business-analyst` | 已接入 |

## 5. 文件上传

```http
POST /api/v1/files/upload
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `file` | 是 | 原始文件 |
| `agent_id` | 否 | 兼容字段；文件实际归当前用户所有，不绑定 Agent |

成功响应 `201`：

```json
{
  "file_id": "file_8e6ab6d6f5684f10a5923c04c105192c",
  "filename": "需求说明.md",
  "content_type": "text/markdown",
  "size": 1024,
  "status": "ready"
}
```

限制：

- 最多同时选择 5 个文件；
- 单文件最大 10 MB；
- 支持 `.pdf`、`.docx`、`.xlsx`、`.md`、`.txt`、`.csv`、`.json`；
- 聊天请求只传 `file_id`，不重复上传二进制内容；
- 不能引用其他用户、已过期或不存在的文件。

## 6. 流式聊天

```http
POST /api/v1/chat
Content-Type: application/json
Accept: text/event-stream
```

请求体：

```json
{
  "query": "分析这份需求是否完整",
  "conversation_id": null,
  "agent_id": "requirement-pre-review",
  "file_ids": ["file_8e6ab6d6f5684f10a5923c04c105192c"],
  "client_message_id": "7d64ddd4-00c9-42a4-bd7f-012f43f8a9f6"
}
```

字段约束：

| 字段 | 必填 | 约束 |
|---|---|---|
| `query` | 是 | 1～5000 字符 |
| `conversation_id` | 否 | 首次请求传 `null`；后续使用 `completed` 返回值 |
| `agent_id` | 是 | 必须是四个稳定 ID 之一 |
| `file_ids` | 否 | 最多 5 个，自动去重 |
| `client_message_id` | 是 | 同一会话内用于防止重复提交；前端默认生成 UUID |

响应可能跨任意 HTTP 分块边界，前端不能假定一次读取对应一个 SSE 事件。事件块格式为：

```text
event: progress
data: {"request_id":"req_...","node":"knowledge_retrieval","message":"知识检索中..."}

```

### `progress`

```json
{
  "request_id": "req_...",
  "node": "knowledge_retrieval",
  "message": "知识检索中..."
}
```

### `delta`

```json
{
  "request_id": "req_...",
  "text": "本次新增的回答文本"
}
```

`delta.text` 为增量内容，前端按到达顺序拼接。

### `completed`

```json
{
  "request_id": "req_...",
  "conversation_id": "conv_...",
  "message_id": 42,
  "answer": "完整最终答案",
  "metadata": {
    "retrieval_count": 5
  }
}
```

收到 `completed` 后，前端保存 `conversation_id`，后续消息继续使用该 ID。

### `error`

```json
{
  "request_id": "req_...",
  "code": "knowledge_base_unavailable",
  "message": "知识库检索服务暂不可用",
  "retryable": true
}
```

收到 `error` 后本次流结束，不会再收到 `completed`。

## 7. 会话历史

会话由首次 `POST /api/v1/chat` 自动创建，不提供前端手工创建会话或手工写入消息的接口。

### 7.1 会话列表

```http
GET /api/v1/conversations?agent_id=requirement-pre-review&limit=20
```

`agent_id` 可省略；`limit` 范围为 1～100。

```json
{
  "conversations": [
    {
      "conversation_id": "conv_...",
      "agent_id": "requirement-pre-review",
      "title": "分析这份需求是否完整",
      "created_at": "2026-07-24T10:00:00+08:00",
      "updated_at": "2026-07-24T10:01:30+08:00"
    }
  ]
}
```

### 7.2 消息列表

```http
GET /api/v1/conversations/{conversation_id}/messages
```

```json
{
  "messages": [
    {
      "message_id": 1,
      "role": "user",
      "content": "分析这份需求是否完整",
      "status": "completed",
      "error_code": null,
      "metadata": {},
      "created_at": "2026-07-24T10:00:00+08:00"
    }
  ]
}
```

### 7.3 删除会话

```http
DELETE /api/v1/conversations/{conversation_id}
```

```json
{ "ok": true }
```

删除操作同时删除关联消息；对于有状态的需求预评审 Agent，Gateway 还会尝试清理 LangGraph checkpoint。

## 8. 系统接口

```http
GET /api/v1/health
```

```json
{ "status": "ok" }
```

`/api/v1/health` 只表示 Gateway 进程存活。Gateway、数据库和 Agent 的完整就绪状态由运维使用 `/api/v1/readiness` 检查，普通前端页面不依赖该接口。

## 9. 状态码处理

| 状态码 | 前端处理建议 |
|---:|---|
| `400` / `422` | 显示输入或文件校验错误 |
| `401` | Session 失效，返回登录页 |
| `404` | 会话或文件不存在，刷新对应列表 |
| `409` | 会话与 Agent 不匹配，或消息重复提交 |
| `503` | Agent 未接入或服务不可用 |
| `504` | Agent 响应超时，可根据 `retryable` 提示重试 |
