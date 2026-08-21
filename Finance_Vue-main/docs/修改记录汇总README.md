# 修改记录汇总（精简版）
## 目录
1. [08-07 项目运行环境修复]
2. [08-07 预评审执行失败修复]
3. [08-07 测试用例评审18项全失败修复]
4. [08-07 主界面测试用例流程卡片按钮删除]
5. [08-07 主界面测试用例流程动态卡片]
6. [08-07 主界面被驳回用例卡片状态修复]
7. [08-07 主界面待审批用例卡片状态符号]
8. [08-07 通过并继续无法进入六维分析修复]
9. [08-07 测试用例流程面板卡片状态分阶段]
10. [08-07 已跑完用例点击呈现预评审报告]
11. [08-08 预评审报告查看六维分析按钮]
12. [08-08 六维分析报告缺少会话ID修复]
13. [08-08 测试用例工作台查看预评审六维报告按钮]
14. [08-10 被驳回用例恢复Agent34结果]
15. [08-10 文件上传entry改为reactive响应式]
16. [08-10 全局助手GlobalAssistant挂载]
17. [08-10 网关注册表新增ai-assistant]
18. [08-10 全局助手悬浮球可拖拽]
19. [08-17 项目首次启动与环境修复]
20. [08-17 需求卡片状态按用户隔离修复]
21. [08-17 GlobalAssistant 移除心情图系统]
22. [08-17 需求追踪界面新增删除按钮]
23. [08-17 侧边栏需求追踪列表]
24. [08-17 知识库文档上传入口（前端）]
25. [08-20 知识图谱与知识库文档查看迁移（前端）]
26. [08-20 知识库文档上传 V2 适配（前端）]
---

## 08-07 项目运行环境修复

- **问题**：首次启动完整项目（KnowledgeBase / Gateway / Vue）遇到环境依赖问题。
- **改动**：
  - KnowledgeBase `requirements.txt`：`elasticsearch` 版本收窄为 `<9.0.0`（客户端 9.x 不兼容 ES 8.15）。
  - 补写宿主机 PG `schema_migrations` 5 条已应用迁移记录（宿主机与 Docker 双 Postgres 并存，索引已存在导致重跑报错）。
  - 新建 3 个 `.env`（复制自 example，填 DeepSeek Key）；补建 Vue 缺失的 `src/data/agents.json`（4 智能体，对齐网关注册表）。
- **验证**：迁移全部 skip；KnowledgeBase 重建 4 文档/40 切片；前端 HTTP 200。

## 08-07 预评审执行失败修复

- **问题**：预评审提示"智能体执行失败"。
- **根因**：langchain-openai 新版默认发 `response_format=json_schema`，DeepSeek 只支持 `json_object` → 首个节点 400。
- **改动**：agent1 的 4 个节点（requirement_parser / keyword_extractor / six_points_eval / risk_assessment）`with_structured_output(method="json_mode")` + try/except 降级。
- **验证**：全流水线跑通，返回 `approval_required` 完整报告。

## 08-07 测试用例评审18项全失败修复

- **问题**：ISTQB 18 项检查清单全显示"模型未返回该检查项"。
- **根因**：`normalize_checklist()` 全名精确匹配，模型返回无前缀名（如"功能场景覆盖"）与代码侧前缀名（"覆盖完整性-功能场景覆盖"）全部错位 → 0/18。
- **改动**：`review.py` 新增 `_item_key()` 去前缀双向匹配 + `_extract_json()` 兼容推理前缀/冗余文字。
- **验证**：命中 17/18。

## 08-07 主界面测试用例流程卡片按钮删除

- **改动**：`DashboardView.vue` 删除 tc 面板 8 张用例卡片及"自定义测试用例编写"入口，仅保留面板外壳。
- **验证**：vite build 通过。

## 08-07 主界面测试用例流程动态卡片

- **改动**：`DashboardView.vue` 将已通过预审批+六维的需求动态放入 tc 面板；req 面板只留未通过卡片（通过的下沉）；`onCardClick` 分发、`goTc()` 携六维会话跳转用例编写。
- **验证**：vite build 通过。

## 08-07 主界面被驳回用例卡片状态修复

