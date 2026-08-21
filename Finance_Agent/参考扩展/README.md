# 参考扩展 · 智能对话助手（agent5 前端 + Gateway）完整实现

> **定位**：本目录是**本地开发的扩展实现副本，供其他人参考**（展示 agent5 前端 UI 与 Gateway 接入的完整代码），**不是本项目本地运行时的依赖路径**。
> 主仓库保持基线（不含以下扩展）；需要在自己环境接入的人，按等同路径移植即可。

---

## 包含内容（等同路径）

| 参考路径 | 原项目对应路径 | 说明 |
|----------|---------------|------|
| `Finance_AI_Vue/src/components/GlobalAssistant.vue` | `Finance_AI_Vue/src/components/GlobalAssistant.vue` | 悬浮助手组件（Vue3 + SSE 流式 + **convId localStorage 持久化** + **集成 FlowVisualizer** + **transfer 两段确认跳转**（2026-08-20：metadata.transfer → 弹窗可编辑 → router.push 跳目标 agent）） |
| `Finance_AI_Vue/src/components/FlowVisualizer.vue` | `Finance_AI_Vue/src/components/FlowVisualizer.vue` | **业务流程可视化组件**（SSE progress 真实节点驱动，节点名对齐契约 §6.2） |
| `Finance_AI_Vue/src/assets/agent5/*.png` | `Finance_AI_Vue/src/assets/agent5/` | 4 张心情形象图（welcome/creating/happy/sad） |
| `Finance_AI_Vue/src/App.vue` | `Finance_AI_Vue/src/App.vue` | **扩展版**：已含 `import GlobalAssistant` + `<GlobalAssistant />` 挂载 |
| `Finance_AI_Vue/src/composables/useFileUpload.js` | `Finance_AI_Vue/src/composables/useFileUpload.js` | **扩展版**：允许类型含图片（`.png/.jpg/.jpeg/.gif/.bmp/.webp/.tiff`，OCR 场景用） |
| `Finance_AI_FASTAPI/app/agent_gateway/registry.py` | `Finance_AI_FASTAPI/app/agent_gateway/registry.py` | **扩展版**：agent 注册表含 `ai-assistant` |
| `Finance_AI_FASTAPI/app/schemas/chat.py` | `Finance_AI_FASTAPI/app/schemas/chat.py` | **扩展版**：`agent_id` 白名单含 `ai-assistant` |

---

## 给谁看、怎么看

- 面向**需要接入/移植 agent5 前端与 Gateway 扩展的开发者**：直接对照本目录文件与主仓库基线的差异，即可知道扩展点在哪、如何接入。
- 本目录不参与本项目本地启动流程，`npm run dev` / 启动脚本不会读取它。

## 如何在其他环境启用（移植参考）

> 以下为**移植说明**，供需要此扩展的人参考。

### 1. 后端（Agent + Gateway）

> Agent 平台（`Finance_Agent`）的 agent5 核心代码已在主仓库中，无需操作。
> Gateway 的两处扩展当前已在主仓库生效（`registry.py` / `chat.py` 含 `ai-assistant`）。

### 2. 前端（Vue）

主仓库 `App.vue` 为基线版本（不含悬浮助手）。移植时：

```bash
# ① 将本目录文件复制到原项目对应路径
cp Finance_AI_Vue/src/components/GlobalAssistant.vue  <你的项目>/Finance_AI_Vue/src/components/
cp Finance_AI_Vue/src/components/FlowVisualizer.vue   <你的项目>/Finance_AI_Vue/src/components/
cp Finance_AI_Vue/src/assets/agent5/*.png             <你的项目>/Finance_AI_Vue/src/assets/agent5/
cp Finance_AI_Vue/src/App.vue                        <你的项目>/Finance_AI_Vue/src/App.vue

# ② 确认依赖：前端组件依赖 SSE 流式渲染；Gateway 依赖 /api/v1/chat 已接入 agent5
```

> [警告] 移植后若再 `git pull` / `checkout`，`App.vue` 会被主仓库基线覆盖，需重新移植或保留本地补丁。

> ⚠️ **多轮记忆字段名（重要）**：会话 ID 以**网关归一化后的 `conversation_id`** 为准（不是 Agent 内部的 `thread_id`）。GlobalAssistant 已兼容两者并持久化到 localStorage（键 `agent5_conv_id`）——移植时**不要改回 `data.thread_id`**，否则刷新后多轮记忆接不上。

> ⚠️ **跳转调度（2026-08-20 新增）**：agent5 识别转交意图后两段确认——① agent5 对话确认（transfer_propose/confirm/cancel）→ ② 前端弹窗（内容可编辑）→ `router.push(/chat/<target>?q=<内容>&pid=custom_<ts>)` 跳目标 agent 页自动发起。后端 Agent 改动在 `Finance_Agent` 主仓库（handler/graph/state/server.py），前端仅本文件（GlobalAssistant.vue 的 metadata.transfer 处理）。**网关零改动**。

---

## 如何回退

- 前端：恢复基线 `App.vue`（删掉 2 处 GlobalAssistant 引用），或直接 `git checkout -- Finance_AI_Vue/src/App.vue`
- Gateway：如需移除 `ai-assistant`，从 `registry.py` 删掉对应 `AgentDefinition` 块、`chat.py` 白名单删掉 `"ai-assistant",` 即可

---

## 维护约定

- 本目录**始终与主仓库扩展实现同步更新**：改动扩展代码时，同步更新参考副本（保持"等同路径"结构）

## 更新记录

| 日期 | 更新 |
|------|------|
| 2026-08-10 | ① 新增 FlowVisualizer.vue（业务流程图，SSE 真实节点驱动）并集成进 GlobalAssistant；② **修复会话 ID 字段**：读 `conversation_id`（非 `thread_id`，网关归一化坑）；③ convId localStorage 持久化（刷新不丢记忆） |
- 参考副本是**给需要的人看的完整实现**，主仓库默认不启用
