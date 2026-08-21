<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'
import { submitForReview, generateSteps } from '@/services/api/testcases'
import { renderMarkdown } from '@/composables/useMarkdown'
import { readScopedMap, writeScopedMap, scopedPidKey } from '@/utils/userStorage'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const agentStore = useAgentStore()
agentStore.loadAgents()

const form = ref({ requirementName:'', title:'', module:'', preconditions:'', testObjective:'', testData:'', expected:'' })
const modules = ['订单管理','权限校验','账户管理','风控模块','批量委托','清算结算','监管报送']
const submitting = ref(false)
const mode = ref('')
const error = ref('')
const reviewResult = ref('')
const reviewPassed = ref(null)
const generatedResult = ref('')
const stepApproved = ref(null)
const reviewProgress = ref({ node:'', status:'' })
const generationProgress = ref({ node:'', status:'' })
let reviewAttempt = 0

const reviewStages = [
  { nodes:['keyword','keyword_parse'], label:'理解用例', detail:'提取测试与业务关键词' },
  { nodes:['retrieval','retrieval_merge'], label:'三维检索', detail:'规范、需求和历史案例' },
  { nodes:['review_generate'], label:'清单评审', detail:'执行 18 项检查清单' },
  { nodes:['score'], label:'评审结论', detail:'汇总覆盖率与改进意见' }
]
const generationStages = [
  { nodes:['extract_keyword_node'], label:'提取关键词', detail:'识别功能与测试范围' },
  { nodes:['kb_route_node','knowledge_retrieve_node'], label:'检索知识', detail:'召回相关测试实践' },
  { nodes:['llm_gen_json_node','json_to_python_node'], label:'生成步骤', detail:'生成并校验结构化步骤' },
  { nodes:['gen_markdown_node'], label:'输出文档', detail:'整理最终测试步骤' }
]

const workflowStage = computed(() => {
  if (generatedResult.value) return 3
  if (mode.value === 'generate' || reviewPassed.value === true) return 2
  if (mode.value === 'review' || reviewResult.value) return 1
  return 0
})

onMounted(async () => {
  try { await agentStore.syncRemoteConversations('requirement-pre-review') } catch {}
  if (route.query.title) form.value.requirementName = route.query.title
  if (route.query.caseName) form.value.title = route.query.caseName
  if (route.query.requirement) form.value.testObjective = route.query.requirement
  if (route.query.q) form.value.testObjective = route.query.q
  await restoreTcState()
})

function clearForm() {
  reviewAttempt += 1
  form.value = { requirementName:'', title:'', module:'', preconditions:'', testObjective:'', testData:'', expected:'' }
  reviewResult.value = ''; generatedResult.value = ''; error.value = ''; mode.value = ''
  reviewPassed.value = null; stepApproved.value = null
  reviewProgress.value = { node:'', status:'' }; generationProgress.value = { node:'', status:'' }
  clearTcState()
}

function resetReviewFlow() {
  reviewAttempt += 1
  submitting.value = false
  mode.value = ''
  error.value = ''
  reviewResult.value = ''
  reviewPassed.value = null
  reviewProgress.value = { node:'', status:'' }
}

// 测试用例流程专用状态标记，与预评审 card_status 隔离（card_status 表示预审批结果，
// 此处表示 Agent3 用例评审 → Agent4 步骤生成 → 人工确认 的完成度）。
function setCardStatus(status) {
  if (!route.query.pid) return
  // 按用户隔离存储（换账号不残留）
  const values = readScopedMap('tc_card_status')
  values[route.query.pid] = status
  writeScopedMap('tc_card_status', values)
}

// —— 工作台进度持久化：Agent3/Agent4 结果与人工确认状态按 pid 存到 localStorage，
//    使"被驳回步骤生成"的用例再次进入（goTc）时能恢复已生成的结果与驳回态。 ——
function saveTcState() {
  if (!route.query.pid) return
  // 按用户隔离存储（换账号不残留）
  localStorage.setItem(scopedPidKey('tc_state', route.query.pid), JSON.stringify({
    form: { ...form.value },
    reviewResult: reviewResult.value,
    generatedResult: generatedResult.value,
    stepApproved: stepApproved.value,
    reviewPassed: reviewPassed.value,
    mode: mode.value
  }))
}

