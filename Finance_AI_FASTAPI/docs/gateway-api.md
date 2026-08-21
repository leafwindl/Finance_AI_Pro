# Gateway 接口契约

> 版本：v1.0
> 状态：已联调
> 公共前缀：`/api/v1`

本文是 Finance AI Gateway 的接口事实来源，覆盖浏览器公共 API 和 Gateway 调用 LangGraph Agent 的内部协议。

## 1. 调用与鉴权边界

```text
Browser / Vue
  -> FastAPI Gateway /api/v1/*
     -> LangGraph Agent /v1/agent/chat
     -> knowledge_agent PostgreSQL
```

浏览器不能直接访问 Agent、知识库或数据库。鉴权使用 HttpOnly Session Cookie；浏览器请求必须设置：

```js
credentials: 'include'
```

Cookie 不包含明文用户资料，服务端只保存随机 token 的 SHA-256 摘要。生产 HTTPS 环境必须配置 `SESSION_COOKIE_SECURE=true`。

## 2. 通用约定

- 普通请求和响应使用 UTF-8 JSON。
- 聊天响应使用 `text/event-stream`。
- 时间为带时区的 ISO 8601 字符串。
- 所有会话、消息和文件查询都必须带当前 `user_id` 所有权条件。
- 首次聊天由 Gateway 创建会话，前端不手工创建会话或写入消息。
- 客户端应为每次用户发送生成唯一 `client_message_id`。
- 响应头 `X-Request-ID` 用于关联 Gateway HTTP 日志。

普通校验错误通常为：

```json
{ "detail": "会话不存在" }
```

结构化错误通常为：

```json
{
  "error": {
    "code": "agent_unavailable",
    "message": "无法连接智能体服务",
    "retryable": true
  }
}
```

## 3. 鉴权

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

约束：

- `name`：1～64 字符，全局唯一；
- `email`：有效邮箱，全局唯一；
- `password`：6～128 字符，数据库只保存 bcrypt 哈希。

成功响应 `201`，同时设置 Session Cookie：

```json
{
  "user": {
    "user_id": "4af5c21b583743da",
    "name": "zhangsan",
    "email": "zhangsan@example.com"
  }
}
```

用户名或邮箱已存在时返回 `409`。用户和 Session 在同一数据库事务中创建。

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

成功响应 `200`，响应体与注册接口一致并设置新 Session Cookie。凭据错误返回 `401`。

### 3.3 当前用户

```http
GET /api/v1/auth/me
```

```json
{
  "user_id": "4af5c21b583743da",
  "name": "zhangsan",
  "email": "zhangsan@example.com"
}
```

Session 缺失、撤销或过期时返回 `401`。

### 3.4 退出

```http
POST /api/v1/auth/logout
```

```json
{ "ok": true }
```

服务端撤销当前 Session 并清除 Cookie。

## 4. Agent 能力清单

```http
GET /api/v1/agents
```

需要登录。成功响应：

```json
{
  "agents": [
    {
      "agent_id": "requirement-pre-review",
      "name": "需求预评审智能体",
      "enabled": true,
      "stateful": true
    }
  ]
}
```

稳定映射：

| `agent_id` | Agent Platform | 状态 |
|---|---:|---|
| `requirement-pre-review` | 8101 | 已接入，有状态 |
| `ai-test-analysis` | 8101 | 已接入 |
| `accounting-expert` | 8101 | 已接入 |
| `business-analyst` | 8101 | 已接入 |

四个 Agent 均由统一 Agent Platform 承载。Agent 进程不可连接时返回 `agent_unavailable`，不会回退到 Dify 或其他 Agent。

## 5. 文件上传

```http
POST /api/v1/files/upload
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `file` | 是 | 原始文件 |
| `agent_id` | 否 | 兼容字段；文件实际属于用户，不绑定 Agent |

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

- 单文件默认最大 10 MB；
- 支持 `.pdf`、`.docx`、`.xlsx`、`.md`、`.txt`、`.csv`、`.json`；
- 文件名只保留基础名称，存储路径由 Gateway 生成；
- 文件记录超过 `UPLOAD_TTL_SECONDS` 后不能用于聊天；
- 只能引用当前用户拥有、状态为 `ready` 且未过期的 `file_id`；
- 单次聊天最多引用 5 个文件，提取文本总长度受配置限制。

## 6. 流式聊天

```http
POST /api/v1/chat
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "query": "分析这份需求是否完整",
  "conversation_id": null,
  "agent_id": "requirement-pre-review",
  "file_ids": ["file_8e6ab6d6f5684f10a5923c04c105192c"],
  "client_message_id": "7d64ddd4-00c9-42a4-bd7f-012f43f8a9f6"
}
```

字段：

| 字段 | 必填 | 约束 |
|---|---|---|
| `query` | 是 | 1～5000 字符 |
| `conversation_id` | 否 | 首次传 `null`，后续使用 Gateway 返回值 |
| `agent_id` | 是 | 四个稳定 ID 之一 |
| `file_ids` | 否 | 最多 5 个，服务端去重 |
| `client_message_id` | 建议必传 | 1～128 字符，同会话内幂等 |

首次请求在文件所有权和解析全部通过后才创建会话，非法附件不会留下空会话。

### 6.1 SSE 编码

```text
event: progress
data: {"request_id":"req_...","conversation_id":"conv_...","node":"retrieve","message":"检索中"}

