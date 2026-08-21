# 智能体预选问题接口提案

> 状态：尚未实现，不属于当前联调链路。当前建议问题来自 `src/data/agents.json` 的本地问题池。本文仅保留为后续扩展设计，不能作为现有 Gateway 接口调用。

> 版本：v1.0 | 状态：待对接 | 2026-07-20

---

## 1. 概述

前端已实现「预选问题随机池」模式，每个智能体配置 20 条静态问题，每次进入对话随机展示 3 条。
本接口用于**替换静态池**，由后端 AI 根据上下文动态生成更精准的预选问题。

## 2. 接口定义

### 2.1 获取预选问题

```
GET /api/v1/suggestions/{agent_id}
```

### 2.2 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| agent_id | path | string | 是 | 智能体 ID，如 `accounting-expert`、`business-analyst` |
| conversation_id | query | string | 否 | 当前会话 ID，传入后后端可基于历史上下文生成更精准的问题 |
| count | query | int | 否 | 返回数量，默认 3，范围 1-5 |

### 2.3 响应格式

**成功 (200)**
```json
{
  "code": 0,
  "data": {
    "questions": [
      "检查用例是否覆盖所有功能点",
      "识别用例中的边界条件遗漏",
      "评审异常场景覆盖是否充分"
    ]
  }
}
```

**智能体不存在 (404)**
```json
{
  "code": 404,
  "detail": "Agent 'unknown-agent' not found"
}
```

**服务异常 (500)**
```json
{
  "code": 500,
  "detail": "Internal server error"
}
```

## 3. 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| code | int | 业务状态码，0 表示成功 |
| data.questions | string[] | 预选问题列表，长度 1-5 |
| detail | string | 错误描述（失败时） |

## 4. 前端对接方式

前端 `store.getSuggestedQuestions(agentId)` 已预留切换逻辑，接入时**只需改一处**：

```js
// src/stores/agents.js — 当前（静态池）
function getSuggestedQuestions(agentId) {
  const agent = agents.value.find(a => a.id === agentId)
  const pool = agent.questionPool || agent.suggestedQuestions
  // Fisher-Yates 洗牌取 3 条
}

// 切换后（API + 降级）
async function getSuggestedQuestions(agentId) {
  try {
    const res = await fetch(`/api/v1/suggestions/${agentId}`)
    const json = await res.json()
    return json.data.questions        // ← 后端返回
  } catch {
    // 降级到本地 questionPool
    const agent = agents.value.find(a => a.id === agentId)
    const pool = agent.questionPool || agent.suggestedQuestions || []
    // Fisher-Yates 取 3 条
  }
}
```

**下游组件无需任何改动。**

## 5. 当前智能体 ID 清单

| agent_id | 名称 | 已有静态池 |
|------|------|------|
| `requirement-pre-review` | 需求预评审智能体 | 3 条 |
| `ai-test-analysis` | 需求AI测试分析智能体 | 3 条 |
| `accounting-expert` | 测试用例评审智能体 | 20 条 |
| `business-analyst` | 测试用例步骤生成智能体 | 20 条 |

## 6. 后端实现建议

- **框架**：FastAPI（项目已用）
- **AI 层**：Dify Workflow 或 LangGraph Agent 生成问题
- **缓存**：同一 agent + conversation 组合可缓存 5 分钟，避免频繁调用 LLM
- **超时**：建议 3 秒内返回，超时前端自动降级到静态池
- **限流**：单用户每分钟最多 10 次请求

## 7. 测试用例

```bash
# 正常请求
curl http://127.0.0.1:8000/api/v1/suggestions/accounting-expert

# 带会话上下文
curl "http://127.0.0.1:8000/api/v1/suggestions/accounting-expert?conversation_id=conv_001"

# 指定返回数量
curl "http://127.0.0.1:8000/api/v1/suggestions/business-analyst?count=5"

# 不存在的智能体
curl http://127.0.0.1:8000/api/v1/suggestions/unknown-agent
```

## 8. 降级策略

```
API 调用
  ├── 成功 → 返回 AI 生成的问题
  └── 失败（超时/500/网络错误）
        └── 自动降级 → 本地 questionPool 随机抽取 3 条
```

前端已实现完整的降级链路，后端可随时接入，不影响现有功能。