- **问题**：r4 已驳回但卡片显示 → 而非 ❌。
- **根因**：`statuses` 读 localStorage 一次性快照（非响应式），且部分跳转入口不带 `pid` 导致审批后不写标记。
- **改动**：`statuses` 改 computed 从真实会话审批数据推导（任一通过→approved/驳回→rejected）；`onMounted` 预加载匹配会话；`go()` 已有会话跳转补 `pid`。
- **验证**：vite build 通过。

## 08-07 主界面待审批用例卡片状态符号

- **改动**：`statuses` 聚合扩展为三态（通过>驳回>待审批）；新增 `pending` 显示 ⏳。
- **验证**：vite build 通过。

## 08-07 通过并继续无法进入六维分析修复

- **问题**：r5"通过并继续"无法进入六维分析。
- **根因**：Agent 平台 `_pending_approvals` 为进程内存态，重启后丢失 → 审批返回 409。
- **改动**：`Finance_AI_FASTAPI/app/api/chat.py` 对 409 降级为以数据库为准（`decide_review` 原子更新 pending→approve），仍拒绝非法/重复审批。
- **验证**：降级路径正常跳转六维分析。需重启 Gateway 生效。

## 08-07 测试用例流程面板卡片状态分阶段

- **问题**：固定卡片进 tc 面板即 ✅，动态卡片需跑完 Agent3+4 才 ✅，行为不一致。
- **根因**：`card_status` 被预评审与用例流程共用同一 key。
- **改动**：`TestCaseEditor` 改独立 `localStorage.tc_card_status`；`DashboardView` 新增 `tcStatuses` 分面板显示（tc 进入即 ⏳，确认后 ✅）。
- **验证**：vite build 通过。

## 08-07 已跑完用例点击呈现预评审报告

- **改动**：`DashboardView.onCardClick` 对 ✅（跑完四智能体）卡片走 `openPreReview` 跳预评审工作台呈现报告；⏳/❌ 仍进入用例编写。
- **验证**：vite build 通过。

## 08-08 预评审报告查看六维分析按钮

- **改动**：`ReviewReportCard` 新增"查看六维分析"按钮（仅已通过态，位于下载按钮左侧）；`ChatView.handleViewSixDim` 匹配已有六维会话或发起新分析。
- **补充**：六维报告从 `pre-review` 入口隐藏"进入测试流程"按钮（`hideNext` prop）。
- **验证**：vite build 通过。

## 08-08 六维分析报告缺少会话ID修复

- **问题**：六维报告页显示"缺少会话 ID"。
- **根因**：会话标题=需求文本前 100 字 ≠ 需求名称，按名称匹配不到 → 坏降级路径只带标题跳转。
- **改动**：`ChatView.handleViewSixDim` 改按需求文本前 100 字匹配；降级路径恢复为发起新六维分析。
- **验证**：Playwright e2e 通过（带 conversationId 跳转，正文正常渲染）。

## 08-08 测试用例工作台查看预评审六维报告按钮

- **改动**：`TestCaseEditor` 按钮区新增"查看预评审报告/查看六维分析报告"（清空按钮左侧），按需求文本前 100 字匹配上游会话只读回看。
- **验证**：Playwright e2e 通过。

## 08-10 被驳回用例恢复Agent34结果

- **改动**：`TestCaseEditor` 新增 `saveTcState/restoreTcState`（localStorage 持久化工作台态）。
- **补充 1**：无本地态时 `restoreFromBackend()` 从后端 Agent3/4 会话按标题前缀+需求名匹配兜底恢复。
- **补充 2**：Agent4 匹配改为关键词命中 + 跳过空会话，并增加坏缓存自愈（`stepApproved=false` 且 `generatedResult` 空 → 清除走后端）。
- **验证**：3 个 Playwright e2e 通过。

## 08-10 文件上传entry改为reactive响应式

- **问题**：上传记录用普通对象，Vue3 改 `status` 绕过响应式代理，UI 不刷新。
- **改动**：`useFileUpload.js` 上传记录 `entry` 改 `reactive()`。
- **验证**：diff 与临时副本一致，vite build 通过。

## 08-10 全局助手GlobalAssistant挂载