function clearTcState() {
  if (!route.query.pid) return
  localStorage.removeItem(scopedPidKey('tc_state', route.query.pid))
}

async function restoreTcState() {
  if (!route.query.pid) return
  // 已完成（approved）用例在 Dashboard 走 openPreReview，不会进入本工作台
  const cardStatus = readScopedMap('tc_card_status')[route.query.pid]
  // 全新 PID（未跑过任何流程）→ 不恢复，保持空白工作台
  if (cardStatus === undefined) return
  // 1) 快路径：本地保存的完整工作台状态（含表单与人工确认态）
  let saved = null
  try { saved = JSON.parse(localStorage.getItem(scopedPidKey('tc_state', route.query.pid)) || 'null') } catch { saved = null }
  if (saved && (saved.generatedResult || saved.reviewResult)) {
    // 非法状态防护：被驳回但无生成结果 → 坏缓存，清除后走后端兜底恢复
    if (saved.stepApproved === false && !saved.generatedResult) {
      clearTcState()
    } else {
      form.value = { ...form.value, ...saved.form }
      reviewResult.value = saved.reviewResult || ''
      generatedResult.value = saved.generatedResult || ''
      stepApproved.value = saved.stepApproved ?? null
      reviewPassed.value = saved.reviewPassed ?? null
      mode.value = saved.mode || ''
      error.value = ''
      await maybeAutoContinueAgent4()
      return
    }
  }
  // 2) 兜底：从后端 Agent3/Agent4 会话恢复（覆盖保存功能上线前就已驳回的用例）
  await restoreFromBackend(cardStatus)
  await maybeAutoContinueAgent4()
}

// 已完成 Agent3 评审但 Agent4 步骤尚未生成 → 进入工作台自动继续 Agent4
async function maybeAutoContinueAgent4() {
  if (reviewResult.value && !generatedResult.value && stepApproved.value !== true && reviewPassed.value !== false) {
    await doGenerate(reviewResult.value)
  }
}

// 按 Agent3/Agent4 工作流会话标题匹配：标题以固定提示词开头，且命中任一关键词（需求名/用例名），
// 返回按更新时间倒序的候选列表（不含消息加载）
async function findWorkflowConversation(agentId, promptPrefix, keywords) {
  await agentStore.syncRemoteConversations(agentId)
  const sessions = agentStore.conversations[agentId]?.sessions || {}
  const keys = (keywords || []).filter(Boolean).map(k => k.trim())
  return Object.values(sessions)
    .filter(s => {
      const st = (s.title || '').trim()
      if (!st.startsWith(promptPrefix)) return false
      if (!keys.length) return true
      return keys.some(k => st.includes(k))
    })
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
}

// 依次加载候选会话消息，返回第一条含 assistant 正文的内容（跳过空会话/失败会话）
async function loadAssistantContent(agentId, candidates) {
  for (const conv of candidates) {
    try {
      if (!conv.messagesLoaded) await agentStore.loadRemoteMessages(agentId, conv.conversationId)
      const assistant = (conv.messages || []).find(m => m.role === 'assistant' && m.content)
      if (assistant) return assistant.content
    } catch { /* 继续下一个候选 */ }
  }
  return ''
}

// 从评审输入文本补全表单（仅填空字段，route.query 已提供的值优先）
function applyParsedForm(text) {
  const map = {
    '对应需求': 'requirementName', '用例名称': 'title', '所属模块': 'module',
    '前置条件': 'preconditions', '测试场景/测试点': 'testObjective',
    '测试数据与输入条件': 'testData', '预期结果': 'expected'
  }
  for (const [label, key] of Object.entries(map)) {
    const m = text.match(new RegExp(`${label}[:：]\\s*([^\\n]+)`))
    if (m && m[1].trim() && !(form.value[key] || '').trim()) form.value[key] = m[1].trim()
  }
}

