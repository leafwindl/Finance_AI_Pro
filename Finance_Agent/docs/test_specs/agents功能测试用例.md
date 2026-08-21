# Agents 功能测试用例

> 用途：对话类智能体（agent3 / agent5）的联调测试样例模板，供开发与回归验证使用。
> 调用方式：`POST /v1/agent/chat`（SSE 流式），字段说明见 `docs/规范与解释/接口契约总表.md`。

---

## 一、agent3 用例评审（accounting-expert）

**输入**：`query` = 待评审的测试用例文本（支持贴入多条用例）
**输出**：评审报告 + `pass_flag` + `coverage` + `checklist`（18 项 ISTQB 清单）

### 模板

```json
{
  "request_id": "t3_<日期序号>",
  "thread_id": "conv_t3_001",
  "user_id": "u1",
  "agent_id": "accounting-expert",
  "query": "<待评审的测试用例文本>",
  "attachments": []
}
```

### 用例 1：标准用例评审（正常流）

- **输入 query**：

```
用例1：正确用户名密码登录
前置条件：用户已注册，账号未被锁定
步骤：输入正确的用户名和密码，点击登录
预期：登录成功，跳转首页

用例2：密码错误登录
前置条件：用户已注册
步骤：输入正确的用户名和错误的密码，点击登录
预期：提示"用户名或密码错误"，停留在登录页
```

- **期望结果**：
  - `progress` 事件：3~7 个节点进度
  - `completed` 事件：`metadata.pass_flag` 为 true/false 之一、`coverage` 为分数、`checklist` 为 18 项明细
  - `answer` 含评审报告 Markdown

### 用例 2：单条用例边界评审（覆盖可执行性）

- **输入 query**：仅 1 条用例，且预期步骤含"随便""等一会儿"等不可执行描述
- **期望结果**：`checklist` 中"可执行性"项被标记为不通过（`pass_flag` 受影响的场景）

### 用例 3：空输入 / 非法输入（异常流）

- **输入 query**：空字符串 / 纯空格
- **期望结果**：`error` 事件（`code: agent_execution_failed`）或明确降级回答，不抛 500

---

## 二、agent5 智能对话助手（ai-assistant）

**输入**：`query` + 可选 `attachments`
**输出**：SSE 事件（progress → delta → completed），`metadata.intent` 标记意图

### 模板

```json
{
  "request_id": "t5_<日期序号>",
  "thread_id": "conv_t5_001",
  "user_id": "u1",
  "agent_id": "ai-assistant",
  "query": "<对话内容>",
  "attachments": []
}
```

### 用例 1：闲聊（intent=chat）

- **输入 query**：`你好` / `我叫小明` / `刚才说的什么意思`
- **期望结果**：`completed.metadata.intent = "chat"`，`delta` 流式输出自然语言回答

### 用例 2：知识库问答（intent=kb_query）

- **输入 query**：`登录功能标准测试用例有哪些？`（含知识库关键词）
- **期望结果**：`intent = "kb_query"`，回答基于 KB 检索内容（引用 KB04/05/06），非空且与知识库内容相关

### 用例 3：文档问答（intent=doc_qa）

- **输入**：`query` = `这份文档讲了什么？`，`attachments` 带 1 个文档：

```json
{
  "request_id": "t5_003",
  "thread_id": "conv_t5_001",
  "user_id": "u1",
  "agent_id": "ai-assistant",
  "query": "这份文档讲了什么？",
  "attachments": [
    {
      "file_id": "f1",
      "filename": "需求说明.txt",
      "content_type": "text/plain",
      "text": "系统需要支持用户注册、登录、忘记密码功能……"
    }
  ]
}
```

- **期望结果**：`intent = "doc_qa"`，回答内容与附件 `text` 内容一致（能说出"讲了注册/登录/忘记密码"）

### 用例 4：转交（intent=transfer_propose/confirm/cancel，2026-08-20 起两段确认 + 前端跳转）

- **输入 query（第一段：提议）**：`帮我预评审这段需求：员工考勤系统需支持打卡、请假……`
- **期望结果**：`completed.metadata.intent = "transfer_propose"`，回答为确认询问「将跳转到 requirement-pre-review，确认吗？」
- **同会话第二段：确认**：`query = 确认`
- **期望结果**：`completed.metadata.intent = "transfer_confirm"`，且 `metadata.transfer = {target: "requirement-pre-review", query: "<第一段原话>"}`（前端据此跳转 agent 页自动发起）
- **改口/取消**：`query = 算了` → `metadata.intent = "transfer_cancel"`，停留在 agent5

### 用例 5：多意图边界（意图识别准确性，2026-08-20 升级 6 态）

| 输入 query | 期望 intent | 说明 |
|-----------|------------|------|
| `今天天气怎么样` | chat | 闲聊词，不进知识库 |
| `缺陷模式有哪些` | kb_query | 知识库关键词 |
| `随便聊聊` | chat | 非知识关键词 |
| `帮我评审用例：……` | transfer_propose | 提议转交 agent3（第一段确认） |
| `确认`（上轮 pending 时） | transfer_confirm | 确认跳转 |
| `算了`（上轮 pending 时） | transfer_cancel | 取消跳转 |

---

## 三、通用断言清单（两个 agent 共用）

1. 事件顺序合法：`progress` 在 `delta` 前，最终必有 `completed` 或 `error`（不存在挂起）
2. `request_id` 回显：所有事件 `data.request_id` 与请求一致
3. 无 `error` 事件时必有 `completed`，且 `answer` 非空
4. 异常不 5xx：KB 停掉 / 模型超时场景下返回 `error` 事件（带 `retryable`），服务进程不崩
5. 响应时间：首事件（progress）≤ 5s，全流程 ≤ 180s
