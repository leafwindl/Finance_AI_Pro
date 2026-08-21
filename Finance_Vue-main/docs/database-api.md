# 数据持久化边界

> 版本：v2.0
> 状态：已联调

完整 HTTP 请求和响应格式见 [Gateway 接口契约](gateway-api.md)。本文只说明前端、Gateway 和数据库之间的职责边界。

## 1. 数据流

```text
Vue
  -> FastAPI Gateway
     -> knowledge_agent PostgreSQL
        - users
        - user_sessions
        - conversations
        - messages
        - uploaded_files
```

前端不直接连接数据库，也不持有数据库账号或密码。所有读写都由 Gateway 在当前 Session 用户范围内完成。

## 2. 当前事实来源

| 数据 | 事实来源 | 前端处理 |
|---|---|---|
| 当前用户 | Gateway Session | 启动时调用 `GET /api/v1/auth/me` |
| Agent 能力 | Gateway Agent Registry | 登录后调用 `GET /api/v1/agents` |
| 会话列表 | PostgreSQL | 调用 `GET /api/v1/conversations` |
| 历史消息 | PostgreSQL | 打开会话时按需加载 |
| 文件元数据 | PostgreSQL | 上传成功后仅保存临时 `file_id` |
| 主题 | 浏览器 localStorage | 与业务数据无关 |
| 会话 UI 缓存 | 按用户隔离的 localStorage | 仅用于界面恢复，数据库仍是事实来源 |

## 3. 写入规则

- 注册、登录和退出由 `/api/v1/auth/*` 处理。
- 首次聊天由 `POST /api/v1/chat` 自动创建会话。
- 用户消息由 Gateway 幂等写入，前端提供 `client_message_id`。
- assistant 消息只能由 Gateway 在 Agent 成功完成后写入。
- 前端不调用“手工创建会话”或“手工新增消息”接口。
- 文件必须先上传，聊天请求只引用当前用户拥有的 `file_id`。
- 删除会话使用 `DELETE /api/v1/conversations/{conversation_id}`。

## 4. Cookie Session

鉴权使用 HttpOnly Session Cookie。前端通过 `credentials: 'include'` 自动携带 Cookie，不在 JavaScript、Pinia 或 localStorage 中保存 token。

不同用户的本地 UI 缓存 key 为：

```text
finance_ai_conversations:{user_id}
```

退出后内存中的用户和会话状态会被清空，其他用户无法复用当前用户的 UI 缓存。