async function restoreFromBackend(cardStatus) {
  const requirementName = (form.value.requirementName || '').trim()
  if (!requirementName) return
  let review = '', steps = '', caseName = ''
  // Agent3 用例评审（accounting-expert）
  try {
    const candidates = await findWorkflowConversation('accounting-expert', '请评审以下结构化测试用例', [requirementName, requirementName.slice(0, 20)])
    const conv = candidates[0]
    if (conv) {
      review = await loadAssistantContent('accounting-expert', candidates)
      // 从评审会话标题提取用例名称，用于精确匹配 Agent4
      const m = (conv.title || '').match(/用例名称[:：]\s*([^\n]+)/)
      if (m) caseName = m[1].trim()
      const userMsg = (conv.messages || []).find(m => m.role === 'user' && m.content)
      if (userMsg) applyParsedForm(userMsg.content)
    }
  } catch { /* 网关不可用时跳过 Agent3 恢复 */ }
  // Agent4 步骤生成（business-analyst）：优先按用例名称匹配，其次按需求名前缀
  try {
    const stepKeys = [caseName, requirementName.slice(0, 20)].filter(Boolean)
    const candidates = await findWorkflowConversation('business-analyst', '请根据以下已评审用例生成可执行测试步骤', stepKeys)
    if (candidates.length) steps = await loadAssistantContent('business-analyst', candidates)
  } catch { /* 网关不可用时跳过 Agent4 恢复 */ }
  if (!review && !steps) return
  reviewResult.value = review
  if (steps) { generatedResult.value = steps; mode.value = 'generate' }
  else if (review) mode.value = 'review'
  reviewPassed.value = true
  error.value = ''
  stepApproved.value = cardStatus === 'rejected' ? false : null
  saveTcState()
}

function detectReviewPassed(text) {
  if (!text) return false
  if ([/不通过/,/不予通过/,/未通过评审/,/不合格/].some(pattern => pattern.test(text))) return false
  return [/通过/,/合格/,/建议通过/].some(pattern => pattern.test(text))
}

function stageState(stages, node, index, done) {
  if (done) return 'done'
  const active = stages.findIndex(stage => stage.nodes.includes(node))
  if (active < 0) return index === 0 ? 'active' : 'waiting'
  return index < active ? 'done' : index === active ? 'active' : 'waiting'
}

async function doGenerate(requirement) {
  mode.value = 'generate'; generatedResult.value = ''; stepApproved.value = null
  generationProgress.value = { node:'extract_keyword_node', status:'正在启动步骤生成智能体...' }
  submitting.value = true
  try {
    let full = ''
    await generateSteps({
      ...form.value,
      reviewReport: requirement
    }, ({ event, data }) => {
      if (event === 'progress') generationProgress.value = { node:data.node || '', status:data.message || '正在生成...' }
      else if (event === 'delta') full += data.text || ''
      else if (event === 'completed') full = data.answer || full
      else if (event === 'error') throw new Error(data.message || '步骤生成请求失败')
    })
    generatedResult.value = full
    saveTcState()
  } catch (e) {
    error.value = e.message
  } finally { submitting.value = false }
}

async function handleReview() {
  if (!form.value.title.trim()) { error.value = '请至少填写测试用例名称'; return }
  const attempt = ++reviewAttempt
  error.value = ''; mode.value = 'review'; reviewResult.value = ''; reviewPassed.value = null
  generatedResult.value = ''; stepApproved.value = null
  reviewProgress.value = { node:'keyword', status:'正在启动测试用例评审智能体...' }
  submitting.value = true
  let full = ''
  let metadataPass = null
  try {
    await submitForReview(form.value, ({ event, data }) => {
      if (attempt !== reviewAttempt) return
      if (event === 'progress') reviewProgress.value = { node:data.node || '', status:data.message || '正在评审...' }
      else if (event === 'delta') full += data.text || ''
      else if (event === 'completed') {
        full = data.answer || full
        if (typeof data.metadata?.pass_flag === 'boolean') metadataPass = data.metadata.pass_flag
      } else if (event === 'error') throw new Error(data.message || '评审请求失败')
    })
    if (attempt !== reviewAttempt) return
    reviewResult.value = full
    saveTcState()
    const actualPassed = metadataPass ?? detectReviewPassed(full)
    reviewPassed.value = actualPassed
    if (actualPassed) {
      setCardStatus('review_passed')
      await doGenerate(full)
    }
  } catch (e) {
    if (attempt !== reviewAttempt) return
    const message = e?.name === 'AbortError'
      ? '评审请求连接 Gateway 超时，请确认登录状态和服务连接后重试。'
      : e.message
    error.value = message; reviewResult.value = message; reviewPassed.value = false
  } finally {
    if (attempt === reviewAttempt) submitting.value = false
  }
}

