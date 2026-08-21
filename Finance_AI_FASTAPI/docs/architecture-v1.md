# Finance AI 第一版架构与实施说明（历史存档）

> 本文记录已下线的 Dify 方案，仅用于追溯，不代表当前运行架构。当前实现请参阅仓库根目录的 [`README.md`](../README.md) 和 [`gateway-api.md`](gateway-api.md)。

## 1. 文档目的

第一版用于熟悉 Vue3、FastAPI 与 Dify 之间的完整调用流程。FastAPI 只承担业务接口与 Dify 转接职责，不引入数据库、Redis、登录、权限或生产部署能力。

## 2. 第一版范围

包含：

- Vue3 提供智能体选择、问题输入和回答展示。
- FastAPI 暴露平台自己的聊天接口。
- FastAPI 在服务端保存并使用 Dify API Key。
- FastAPI 将问题转发给 Dify Chat API。
- Dify 根据应用内已有编排调用模型和知识库。
- FastAPI 将 Dify 回答转换为稳定的前端响应。
- Vue 在当前页面生命周期内保存 `conversation_id`，支持多轮对话。

暂不包含：

- 数据库和会话持久化。
- 用户登录、权限和多租户。
- Redis、限流和分布式任务。
- SSE 流式输出和停止生成。
- 多个智能体到多个 Dify 应用的动态映射。
- Docker、Nginx 和正式生产部署。

## 3. 总体架构

```text
Vue3 页面
   │
   │ POST /api/v1/chat
   ▼
FastAPI
   │ 参数校验、密钥注入、错误转换
   │ POST {DIFY_BASE_URL}/chat-messages
   ▼
Dify 应用
   │ 模型、工作流、知识库
   ▼
FastAPI
   │ 标准化回答
   ▼
Vue3 页面
```

### 3.1 Vue3 职责

- 收集用户问题。
- 调用 FastAPI，不直接调用 Dify。
- 展示加载、成功和失败状态。
- 保存 FastAPI 返回的 `conversation_id`，并在下一轮请求中带回。
- 点击“新对话”时清空本地 `conversation_id`。

### 3.2 FastAPI 职责

- 定义平台接口 `/api/v1/chat` 和 `/api/v1/health`。
- 使用 Pydantic 校验请求和响应。
- 从后端 `.env` 读取 Dify 地址、API Key、用户标识和超时时间。
- 组装 Dify 请求，固定使用 `blocking` 模式。
- 捕获超时、网络错误和 Dify 非成功响应。
- 只向 Vue 返回需要的字段，不暴露 Dify API Key。

### 3.3 Dify 职责

- 管理模型、提示词、知识库和应用编排。
- 根据 `query` 与 `conversation_id` 完成单轮或多轮问答。
- 返回最终回答。

FastAPI 不需要单独调用 Dify 知识库接口。只要知识库已在 Dify 应用中完成配置，调用聊天接口时就会由 Dify 内部执行知识检索。

## 4. API 契约

### 4.1 健康检查

```http
GET /api/v1/health
```

响应：

```json
{
  "status": "ok"
}
```

健康检查只表示 FastAPI 进程可用，不主动请求 Dify，避免产生额外调用。

### 4.2 发送消息

```http
POST /api/v1/chat
Content-Type: application/json
```

请求：

```json
{
  "query": "请解释一下资产负债率",
  "conversation_id": ""
}
```

字段约束：

- `query`：必填，去除首尾空格后长度为 1～2000。
- `conversation_id`：可选；第一次请求为空，后续传入上一次响应值。

成功响应：

```json
{
  "answer": "资产负债率是……",
  "conversation_id": "dify-conversation-id",
  "message_id": "dify-message-id"
}
```

上游错误响应示例：

```json
{
  "error": {
    "code": "dify_upstream_error",
    "message": "Dify 请求失败"
  }
}
```

## 5. Dify 请求映射

FastAPI 向 Dify 发送：

```json
{
  "inputs": {},
  "query": "用户问题",
  "response_mode": "blocking",
  "conversation_id": "已有会话 ID 或空字符串",
  "user": "finance-ai-web"
}
```

请求头由 FastAPI 添加：

```http
Authorization: Bearer {DIFY_API_KEY}
Content-Type: application/json
```

## 6. 目录结构

```text
Finance_AI/
├─ Backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ api/chat.py
│  │  ├─ core/config.py
│  │  ├─ core/exceptions.py
│  │  ├─ schemas/chat.py
│  │  └─ services/dify.py
│  ├─ tests/
│  ├─ .env
│  ├─ .env.example
│  └─ pyproject.toml
├─ Vue/
│  ├─ src/components/DifyChat.vue
│  ├─ src/services/api/chat.js
│  ├─ .env.example
│  └─ vite.config.js
└─ doc/architecture-v1.md
```

## 7. 配置说明

后端 `Backend/.env`：

```dotenv
DIFY_BASE_URL=https://api.dify.ai/v1
DIFY_API_KEY=app-xxxxxxxxxxxxxxxx
DIFY_USER=finance-ai-web
DIFY_TIMEOUT_SECONDS=60
```

为了兼容原开发配置，后端同时接受 `DIFY_ORIGIN`。当地址不以 `/v1` 结尾时，后端会自动补充 `/v1`。

前端 `Vue/.env.local` 可选配置：

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

前端环境变量中不得再出现 Dify API Key。

## 8. 本地启动流程

### 8.1 启动 FastAPI

```powershell
cd Backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

可访问：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

### 8.2 启动 Vue

```powershell
cd Vue
npm install
npm run dev
```

访问 `http://127.0.0.1:83`。Vite 固定监听 `127.0.0.1:83`，并将浏览器的 `/api` 请求代理到 `http://127.0.0.1:8000`，FastAPI 再请求 Dify。如果 83 端口已被占用，Vite 会直接报错，不会静默切换到其他端口。

FastAPI 会在终端记录请求进入、Dify 调用开始、响应状态和耗时。日志不记录 Dify API Key、问题正文或回答正文。

## 9. 错误处理约定

- 请求字段不合法：FastAPI 返回 `422`。
- Dify 请求超时：FastAPI 返回 `504`。
- 无法连接 Dify：FastAPI 返回 `502`。
- Dify 返回非成功状态：FastAPI 返回 `502`。
- Dify 返回无法识别的结果：FastAPI 返回 `502`。

第一版不自动重试聊天请求，避免同一问题被重复提交给 Dify。

## 10. 验收标准

- Vue 源码和 Vite 配置中不存在 Dify API Key 注入逻辑。
- 浏览器只请求 `/api/v1/chat`。
- FastAPI 能从 `.env` 读取 Dify 配置并完成转发。
- 第一次提问能获得回答和 `conversation_id`。
- 第二次提问能携带同一 `conversation_id` 完成多轮对话。
- “新对话”能够清空当前会话。
- Dify 超时或报错时，Vue 能展示可读错误。
- 后端自动化测试通过，前端生产构建通过。

## 11. 后续演进

完成第一版并熟悉调用链后，可按实际需求依次增加：SSE 流式响应、多 Dify 应用映射、用户认证、数据库会话持久化、日志审计和正式部署。后续能力应继续保持 Vue 只依赖 FastAPI API 契约，不直接依赖 Dify 协议。
