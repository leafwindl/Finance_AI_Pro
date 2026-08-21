# agent_gateway — Agent 端接口

**负责人：人员A**

## 职责

与外部 LangGraph Agent 服务通信。不碰数据库、不碰文件存储。

## 文件

| 文件 | 职责 |
|------|------|
| `registry.py` | Agent 注册表，维护 4 个 Agent 的 id/名称/地址/enabled/stateful |
| `client.py` | HTTP SSE 流式客户端，POST 到 `/v1/agent/chat`，返回标准化事件流 |
| `sse.py` | SSE 编解码：`encode_sse()` 编码、`parse_sse()` 解析（跨分块、CRLF/LF） |

## 对外接口（供 api/ 层调用）

### `build_registry(settings) -> dict[str, AgentDefinition]`

返回 4 个 Agent 的定义字典。调用方不直接写死端口号。

### `AgentClient(settings).stream(agent, payload) -> AsyncIterator[tuple[str, dict]]`

向 Agent 发送聊天请求，返回 `(event_type, data)` 的异步迭代器。

**输入 payload 格式：**
```json
{
    "request_id": "req_xxx",
    "thread_id": "conv_xxx",
    "user_id": "xxx",
    "query": "用户问题",
    "attachments": [
        {
            "file_id": "file_xxx",
            "filename": "需求.md",
            "content_type": "text/markdown",
            "text": "由 Gateway 提取后的文本"
        }
    ]
}
```

**输出事件类型：**

| event | data 关键字段 | 含义 |
|-------|-------------|------|
| `progress` | node, message | 阶段进度 |
| `delta` | text | 增量回答文本 |
| `completed` | answer, metadata | 最终回答 |
| `error` | code, message, retryable | 异常中止 |

**异常映射：**

| 场景 | 抛出异常 |
|------|---------|
| Agent 进程不可达 | `UpstreamServiceError(code="agent_unavailable", status=503)` |
| Agent 响应超时 | `UpstreamServiceError(code="agent_timeout", status=504)` |
| Agent HTTP >=400 | `UpstreamServiceError(code="agent_upstream_error", status=502)` |

## 不负责

- 不校验用户登录状态（由 api/ 层通过 `get_current_user` 处理）
- 不存储消息（由 data_gateway 处理）
- 不解析上传文件（由 knowledge_gateway 处理）

## 测试

```bash
uv run pytest app/agent_gateway/tests/
```

Mock 外部 Agent HTTP 服务即可，不需要数据库或真实文件。