function handleStepApprove() { stepApproved.value = true; setCardStatus('approved'); clearTcState() }
function handleStepReject() { stepApproved.value = false; setCardStatus('rejected'); saveTcState() }
function handleRegenerate() { error.value = ''; doGenerate(reviewResult.value) }

// 人工通过：评审结论为不通过时，允许人工判断后手动进入步骤生成
function handleManualPass() {
  reviewPassed.value = true
  setCardStatus('review_passed')
  doGenerate(reviewResult.value)
}

// 按"需求文本前 100 字"匹配已有会话（会话标题由后端按 payload.query[:100] 生成，
// 与 Dashboard openPreReview / ChatView handleViewSixDim 的匹配方式一致）。
async function findReportConversation(agentId) {
  const title = (form.value.requirementName || '').trim()
  const contentKey = (form.value.testObjective || title).slice(0, 100)
  if (!contentKey && !title) return null
  await agentStore.syncRemoteConversations(agentId)
  const sessions = agentStore.conversations[agentId]?.sessions || {}
  return Object.values(sessions).find(s => {
    const st = (s.title || '').trim()
    return (contentKey && st === contentKey) || st === title
  }) || null
}

// 查看预评审报告：打开该需求的预评审工作台（只读已生成的报告，不重新跑 Agent1）
async function viewPreReviewReport() {
  const title = (form.value.requirementName || '').trim()
  try {
    const existing = await findReportConversation('requirement-pre-review')
    if (existing) {
      agentStore.setActiveAgent('requirement-pre-review', existing.conversationId)
      await agentStore.loadRemoteMessages('requirement-pre-review', existing.conversationId)
      router.push({ path: '/chat/requirement-pre-review', query: { conversationId: existing.conversationId, title } })
      return
    }
  } catch { /* 网关不可用时走未找到提示 */ }
  ElMessage.warning('未找到该需求的预评审报告，请先在需求流程中完成预评审')
}

// 查看六维分析报告：跳转独立六维报告查看页（只读已生成的报告，不重新跑 Agent2）
async function viewSixDimReport() {
  const title = (form.value.requirementName || '').trim()
  try {
    const existing = await findReportConversation('ai-test-analysis')
    if (existing) {
      router.push({ path: '/six-dim-report', query: { conversationId: existing.conversationId, title } })
      return
    }
  } catch { /* 网关不可用时走未找到提示 */ }
  ElMessage.warning('未找到该需求的六维分析报告，请先完成六维分析')
}
</script>