```

事件可能跨任意 HTTP 分块边界，调用方必须按空行切分 SSE，而不能把一次网络读取当成一个事件。

### 6.2 `progress`

```json
{
  "request_id": "req_...",
  "conversation_id": "conv_...",
  "node": "knowledge_retrieval",
  "message": "知识检索中..."
}
```

### 6.3 `delta`

```json
{
  "request_id": "req_...",
  "conversation_id": "conv_...",
  "text": "本次新增的回答文本"
}
```

调用方按到达顺序拼接 `text`。

### 6.4 `completed`

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

Gateway 只在 assistant 消息成功落库后发送 `completed`。

### 6.5 `error`

```json
{
  "request_id": "req_...",
  "conversation_id": "conv_...",
  "code": "knowledge_base_unavailable",
  "message": "知识库检索服务暂不可用",
  "retryable": true
}
```

收到 `error` 后流结束。`conversation_id` 即使在首次请求失败时也会返回，客户端应保存它，以便安全重试或打开失败历史。

常见流错误码：

| code | 含义 |
|---|---|
| `agent_unavailable` | 无法连接 Agent |
| `agent_timeout` | Agent 响应超时 |
| `agent_upstream_error` | Agent 返回非成功状态 |
| `agent_stream_incomplete` | Agent 流意外结束 |
| `agent_invalid_response` | Agent 完成事件没有答案 |
| `knowledge_base_unavailable` | Agent 无法检索知识库 |
| `model_authentication_failed` | Agent 大模型鉴权失败 |
| `gateway_stream_error` | Gateway 处理流时发生未知错误 |

## 7. 会话历史

### 7.1 列出会话

```http
GET /api/v1/conversations?agent_id=requirement-pre-review&limit=20
```

`agent_id` 可省略；`limit` 为 1～100。

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

### 7.2 获取消息

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

其他用户的会话统一按不存在处理，返回 `404`。

### 7.3 删除会话

```http
DELETE /api/v1/conversations/{conversation_id}
```

```json
{ "ok": true }
```

数据库通过外键级联删除关联消息。对于 `requirement-pre-review`，Gateway 还会尽力请求 Agent 删除对应 LangGraph checkpoint。

## 8. 系统接口

### 8.1 存活检查

```http
GET /api/v1/health
```

```json
{ "status": "ok" }
```

只表示 Gateway 进程存活，不检查数据库、Agent、知识库或模型。

### 8.2 就绪检查

```http
GET /api/v1/readiness
```

成功响应 `200`：

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "agent:requirement-pre-review": "ok",
    "agent:ai-test-analysis": "ok",
    "agent:accounting-expert": "ok",
    "agent:business-analyst": "ok"
  }
}
```

数据库或任一已启用 Agent 不可用时返回 `503`，`status` 为 `degraded`。

## 9. Gateway → Agent 内部协议

所有已接入 Agent 必须实现：

```http
POST /v1/agent/chat
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "request_id": "req_...",
  "thread_id": "conv_...",
  "user_id": "4af5c21b583743da",
  "query": "分析这份需求是否完整",
  "attachments": [
    {
      "file_id": "file_...",
      "filename": "需求说明.md",
      "content_type": "text/markdown",
      "text": "由 Gateway 校验所有权并提取的文本"
    }
  ]
}
```

规则：

- `thread_id` 等于 Gateway `conversation_id`；
- Agent 不接收浏览器 Cookie，也不自行鉴权浏览器身份；
- Agent 不接收本地文件路径，只接收 Gateway 提取后的文本附件；
- Agent 返回 `progress`、`delta`、`completed`、`error`；
- Gateway 重新解析并白名单转发事件，不盲目透传上游数据；
- `GET /health` 只检查 Agent 进程存活，不调用 LLM。

Agent `completed` 示例：

```text
event: completed
data: {"request_id":"req_...","thread_id":"conv_...","answer":"完整回答","metadata":{"retrieval_count":5}}

```

## 10. HTTP 状态码

| 状态码 | 含义 |
|---:|---|
| `200` / `201` | 成功 |
| `400` / `422` | 请求或文件校验失败 |
| `401` | Session 缺失或过期 |
| `404` | 会话或附件不存在、过期或不属于当前用户 |
| `409` | 用户重复、会话与 Agent 不匹配、消息重复提交 |
| `503` | Agent 禁用或不可连接 |
| `504` | Agent 响应超时 |
