# Agent5 对话调度改造方案（2026-08-14）

> 状态：**方案已实施（2026-08-20）**——handler/graph/state/server/前端 GlobalAssistant 均已落地，实跑验证通过（意图 11/11、跳转指令 metadata.transfer 生效）；本文件保留作为设计文档。
> 目标：通过 agent5 对话调度 agent1~4 跑通全流程（需求预评审 → 六维分析 → 用例评审 → 步骤生成）
> **核心红线：所有 agent 的回答只能依据知识库（Finance_Knowledge-main 六库）内容，库外一律拒绝/标注，禁止编造**（grounding 硬约束部分待实施，见 §0）

## 0. grounding 硬约束（全 agent 统一红线，2026-08-14 新增）

**背景**：业务需求必须是知识库覆盖的业务。例如业务人员要改登录方式，但知识库中平台无登录方式相关内容 → 需求预评审（agent1）应直接拒绝，而非出报告。

**知识库唯一事实来源（实测确认）**：
- 数据源 = `Finance_Knowledge-main/` 六库（89 文件 / 713 分段），由 `Finance_AI_KnowledgeBase/lightweight_kb_server.py`（8002）加载
- **注意**：`Finance_Agent/docs/` 下的 `standard_cases` / `test_specs` / `history_defects` 是参考文档，**不参与实际检索**，不是知识库来源

### 各 agent 硬约束要求

| Agent | 约束 | 实现位置 |
|---|---|---|
| **agent1 预评审** | 检索不到需求核心业务 → **直接拒绝**（不生成报告正文）；检索命中才正常评审 | `agent1/prompts.py` 报告/风险 prompt 顶部 |
| **agent2 六维分析** | 只依据检索上下文；未检索到维度写"知识库未收录" | `agent2/prompts/rag_prompt.txt` |
| **agent3 用例评审** | 对照 KB 证据评审；KB 无依据检查项判 FAIL | `agent3/prompts/review_prompt.py` |
| **agent4 步骤生成** | 步骤必须基于召回知识，未覆盖禁止编造 | `agent4/.../llm_gen_json_node.py` prompt |
| **agent5 对话助手** | 业务问题只依据检索结果；检索不到明确说"知识库未收录"；纯闲聊可正常答；检索缺 KB02/KB03 需补全 | `agent5/core/handler.py` + 检索 `kb_codes` |

### 硬约束模板（agent1 示例，写进 prompt 顶部）

```text
# 强制硬性规则（不符合即拒绝）

1. 本需求评审的唯一依据是"知识库检索结果"。
2. 检索节点执行后：若【该需求的核心业务/功能】在知识库中【检索不到对应内容】，则判定该需求【超出平台知识范围】，直接输出拒绝结论：
   - 明确写"该需求涉及【XX】在知识库中未收录，平台不支持该业务，予以拒绝"
   - 不生成需求完整性分析、不生成风险评估、不生成报告正文
3. 只有知识库检索到该需求的对应业务内容时，才允许正常进行完整性/风险评估并生成报告。
4. 检索结果与需求主题无关（如需求是交易类，检索命中的全是登录类）时，同样按第 2 条拒绝。
```

### 验证样例（验收口径）

| 样例 | 类型 | 预期 |
|---|---|---|
| A. 登录认证增强（手机号+密码+短信验证码+适当性） | 应过 | 命中 KB01/KB02/KB04/KB05 → 正常报告 |
| B. 批量委托下单（市价/限价/订单生命周期） | 应过 | 命中 KB01/KB03/KB04/KB05 → 正常报告 |
| C. 资金校验（资金不足拒单/超持仓拒单/金额精度） | 应过 | 命中 KB01/KB03/KB04 → 正常报告 |
| D. 客户画像重构/智能推荐 | 应拒 | 知识库无 CRM/画像内容 → agent1 拒绝 |
| E. 加密货币交易 | 应拒 | 完全不在证券知识库 → agent1 拒绝 |
| F. 量价因子选股模型 | 应拒 | 无量化/ML 内容 → agent1 拒绝 |
| G. 登录认证+人脸识别 | 边缘 | 命中部分引库，未收录部分标注"知识库未收录" |