- **改动**：`App.vue` 挂载 `<GlobalAssistant />`（应用外壳全局可用，登录页除外）。
- **验证**：vite build 通过。

## 08-10 网关注册表新增ai-assistant

- **改动**：`registry.py` 注册 `ai-assistant`；`schemas/chat.py` agent_id 白名单新增。
- **⚠️ 注意**：Agent 平台（Finance_Agent）缺 agent5 后端路由（`ROUTE_MAP` 仅 4 个 agent），当前调用会 500，属部分整合。需重启 Gateway 生效。

## 08-10 全局助手悬浮球可拖拽

- **改动**：`GlobalAssistant.vue` 悬浮球 mousedown 拖拽（2px 阈值区分点击/拖拽），`translate` 定位 + `grabbing` 光标。
- **验证**：vite build 通过。

## 08-17 项目首次启动与环境修复

- **问题**：Pro-main 首次在本机启动。`psycopg-binary==3.2.9` 无 Python 3.14 wheel 导致依赖安装失败（本机仅装 Python 3.14）。
- **改动**：
  - `Finance_Agent/requirements.txt`：`psycopg[binary]` 3.2.9 → 3.2.13。
  - 创建 4 个 `.env`（Agent 的 DeepSeek Key 复用 Finance_AI_Team-main，模型 `deepseek-v4-pro`）。
  - 三个 Python 项目各建 `.venv`（清华镜像）；Vue 执行 `npm install`。
  - 复用本机原生 PG 17（未启动 compose postgres）；Agent 用 `python -m src.api.server` 启动。
- **验证**：五服务全部启动；E2E 跑通（注册/登录/SSE 聊天/消息落库/agent5 checkpoints 表生成）；测试账号 `startup_check_user` 留库。
- **详情**：见 `改动与问题记录_20260817.md`。

## 08-17 需求卡片状态按用户隔离修复

- **问题**：`card_status` / `tc_state_{pid}` / `tc_card_status` 按浏览器全局存储，不带 user_id，同一浏览器换账号后打勾、审批标记残留。
- **改动**：新增 `src/utils/userStorage.js`（key 追加 `__u_<user_id>`）；ChatView / DashboardView / TestCaseEditor 全部改走用户隔离 key；GlobalAssistant 的 `agent5_conv_id` 一并隔离 + watch 登录态切换重新加载。`theme` 保持全局。
- **验证**：`npm run build` 通过（6.50s）；dev server HMR 正常。
- **详情**：见根目录 `修改记录/需求卡片状态按用户隔离修复.md`。

## 08-17 GlobalAssistant 移除心情图系统

- **问题**：agent5 的 4 张心情图（welcome/creating/happy/sad.png）已被删除，GlobalAssistant.vue 仍 import → build 在 asset 阶段失败。
- **改动**：GlobalAssistant.vue 删除 4 个心情图 import 与 `moodImg` 表（悬浮球/头像统一用 智能体助手.png）；保留 `mood` + `moodText` 文字状态提示；4 张 png 随提交移除。
- **验证**：`npm run build` 通过；dev 页面 HTTP 200。
- **详情**：见根目录 `修改记录/GlobalAssistant移除心情图系统.md`。

## 08-17 需求追踪界面新增删除按钮

- **改动**：需求追踪表格最右侧新增「操作」列；点击删除按钮弹 `ElMessageBox.confirm` 确认框（确认/取消）；确认后删除该需求名下跨智能体的全部会话（调 Gateway DELETE + store 同步移除），失败不阻塞并提示。
- **验证**：`npm run build` 通过（5.38s）；HMR 正常；后端接口为已有契约无改动。
- **详情**：见根目录 `修改记录/需求追踪界面新增删除按钮.md`。

## 08-17 侧边栏需求追踪列表

- **改动**：store 新增 `requirementRows` computed（与需求追踪表格同分组口径、按时间倒序）；侧边栏「需求追踪」按钮下方新增需求按钮列表——名称前 10 字（超出加 `...`、不足空格补齐），点击打开该需求最近活跃会话（当前阶段所在 agent，待审批 → 待审批界面）；无真实会话回退追踪页。
- **补充修复**：点击出现"历史报告"——同路由切换会话未拉远端消息 + store 快照缺审批字段。已补 watch 加载 + `enrichLastMessage` 回填 + `latestConv` 路由；Playwright 实测两条路径均进入**待审批**界面。
- **验证**：`npm run build` 通过；Playwright（Edge 无头 + 真实 DeepSeek 流程）两条路径均显示「待审批」+ 驳回/通过并继续按钮，无页面错误。
- **详情**：见根目录 `修改记录/侧边栏需求追踪列表.md`。

