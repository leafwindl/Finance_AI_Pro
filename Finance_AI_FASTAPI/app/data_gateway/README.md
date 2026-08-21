# data_gateway — 数据库端接口

**负责人：人员B**

## 职责

负责 PostgreSQL 数据持久化与用户维度的数据隔离，提供会话、消息、附件元数据的读写能力。它不负责 Agent 通信、不负责文件内容解析、不负责登录鉴权。

## 文件

| 文件 | 职责 |
|------|------|
| `pool.py` | asyncpg 连接池，供 api 层通过 `get_pool` 依赖注入使用 |
| `repositories/conversations.py` | 会话、消息的创建、查询、删除与失败状态更新 |
| `repositories/files.py` | 上传文件元数据的创建和权限可见性查询 |

## 数据库连接

当前通过项目根目录 `.env` 中的配置项读取连接信息：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `DB_HOST` | 数据库地址 | `localhost` |
| `DB_PORT` | 数据库端口 | `5432` |
| `DB_NAME` | 数据库名 | `knowledge_agent` |
| `DB_USER` | 数据库用户 | `postgres` |
| `DB_PASSWORD` | 数据库密码 | 无默认值，必须在 `.env` 中填写 |

`.env` 模板文件为项目根目录的 `.env.example`，可复制后修改：

```bash
cp .env.example .env
# 然后编辑 .env，填入 DB_PASSWORD
```

迁移脚本位于 `scripts/apply_migrations.py`，SQL 文件位于 `database/`。

## 对外接口（供 api/ 层调用）

### 会话

| 函数 | 输入 | 输出 |
|------|------|------|
| `create_conversation(pool, *, conversation_id, user_id, agent_id, title)` | 会话信息（keyword-only） | Record |
| `get_owned_conversation(pool, conversation_id, user_id)` | 会话 id + 用户 id | Record 或 None |
| `list_owned_conversations(pool, *, user_id, agent_id, limit)` | 用户 id + 可选筛选（keyword-only） | list[dict] |
| `delete_owned_conversation(pool, *, conversation_id, user_id)` | 会话 id + 用户 id（keyword-only） | bool |

### 消息

| 函数 | 输入 | 输出 |
|------|------|------|
| `insert_user_message(pool, *, conversation_id, content, request_id, client_message_id)` | 消息内容 + 幂等键（keyword-only） | `message_id` 或 `None`（重复提交） |
| `insert_assistant_message(pool, *, conversation_id, content, request_id, metadata)` | AI 回复内容与元数据（keyword-only，metadata 可选） | `message_id` |
| `list_owned_messages(pool, *, user_id, conversation_id)` | 用户 id + 会话 id（keyword-only） | list[dict] 或 `None`（无权限/不存在） |
| `mark_request_failed(pool, *, request_id, error_code)` | 请求 id + 错误码（keyword-only） | — |

### 文件

| 函数 | 输入 | 输出 |
|------|------|------|
| `create_file_record(pool, *, file_id, user_id, filename, content_type, extension, size_bytes, storage_path, ttl_seconds)` | 文件元数据（keyword-only） | — |
| `get_owned_ready_files(pool, *, user_id, file_ids)` | 用户 id + 文件 id 列表（keyword-only） | list[dict] |

## 安全约束（必须保证）

1. **所有权隔离**：所有查询必须带 `user_id` 条件，尤其是会话、消息和附件记录。
2. **SQL 注入防护**：全部使用 `$1/$2` 参数化，禁止字符串拼接。
3. **幂等**：`insert_user_message` 依赖 `(conversation_id, client_message_id)` 唯一索引，重复提交会返回 `None`。
4. **失败标记**：`mark_request_failed` 会更新用户消息的状态、错误码和元数据，供前端做重试提示。
5. **TTL 过期**：`get_owned_ready_files` 只返回 `status='ready'` 且 `expires_at > NOW()` 的附件，避免过期文件被继续使用。

## 不负责

- 不调用 Agent（由 `agent_gateway` 处理）
- 不解析文件内容（由 `knowledge_gateway` 处理）
- 不做用户鉴权（由 `api/` 层通过 `get_current_user` 处理）
- 不承担 SSE 流式响应编排（由 `api/chat.py` 处理）

## 测试

### 数据库直连测试（推荐日常开发使用）

`app/data_gateway/test_data_gateway.py` 直接连接本地 PostgreSQL，测试所有 repository 函数的实际数据库读写行为，包括会话 CRUD、消息 CRUD、文件元数据、幂等性、所有权隔离、失败标记和边界情况。每次运行自动清理测试数据。

```bash
python app/data_gateway/test_data_gateway.py
```

前置条件：本地 PostgreSQL 已启动、`knowledge_agent` 库已创建、迁移已执行、`.env` 中 `DB_PASSWORD` 已配置。

### 契约测试（Mock，不依赖数据库）

位于 `tests/`，使用 FastAPI TestClient + 依赖注入 Mock，不连接真实数据库：

```bash
pytest -q tests/ -v
```