## 1. 现状与问题

- `transfer_agent` 只有关键词判断 + 进程内代跑（缺 agent2、无进度/审批、绕开统一层）
- 前端 GlobalAssistant 实测只覆盖 chat/kb_query/doc_qa 三意图，transfer 无 UI 触发路径
- 需求方案文档（agent5_智能对话助手_需求方案.md §2.4）只写了转 agent1/3，agent2 从未在设计里

## 2. 方案评审确认结论

| 问题 | 定案 |
|---|---|
| Q1' 调度路径 | **前端跳转**：agent5 识别意图 → 发跳转指令 → 前端 GlobalAssistant 跳 agent 页带 q → agent 自己跑（进度/审批完整） |
| Q2' 补 agent2 | **要**：六维分析也能对话触发 |
| Q6 跳转后悬浮球 | **保留**（只关对话框） |
| Q7 触发边界 | **宽松触发** + agent5 对话确认（两段确认①） |
| Q8/Q10 跳转前 | **弹窗确认** + 需求内容预填用户原话**可编辑**（两段确认②） |
| Q9 改口 | **以新说为准**（一次对话可切换目标） |
| Q11 会话 | **新建会话**（pid=custom_<ts>，需求追踪自动收录） |

## 3. 交互流程（两段确认）

```
用户对话 → agent5 宽松检测转交意图（预评审/六维/用例评审/生成步骤）
   │
   ▼
① agent5 对话确认：「我检测到你想调用需求预评审，确认吗？」
   ├─ 否认/改口 → 回普通对话（以新说为准）
   └─ 确认
   ▼
② 前端弹窗确认：预填需求内容（=用户原话，可编辑）「将跳转到需求预评审智能体」
   ├─ 取消 → 留在 agent5 继续
   └─ 确认 → 跳转 /chat/<target>?q=<内容>&pid=custom_<ts>（新建会话，agent 自动发起）
```

## 4. 改动清单（只动 Finance_Agent 智能体 + Finance_AI_Vue 前端，网关零改动）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `src/agents/agent5/core/handler.py` | `recognize_intent` 升级：宽松转交检测 + 确认/否定判断 + 多轮记忆检查 → 新意图 `transfer_propose` / `transfer_confirm` / `transfer_cancel` |
| 2 | `src/agents/agent5/core/graph.py` | `transfer_agent` 从"代跑 agent 图"改为"生成转交指令"（target + query），不再实际调 agent1~4 |
| 3 | `src/agents/agent5/core/state.py` | 加 `transfer_target` / `transfer_query` 字段 |
| 4 | `src/api/server.py` | `_stream_ai_assistant` completed 的 metadata 多带 transfer 指令（接口格式不变） |

## 5. 接口契约

- 对外 SSE（Gateway `/api/v1/chat`）**零变更**；网关/数据库/agent1~4 全不动。
- completed 事件 metadata 新增字段：`transfer: { target: agent_id, query: string }`。

## 6. 验证计划

1. curl 验证 3 意图（propose 询问 / confirm 锁定 / cancel 取消）
2. 浏览器实测：GlobalAssistant 对话 → 确认 → 弹窗 → 跳转 agent1 页自动发起预评审
3. 截图留底

## 7. 目标关键词映射

| 用户话术 | 目标 agent_id |
|---|---|
| 预评审 / 需求评审 / 建需求 / 新建需求 | `requirement-pre-review` |
| 六维 / 分析需求 / 测试分析 | `ai-test-analysis` |
| 用例评审 / 评审用例 | `accounting-expert` |
| 步骤生成 / 生成步骤 / 测试步骤 | `business-analyst` |