## 08-17 知识库文档上传入口（前端）

- **改动**：新增 `KbUploadDropzone.vue`（合并拖拽框，同步等待入库、不展示分类）、`services/api/knowledge.js`（调 `POST /api/v1/knowledge/upload`）；DashboardView 两面板下方接入；新增接口文档。
- **验证**：`npm run build` 通过；Playwright 确认拖拽框渲染正常。
- **对接**：后端 Gateway 转调接口 + 知识库入库接口待后端/知识库组按 `知识库文档上传接口文档.md` 实现。
- **详情**：见根目录 `修改记录/知识库文档上传入口（前端）.md`。

## 08-20 知识图谱与知识库文档查看迁移（前端）

- **改动**：从参考目录 `Finance_AI_Vue(图）` 选择性迁移知识图谱页面、知识库文档列表、Markdown 正文、分块/实体子图；新增 `/knowledge-graph` 路由及侧边栏入口；`knowledge.js` 保留上传方法并追加 4 个 GET 查询方法；验收后按需将侧边栏「知识图谱」按钮上移至「需求追踪」上方。
- **依赖**：显式新增 `force-graph@1.51.4`，避免依赖未直接使用的 Vue 包装器传递依赖。
- **可靠性**：加入请求取消/序号防竞态、响应结构检查、tooltip 转义、子图独立错误态及窄屏上下布局。
- **验证**：`npm ls force-graph`、`npm run build` 通过（5.91s）；构建生成独立知识图谱懒加载 chunk。
- **测试**：新增 `scripts/verify-knowledge-graph-acceptance.mjs`，Playwright mock 验收 30/30 通过、页面异常 0（全图/选库/正文/子图/分块/实体/收起/错误态/鉴权重定向/XSS/无直连后端）；亮暗主题与 500px 窄屏检查通过；迁移对照确认上传入口保留、`listKbs()`（源中死代码）与 `debug_kg_page.cjs`（调试脚本）未迁移。
- **缺陷**：随附脚本 `verify-knowledge-graph-mock.mjs` 用 `getByText('业务知识库')` 定位画布节点失败（force-graph 渲染在 Canvas 上，已复现超时），改用 `setupState` 驱动的验收脚本替代。
- **对接**：4 个 `GET /api/v1/knowledge/*` 路由当前尚未在 Gateway 实现（`app/main.py` 无 knowledge 路由、`app/knowledge_gateway/` 无 FastAPI 路由）；真实端到端联调阻塞，接口契约见 `知识图谱与知识库文档查看接口文档.md`。
- **详情**：见 `改动与问题记录_20260820.md`。

## 08-20 知识库文档上传 V2 适配（前端）

- **背景**：后端入库升级为 V2——`POST /knowledge/upload` 改为异步（202 + task_id，`kb_code` 可选，不传则后台按块全自动分类），新增 `GET /knowledge/tasks/{taskId}` 轮询，结果改为块级多库 `{kb_distribution, total_chunks, blocks, kb_code?, doc_id?}`。
- **改动**：`knowledge.js` 的 `uploadToKnowledgeBase` 支持可选 `kbCode`，新增 `getKnowledgeTask` 与 `uploadDocumentAndWait`（轮询 + 进度 + 取消）；`KbUploadDropzone.vue` 新增「自动分类（推荐）/KB01~KB06」下拉，异步轮询并展示块级多库结果，失败展示后端错误可重试。
- **验证**：`npm run build` 通过；新增 `scripts/verify-upload-v2.mjs` mock 验收 13/13 通过；后端路由已注册（Gateway 8000 未启动，真实联调待启动后复测）。
- **文档**：`知识库文档上传接口文档.md` 升级 v2（含 tasks 轮询契约与 v1→v2 差异表）。
- **详情**：见 `改动与问题记录_20260820.md`。
