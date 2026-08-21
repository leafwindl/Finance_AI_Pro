# Finance AI Vue

Finance AI 的 Vue 3 前端。浏览器只访问 FastAPI Gateway，不直接访问 Agent、知识库或数据库。

## 运行

要求 Node.js 18+。

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

默认地址为 `http://127.0.0.1:84`，开发代理把 `/api` 转发到 `http://127.0.0.1:8000`。

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

生产构建：

```powershell
npm run build
```

## 接口契约

用户需要先通过 `/api/v1/auth/register` 或 `/api/v1/auth/login` 登录。会话 Cookie、对话、消息和文件都由 Gateway 管理。

完整请求、响应、SSE 事件和错误码见 [Gateway 接口契约](docs/gateway-api.md)。数据库职责和前端缓存边界见 [数据持久化边界](docs/database-api.md)。

发送消息：

```http
POST /api/v1/chat
Content-Type: application/json
```

```json
{
  "query": "分析这份需求是否完整",
  "conversation_id": null,
  "agent_id": "requirement-pre-review",
  "file_ids": [],
  "client_message_id": "browser-generated-uuid"
}
```

响应为 `text/event-stream`。前端处理四种统一事件：

- `progress`：阶段进度；
- `delta`：增量回答文本；
- `completed`：最终结果及 Gateway 的会话、消息 ID；
- `error`：结构化错误。

文件先上传到 `POST /api/v1/files/upload`，聊天请求只传返回的 `file_id`。支持 `pdf/docx/xlsx/md/txt/csv/json`。

会话历史使用：

- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `DELETE /api/v1/conversations/{conversation_id}`

智能体可用性由 `GET /api/v1/agents` 决定。四个稳定 Agent ID 均已接入，`accounting-expert` 对应 Agent3 测试用例评审服务。

会话由第一次聊天自动创建，前端不主动创建会话，也不直接写入用户或 assistant 消息。

### agent5 悬浮助手（多轮记忆 + 流程图）

- **会话 ID 字段名**：Agent 内部叫 `thread_id`，**网关归一化后的事件字段是 `conversation_id`**——前端保存会话 ID 必须读 `data.conversation_id`（兼容 `?? data.thread_id`），并持久化到 `localStorage`（键 `agent5_conv_id`），刷新页面后继续用旧会话（多轮记忆才接得上）。
- **业务流程可视化**：`FlowVisualizer.vue` 组件，SSE `progress` 事件真实节点驱动（节点名与 Agent 侧 `ASSISTANT_NODE_PROGRESS` 一致），`completed` 全绿 / `error` 标红。
- 完整契约见 Agent 侧 `docs/规范与解释/接口契约总表.md` §8（记忆）/ §6.2（节点表）。

## 主要技术

Vue 3、Vite 5、Pinia、Vue Router、Element Plus。最初的界面设计与组件说明见 [DESIGN_DOC.md](DESIGN_DOC.md)；其中历史架构描述不作为当前接口依据。

## 更新改动记录

| 日期 | 改动 |
|------|------|
| 2026-08-10 | 新增 `FlowVisualizer.vue`（agent5 业务流程图，SSE 真实节点驱动，对齐契约 §6.2）；GlobalAssistant 集成；**修复会话 ID 字段**（读 `conversation_id` 非 `thread_id`）+ convId localStorage 持久化（刷新不丢记忆） |