<template>
  <div class="case-workbench"><div class="page-scroll"><main class="page-content">
    <header class="hero">
      <div><button class="back" @click="router.push('/')"><el-icon><ArrowLeft /></el-icon>返回首页</button><span class="eyebrow">TEST CASE WORKFLOW</span><h1>结构化测试用例工作台</h1><p>编写用例后，由评审智能体执行质量检查；通过后自动交给步骤生成智能体。</p></div>
      <div class="agent-chain"><span>Agent 3</span><b>用例评审</b><el-icon><Right /></el-icon><span>Agent 4</span><b>步骤生成</b></div>
    </header>

    <section class="workflow-overview">
      <div v-for="(item,index) in ['编写用例','智能评审','步骤生成','人工确认']" :key="item" class="flow-step" :class="{ active:workflowStage===index, done:workflowStage>index }"><div class="flow-index"><el-icon v-if="workflowStage>index"><Check /></el-icon><span v-else>{{ index+1 }}</span></div><strong>{{ item }}</strong></div>
    </section>

    <section class="form-card">
      <div class="section-title"><div class="title-icon"><el-icon><EditPen /></el-icon></div><div><span>STEP 01</span><h2>编写结构化测试用例</h2></div><el-tag type="info" effect="plain" round>必填：用例名称</el-tag></div>
      <div class="form-grid">
        <label><span>关联需求</span><el-select v-model="form.requirementName" placeholder="选择已有需求" filterable clearable><el-option v-for="name in agentStore.requirementNames" :key="name" :label="name" :value="name" /></el-select></label>
        <label><span>用例名称 <b>*</b></span><el-input v-model="form.title" placeholder="例如：交易密码重置成功流程" /></label>
        <label><span>所属模块</span><el-select v-model="form.module" placeholder="选择模块" clearable><el-option v-for="item in modules" :key="item" :label="item" :value="item" /></el-select></label>
        <label class="wide"><span>前置条件</span><el-input v-model="form.preconditions" type="textarea" :rows="3" placeholder="描述账号状态、权限、数据准备等前置条件" /></label>
        <label class="wide"><span>测试场景 / 测试点</span><el-input v-model="form.testObjective" type="textarea" :rows="4" placeholder="描述要验证的业务场景、规则、异常或边界，不需要编写操作步骤" /></label>
        <label class="wide"><span>测试数据与输入条件</span><el-input v-model="form.testData" type="textarea" :rows="3" placeholder="例如：客户状态、账号权限、输入值、边界值或数据组合" /></label>
        <label class="wide"><span>预期结果</span><el-input v-model="form.expected" type="textarea" :rows="3" placeholder="描述系统应产生的页面、数据和状态变化" /></label>
      </div>
      <div v-if="error" class="error-banner"><el-icon><WarningFilled /></el-icon>{{ error }}</div>
      <footer class="form-actions">
        <el-button plain :disabled="submitting" @click="viewPreReviewReport"><el-icon><Memo /></el-icon>查看预评审报告</el-button>
        <el-button plain :disabled="submitting" @click="viewSixDimReport"><el-icon><DataAnalysis /></el-icon>查看六维分析报告</el-button>
        <el-button plain :disabled="submitting" @click="clearForm">清空内容</el-button>
        <el-button v-if="submitting && mode==='review'" plain type="warning" @click="resetReviewFlow">重置当前流程</el-button>
        <el-button type="primary" :disabled="stepApproved===true" @click="handleReview"><el-icon><Promotion /></el-icon>{{ submitting && mode==='review' ? '重新提交评审' : '提交智能评审' }}</el-button>
      </footer>
    </section>

    <section v-if="mode==='review' || reviewResult" class="agent-stage review-stage">
      <div class="stage-heading"><div><span class="eyebrow">AGENT 3 · CASE REVIEW</span><h2>测试用例评审</h2></div><el-tag v-if="reviewPassed===true" type="success" round>评审通过</el-tag><el-tag v-else-if="reviewPassed===false" type="danger" round>评审未通过</el-tag><el-tag v-else type="warning" round>评审中</el-tag></div>
      <div class="stage-progress"><div v-for="(stage,index) in reviewStages" :key="stage.label" class="mini-stage" :class="`is-${stageState(reviewStages,reviewProgress.node,index,Boolean(reviewResult))}`"><div class="marker"><el-icon v-if="stageState(reviewStages,reviewProgress.node,index,Boolean(reviewResult))==='done'"><Check /></el-icon><span v-else>{{ index+1 }}</span></div><div><strong>{{ stage.label }}</strong><small>{{ stage.detail }}</small></div></div></div>
      <el-progress :percentage="reviewResult ? 100 : Math.max(8,(reviewStages.findIndex(s=>s.nodes.includes(reviewProgress.node))+1)*25)" :status="reviewResult ? 'success' : undefined" />
      <p v-if="submitting && mode==='review'" class="live-status"><span></span>{{ reviewProgress.status }}</p>
      <details v-if="reviewResult" class="report-details" :open="reviewPassed===false"><summary>查看完整评审报告</summary><article class="markdown-body" v-html="renderMarkdown(reviewResult)"></article></details>
      <div v-if="reviewPassed===false" class="manual-pass"><p><el-icon><WarningFilled /></el-icon>Agent 3 评审结论为"不通过"。您可以修改用例后重新提交评审，或人工判断后手动进入步骤生成。</p><el-button type="warning" :disabled="submitting" @click="handleManualPass"><el-icon><Check /></el-icon>人工通过并继续</el-button></div>
    </section>

    <section v-if="mode==='generate' || generatedResult" class="agent-stage generation-stage">
      <div class="stage-heading"><div><span class="eyebrow">AGENT 4 · STEP GENERATION</span><h2>测试步骤生成</h2></div><el-tag v-if="generatedResult" type="success" round>生成完成</el-tag><el-tag v-else type="warning" round>生成中</el-tag></div>
      <div class="stage-progress"><div v-for="(stage,index) in generationStages" :key="stage.label" class="mini-stage" :class="`is-${stageState(generationStages,generationProgress.node,index,Boolean(generatedResult))}`"><div class="marker"><el-icon v-if="stageState(generationStages,generationProgress.node,index,Boolean(generatedResult))==='done'"><Check /></el-icon><span v-else>{{ index+1 }}</span></div><div><strong>{{ stage.label }}</strong><small>{{ stage.detail }}</small></div></div></div>
      <el-progress :percentage="generatedResult ? 100 : Math.max(8,(generationStages.findIndex(s=>s.nodes.includes(generationProgress.node))+1)*25)" :status="generatedResult ? 'success' : undefined" />
      <p v-if="submitting && mode==='generate'" class="live-status purple"><span></span>{{ generationProgress.status }}</p>
      <article v-if="generatedResult" class="generated-report markdown-body" v-html="renderMarkdown(generatedResult)"></article>
      <div v-if="generatedResult && stepApproved===null" class="decision"><div><strong>人工确认生成结果</strong><p>请检查步骤的完整性、顺序和预期结果，确认后完成流程。</p></div><div><el-button type="danger" plain @click="handleStepReject">驳回</el-button><el-button type="success" @click="handleStepApprove"><el-icon><Check /></el-icon>确认通过</el-button></div></div>
      <div v-else-if="stepApproved===false" class="decision rejected"><strong>步骤已驳回</strong><el-button type="primary" @click="handleRegenerate">重新生成</el-button></div>
      <div v-else-if="stepApproved===true" class="decision approved"><div><strong><el-icon><CircleCheckFilled /></el-icon>测试用例流程已完成</strong><p>生成步骤已通过人工确认。</p></div><el-button @click="router.push('/')">返回首页</el-button></div>
    </section>
  </main></div></div>
</template>

<style scoped>
.case-workbench{height:100vh;overflow:hidden;background:radial-gradient(circle at 8% 0,rgba(15,108,189,.08),transparent 27%),var(--el-bg-color-page)}.page-scroll{height:100%;overflow-y:auto}.page-content{display:flex;flex-direction:column;gap:20px;width:min(1120px,calc(100% - 48px));margin:0 auto;padding:30px 0 64px}.hero{display:flex;align-items:flex-end;justify-content:space-between;gap:30px}.back{display:flex;align-items:center;gap:5px;margin:0 0 24px;padding:0;color:var(--el-text-color-secondary);border:0;background:none;cursor:pointer}.eyebrow,.section-title span{display:block;margin-bottom:5px;color:var(--el-color-primary);font-size:10px;font-weight:800;letter-spacing:.14em}.hero h1{margin:0;color:var(--el-text-color-primary);font-size:28px}.hero p{margin:8px 0 0;color:var(--el-text-color-secondary);font-size:13px}.agent-chain{display:flex;align-items:center;gap:9px;padding:13px 16px;border:1px solid var(--el-border-color-lighter);border-radius:14px;background:var(--el-bg-color);font-size:11px}.agent-chain span{padding:5px 8px;color:var(--el-color-primary);border-radius:7px;background:var(--el-color-primary-light-9);font-weight:800}.agent-chain b{font-size:12px}.workflow-overview{display:grid;grid-template-columns:repeat(4,1fr);padding:15px 18px;border:1px solid var(--el-border-color-lighter);border-radius:16px;background:var(--el-bg-color)}.flow-step{position:relative;display:flex;align-items:center;gap:10px;color:var(--el-text-color-placeholder);font-size:12px}.flow-step:not(:last-child):after{position:absolute;right:16px;width:35%;height:1px;background:var(--el-border-color);content:''}.flow-index{display:grid;width:27px;height:27px;border:1px solid var(--el-border-color);border-radius:50%;place-items:center}.flow-step.active{color:var(--el-color-primary)}.flow-step.active .flow-index{color:#fff;border-color:var(--el-color-primary);background:var(--el-color-primary)}.flow-step.done{color:var(--el-color-success)}.flow-step.done .flow-index{color:#fff;border-color:var(--el-color-success);background:var(--el-color-success)}.form-card,.agent-stage{padding:26px;border:1px solid var(--el-border-color-lighter);border-radius:18px;background:var(--el-bg-color);box-shadow:0 10px 30px rgba(15,23,42,.05)}.section-title,.stage-heading{display:flex;align-items:center;gap:13px;margin-bottom:23px}.section-title>div:nth-child(2),.stage-heading>div{flex:1}.section-title h2,.stage-heading h2{margin:0;color:var(--el-text-color-primary);font-size:19px}.title-icon{display:grid;width:42px;height:42px;color:#fff;border-radius:12px;background:linear-gradient(135deg,var(--el-color-primary),#4b95d3);place-items:center}.form-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}.form-grid label{display:flex;flex-direction:column;gap:8px}.form-grid label>span{color:var(--el-text-color-regular);font-size:12px;font-weight:650}.form-grid label b{color:var(--el-color-danger)}.form-grid .wide{grid-column:1/-1}.form-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:22px;padding-top:18px;border-top:1px solid var(--el-border-color-extra-light)}.error-banner,.test-mode{display:flex;align-items:center;gap:8px;margin-top:16px;padding:11px 14px;color:var(--el-color-danger);border-radius:10px;background:var(--el-color-danger-light-9);font-size:12px}.stage-progress{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px}.mini-stage{display:flex;gap:10px;padding:12px;border:1px solid var(--el-border-color-extra-light);border-radius:12px;background:var(--el-fill-color-extra-light)}.marker{display:grid;width:27px;height:27px;flex:none;color:var(--el-text-color-placeholder);border:1px solid var(--el-border-color);border-radius:8px;background:var(--el-bg-color);font-size:11px;place-items:center}.mini-stage strong,.mini-stage small{display:block}.mini-stage strong{font-size:12px}.mini-stage small{margin-top:3px;color:var(--el-text-color-placeholder);font-size:9px;line-height:1.4}.mini-stage.is-active{border-color:var(--el-color-primary-light-5);background:var(--el-color-primary-light-9)}.mini-stage.is-active .marker{color:#fff;border-color:var(--el-color-primary);background:var(--el-color-primary)}.mini-stage.is-done .marker{color:#fff;border-color:var(--el-color-success);background:var(--el-color-success)}.live-status{display:flex;align-items:center;gap:8px;margin:14px 0 0;color:var(--el-color-primary);font-size:12px}.live-status span{width:8px;height:8px;border-radius:50%;background:currentColor;animation:pulse 1.2s infinite}.report-details{margin-top:18px;border-top:1px solid var(--el-border-color-extra-light);padding-top:16px}.report-details summary{color:var(--el-color-primary);font-size:13px;font-weight:650;cursor:pointer}.report-details article{max-height:440px;margin-top:15px;padding:20px;overflow-y:auto;border-radius:12px;background:var(--el-fill-color-extra-light);font-size:13px;line-height:1.7}.test-mode{color:var(--el-color-warning);background:var(--el-color-warning-light-9)}.generation-stage .eyebrow{color:#7257d9}.generated-report{max-height:620px;margin-top:20px;padding:25px;overflow-y:auto;border:1px solid var(--el-border-color-extra-light);border-radius:14px;background:var(--el-fill-color-extra-light);font-size:14px;line-height:1.75}.decision{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-top:18px;padding:16px 18px;border:1px solid var(--el-color-primary-light-7);border-radius:13px;background:var(--el-color-primary-light-9)}.decision p{margin:4px 0 0;color:var(--el-text-color-secondary);font-size:12px}.decision.approved{border-color:var(--el-color-success-light-5);background:var(--el-color-success-light-9)}.decision.approved strong{display:flex;align-items:center;gap:7px;color:var(--el-color-success)}.decision.rejected{border-color:var(--el-color-danger-light-5);background:var(--el-color-danger-light-9)}.manual-pass{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:18px;padding:14px 18px;border:1px solid var(--el-color-warning-light-5);border-radius:13px;background:var(--el-color-warning-light-9)}.manual-pass p{display:flex;align-items:center;gap:8px;margin:0;color:var(--el-color-warning);font-size:12px;line-height:1.5}@keyframes pulse{50%{opacity:.25;transform:scale(.75)}}@media(max-width:760px){.page-content{width:calc(100% - 24px);padding-top:18px}.hero{align-items:flex-start;flex-direction:column}.agent-chain{width:100%;box-sizing:border-box}.workflow-overview,.stage-progress{grid-template-columns:repeat(2,1fr);gap:12px}.flow-step:after{display:none}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}.decision{align-items:flex-start;flex-direction:column}}
</style>
