<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'
import { readScopedMap } from '@/utils/userStorage'
import KbUploadDropzone from '@/components/KbUploadDropzone.vue'

const router = useRouter()
const agentStore = useAgentStore()
agentStore.loadAgents()

// ---------- 新建需求（自由输入需求文本 → 发起预评审） ----------
const showNewReqDialog = ref(false)
const newReqText = ref('')
const newReqTitle = ref('')
const newReqSubmitting = ref(false)

function openNewReqDialog() {
  newReqText.value = ''
  newReqTitle.value = ''
  showNewReqDialog.value = true
}

async function submitNewRequirement() {
  const text = newReqText.value.trim()
  if (!text) return
  newReqSubmitting.value = true
  try {
    // 需求文本前 100 字作为会话标题（与后端 chat.py title=payload.query[:100] 对齐），
    // 便于需求追踪/卡片匹配复用。q 参数 → ChatView 自动发起预评审。
    const title = newReqTitle.value.trim() || text.slice(0, 100)
    showNewReqDialog.value = false
    await router.push({
      path: '/chat/requirement-pre-review',
      query: { q: text, title, pid: `custom_${Date.now()}` }
    })
  } finally {
    newReqSubmitting.value = false
  }
}

// ---------- 需求流程面板（固定需求卡片） ----------
// 卡片状态从真实会话审批数据推导（DB 权威，localStorage 标记仅兜底），
// 避免从追踪表格 / 已有会话入口审批后 localStorage 未写入导致状态脱节。
const statuses = computed(() => {
  const map = readScopedMap('card_status')
  const sessions = agentStore.conversations[AGENT_PRE_REVIEW]?.sessions || {}
  for (const c of reqPanel.cards) {
    const matched = Object.values(sessions).filter(s => s.title === c.content.slice(0, 100))
    // 消息级聚合：遍历所有匹配会话，按 通过 > 驳回 > 待审批 优先级聚合
    // （与需求追踪表格 analyzeConversation 语义一致，且不被最新空会话顶掉）
    let hasApproved = false, hasRejected = false, hasPending = false
    for (const s of matched) {
      if (!s.messages?.length) continue
      const st = analyzeConversation(s)
      if (st.preReview === '通过') hasApproved = true
      else if (st.preReview === '未通过') hasRejected = true
      else if (st.preReview === '待审批') hasPending = true
    }
    if (hasApproved) map[c.id] = 'approved'
    else if (hasRejected) map[c.id] = 'rejected'
    else if (hasPending) map[c.id] = 'pending'
    // 兜底：会话级 reviewDecision（列表接口返回的最近一次审批）
    else {
      const decisions = matched.map(s => s.reviewDecision)
      if (decisions.includes('approve')) map[c.id] = 'approved'
      else if (decisions.some(d => d === 'reject' || d === 'revise')) map[c.id] = 'rejected'
      else if (decisions.some(d => d === 'pending')) map[c.id] = 'pending'
    }
  }
  return map
})
const reqPanel = {
  id:'req', title:'需求流程', icon:'Memo', desc:'预评审 → 审批 → 六维分析',
  cards:[
    { id:'r1', title:'客户密码重置功能', content:'客服后台支持授权客服人员直接重置客户交易密码。仅适用于已通过视频双录完成身份核验的场景。需关注合规风险与操作审计。' },
    { id:'r2', title:'资金对冲需求分析', content:'实现当日卖出股票资金可当日取现，提升资金使用效率。关注合规风险和系统变更控制，需评估对现有交易流程的影响。' },
    { id:'r3', title:'账户安全升级方案', content:'增加多因素认证机制，对高风险交易进行二次确认。需评估短信验证、生物识别等多种方案的可行性及成本。' },
    { id:'r4', title:'交易风控规则优化', content:'优化现有交易风控规则引擎，支持动态阈值调整。' },
    { id:'r5', title:'客户信息管理重构', content:'重构客户信息管理模块，支持多维度客户画像标签。' },
    { id:'r6', title:'投资者适当性管理', content:'完善投资者风险评级体系，根据客户资产、投资经验、风险偏好自动匹配产品推荐。' },
    { id:'r7', title:'清算结算流程优化', content:'优化T+1清算结算流程，支持实时对账与差异处理。' },
    { id:'r8', title:'监管报送自动化', content:'实现监管报表自动生成与报送，支持证监会、交易所等多维度数据上报。' },
    { id:'r9', title:'客户投诉处理流程', content:'建立客户投诉全流程跟踪系统，支持投诉录入、分发、处理、回访闭环管理。' },
    { id:'r10', title:'理财产品智能推荐', content:'基于客户风险偏好与持仓情况，实现理财产品智能推荐算法。' }
  ]
}
const go = async (p, c) => {
  // 已产生过评审记录的固定需求直接打开原会话，避免重复调用大模型。
  try {
    await agentStore.syncRemoteConversations(AGENT_PRE_REVIEW)
    const sessions = agentStore.conversations[AGENT_PRE_REVIEW]?.sessions || {}
    const existing = Object.values(sessions).find(session =>
      session.reviewDecision && session.title === c.content.slice(0, 100)
    )
    if (existing) {
      agentStore.setActiveAgent(AGENT_PRE_REVIEW, existing.conversationId)
      await agentStore.loadRemoteMessages(AGENT_PRE_REVIEW, existing.conversationId)
      router.push({
        path: `/chat/${AGENT_PRE_REVIEW}`,
        query: { conversationId: existing.conversationId, pid: c.id, title: c.title }
      })
      return
    }
  } catch { /* 网关不可用时仍允许发起新评审 */ }
  router.push({ path: '/chat/requirement-pre-review', query: { q: c.content, pid: c.id, title: c.title } })
}

const AGENT_PRE_REVIEW = 'requirement-pre-review'
const AGENT_TEST_ANALYSIS = 'ai-test-analysis'

function analyzeConversation(session) {
  if (!session) return { preReview: '未开始', sixDim: '--', caseReview: '未开始', caseSteps: 0 }
  const msgs = session.messages || []
  const hasApproved = msgs.some(m => m.approved === true)
  const hasRejected = msgs.some(m => m.approved === false)
  const hasNeedApproval = msgs.some(m => m.needApproval === true)
  if (hasApproved) {
    const assistantMsgs = msgs.filter(m => m.role === 'assistant' && m.content)
    const steps = assistantMsgs.reduce((sum, m) => sum + (m.content || '').split('\n').filter(l => /^\d+[\.\、\)]/.test(l.trim())).length, 0)
    return { preReview: '通过', sixDim: '已生成', caseReview: '通过', caseSteps: steps || '已生成' }
  }
  if (hasRejected) return { preReview: '未通过', sixDim: '--', caseReview: '未通过', caseSteps: 0 }
  if (hasNeedApproval) return { preReview: '待审批', sixDim: '--', caseReview: '待审批', caseSteps: 0 }
  if (msgs.length > 1) return { preReview: '进行中', sixDim: '--', caseReview: '进行中', caseSteps: 0 }
  return { preReview: '未开始', sixDim: '--', caseReview: '未开始', caseSteps: 0 }
}

// 动态需求分组（tc 面板需要：把已通过 预审批+六维分析 的需求做成动态卡片）。
// 与需求追踪页 RequirementTracking.vue 的 requirementData 逻辑一致。
const requirementData = computed(() => {
  const allSessions = []
  for (const [agentId, data] of Object.entries(agentStore.conversations)) {
    if (!data?.sessions) continue
    for (const [convId, session] of Object.entries(data.sessions)) {
      if (convId.startsWith('local_') && session.title === '新对话' && (session.messages?.length || 0) <= 1) continue
      allSessions.push({
        agentId, conversationId: session.conversationId || convId,
        title: session.title || '', messages: session.messages || [],
        messagesLoaded: session.messagesLoaded || false, updatedAt: session.updatedAt || 0
      })
    }
  }
  const groupMap = {}
  for (const s of allSessions) {
    const key = s.title.trim() || '未知需求'
    if (!groupMap[key]) groupMap[key] = {}
    groupMap[key][s.agentId] = s
  }
  const rows = []
  let idx = 0
  for (const [title, agentConvs] of Object.entries(groupMap)) {
    idx++
    const p1 = analyzeConversation(agentConvs[AGENT_PRE_REVIEW])
    const p2 = analyzeConversation(agentConvs[AGENT_TEST_ANALYSIS])
    rows.push({
      id: `REQ-${String(idx).padStart(4, '0')}`, name: title,
      preReview: p1.preReview, preReviewConv: agentConvs[AGENT_PRE_REVIEW] || null,
      sixDim: p1.sixDim, sixDimConv: (p1.sixDim !== '--' && p1.sixDim !== '未开始') ? agentConvs[AGENT_PRE_REVIEW] : null,
      caseReview: p2.caseReview, caseReviewConv: agentConvs[AGENT_TEST_ANALYSIS] || null,
      caseSteps: p2.caseSteps, caseStepsConv: (p2.caseSteps > 0 || p2.caseSteps === '已生成') ? agentConvs[AGENT_TEST_ANALYSIS] : null
    })
  }
  rows.sort((a, b) => {
    const aMax = Math.max(a.preReviewConv?.updatedAt || 0, a.caseReviewConv?.updatedAt || 0)
    const bMax = Math.max(b.preReviewConv?.updatedAt || 0, b.caseReviewConv?.updatedAt || 0)
    return bMax - aMax
  })
  return rows
})

// ---------- 测试用例流程面板（已通过 预审批 + 六维分析 的需求） ----------
// 打勾标记（localStorage card_status）标识已通过预审批 + 六维分析的固定需求卡片
const approvedReqCards = computed(() =>
  reqPanel.cards.filter(c => statuses.value[c.id] === 'approved')
)

// 需求流程面板：仅保留尚未通过的固定需求卡片
const reqCards = computed(() =>
  reqPanel.cards.filter(c => statuses.value[c.id] !== 'approved')
)

// 测试用例流程面板：已通过的固定卡片 + 已通过的动态需求（按需求内容去重）
const tcCards = computed(() => {
  const fixed = approvedReqCards.value.map(c => ({
    id: c.id, title: c.title, content: c.content, pid: c.id, sixDimConv: null
  }))
  const fixedKeys = new Set(fixed.map(c =>
    c.content.length > 30 ? c.content.slice(0, 30) + '...' : c.content
  ))
  const dynamic = requirementData.value
    .filter(row => row.preReview === '通过' && row.sixDim === '已生成' && !fixedKeys.has(row.name))
    .map(row => ({
      id: row.id, title: row.name, pid: row.id, sixDimConv: row.sixDimConv || null
    }))
  return [...fixed, ...dynamic]
})

// 测试用例流程面板（已通过 预审批 + 六维分析 的需求）卡片状态：
// 进入 tc 面板默认 ⏳（待进行），跑完 Agent3 用例评审 → Agent4 步骤生成 → 人工确认
// 后由 TestCaseEditor 写入 localStorage.tc_card_status[pid]='approved' → ✅；
// 驳回步骤则 → ❌。与预评审 card_status 隔离，避免"已通过预审批"与"用例流程完成"混淆。
const tcStatuses = computed(() => {
  const map = readScopedMap('tc_card_status')
  const out = {}
  for (const c of tcCards.value) {
    const s = map[c.pid || c.id]
    if (s === 'approved') out[c.id] = 'approved'
    else if (s === 'rejected') out[c.id] = 'rejected'
    else out[c.id] = 'pending'
  }
  return out
})

const panels = computed(() => [
  { ...reqPanel, cards: reqCards.value },
  {
    id: 'tc', title: '测试用例流程', icon: 'DocumentCopy', desc: '用例评审 → 审批 → 步骤生成',
    cards: tcCards.value
  }
])

// 卡片状态符号：req 面板用预审批状态 statuses；tc 面板用测试用例流程状态 tcStatuses
function cardStatus(p, c) {
  return p.id === 'tc' ? tcStatuses.value[c.id] : statuses.value[c.id]
}

const onCardClick = (p, c) => {
  if (p.id === 'tc') {
    // tc 面板中已跑完四个智能体（预评审→六维→用例评审→步骤生成，右侧 ✅）的用例：
    // 点击呈现该用例的需求预评审报告；未完成（⏳/❌）则继续进入测试用例编写流程。
    if (tcStatuses.value[c.id] === 'approved') openPreReview(c)
    else goTc(c)
  } else go(p, c)
}

const goTc = async (c) => {
  // 预审批 + 六维分析已通过，直接进入该需求的测试用例流程。
  let requirement = c.content || ''
  const conv = c.sixDimConv
  if (!requirement && conv) {
    try {
      if (!conv.messagesLoaded) {
        await agentStore.loadRemoteMessages(AGENT_TEST_ANALYSIS, conv.conversationId)
      }
      const userMsg = [...(conv.messages || [])].reverse().find(m => m.role === 'user')
      requirement = userMsg?.content || ''
    } catch { /* 消息加载失败时仅携带需求名称 */ }
  }
  router.push({
    path: '/test-case/write',
    query: { title: c.title, requirement, pid: c.id }
  })
}

const openPreReview = async (c) => {
  // 打开该用例的预评审会话，呈现需求预评审报告（Agent1 输出，已通过）。
  // 动态需求卡片已记录预评审会话；固定需求卡片按需求内容匹配（与 statuses 一致）。
  try {
    await agentStore.syncRemoteConversations(AGENT_PRE_REVIEW)
    const sessions = agentStore.conversations[AGENT_PRE_REVIEW]?.sessions || {}
    let existing = null
    if (c.sixDimConv?.conversationId && sessions[c.sixDimConv.conversationId]) {
      existing = sessions[c.sixDimConv.conversationId]
    } else {
      const matchContent = (c.content || c.title || '').slice(0, 100)
      existing = Object.values(sessions).find(s => s.title === matchContent) || null
    }
    if (existing) {
      agentStore.setActiveAgent(AGENT_PRE_REVIEW, existing.conversationId)
      await agentStore.loadRemoteMessages(AGENT_PRE_REVIEW, existing.conversationId)
      router.push({
        path: `/chat/${AGENT_PRE_REVIEW}`,
        query: { conversationId: existing.conversationId, pid: c.pid || c.id, title: c.title }
      })
      return
    }
  } catch { /* 网关不可用时回退到用例流程 */ }
  goTc(c)
}

// 预加载与固定需求卡片匹配的预评审会话消息，使卡片状态能读取真实审批结果
onMounted(async () => {
  try {
    await agentStore.syncRemoteConversations(AGENT_PRE_REVIEW)
    const sessions = agentStore.conversations[AGENT_PRE_REVIEW]?.sessions || {}
    const targets = new Set()
    for (const c of reqPanel.cards) {
      for (const s of Object.values(sessions)) {
        if (s.title === c.content.slice(0, 100)) targets.add(s.conversationId)
      }
    }
    await Promise.allSettled([...targets].map(id => agentStore.loadRemoteMessages(AGENT_PRE_REVIEW, id)))
  } catch { /* 网关不可用时卡片状态回退到 localStorage 标记 */ }
})
</script>

<template>
<div class="dashboard"><div class="dashboard-scroll"><div class="dashboard-content">
  <div class="welcome">
    <div class="welcome-head">
      <div>
        <h2>AI 需求助手</h2>
        <p>点击用例卡片自动启动分析流程</p>
      </div>
      <el-button type="primary" :icon="'Plus'" @click="openNewReqDialog">新建需求</el-button>
    </div>
  </div>
  <div class="usecase-grid">
    <div v-for="p in panels" :key="p.id" class="usecase-panel">
      <div class="panel-header"><div class="panel-icon"><el-icon :size="22"><component :is="p.icon"/></el-icon></div><div class="panel-title"><h3>{{p.title}}</h3><p>{{p.desc}}</p></div></div>
      <div class="panel-body">
        <template v-if="p.cards.length">
          <div class="usecase-label">{{ p.id === 'tc' ? '已通过需求' : '常用用例' }}</div>
          <div class="usecase-list">
            <button v-for="(c,i) in p.cards" :key="c.id" class="usecase-item" @click="onCardClick(p,c)">
              <span class="usecase-bullet">{{i+1}}</span><span class="usecase-text">{{c.title}}</span>
              <span v-if="cardStatus(p,c)==='approved'" class="usecase-status">✅</span><span v-else-if="cardStatus(p,c)==='rejected'" class="usecase-status">❌</span><span v-else-if="cardStatus(p,c)==='pending'" class="usecase-status">⏳</span>
              <el-icon v-else :size="14" class="usecase-arrow"><Right/></el-icon>
            </button>
          </div>
        </template>
        <div v-else class="panel-empty">
          <span>{{ p.id === 'tc' ? '暂无已通过预审批与六维分析的需求' : '暂无待评审需求' }}</span>
          <el-button v-if="p.id === 'tc'" size="small" type="primary" plain @click="router.push({ path: '/test-case/write' })">进入测试用例编写</el-button>
          <el-button v-else size="small" type="primary" plain @click="openNewReqDialog">新建需求</el-button>
        </div>
      </div>
    </div>
  </div>

  <!-- 知识库文档入库（合并大框，位于两个流程面板下方） -->
  <KbUploadDropzone />

  <!-- 新建需求弹窗 -->
  <el-dialog v-model="showNewReqDialog" title="新建需求" width="560px" :close-on-click-modal="false">
    <el-form label-position="top">
      <el-form-item label="需求名称（可选）">
        <el-input v-model="newReqTitle" placeholder="例如：用户登录认证增强" maxlength="100" show-word-limit />
      </el-form-item>
      <el-form-item label="需求描述" required>
        <el-input
          v-model="newReqText"
          type="textarea"
          :rows="8"
          placeholder="粘贴或输入需求描述，将自动发起需求预评审（agent1）并检索知识库……"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showNewReqDialog = false">取消</el-button>
      <el-button type="primary" :loading="newReqSubmitting" :disabled="!newReqText.trim()" @click="submitNewRequirement">
        发起预评审
      </el-button>
    </template>
  </el-dialog>

</div></div></div>
</template>

<style scoped>
.dashboard{height:100vh;overflow:hidden}
.dashboard-scroll{height:100%;overflow-y:auto}
.dashboard-content{max-width:1100px;margin:0 auto;padding:40px 40px 60px}
.welcome{margin-bottom:32px}
.welcome-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.welcome h2{font-size:28px;font-weight:750;color:var(--el-text-color-primary);letter-spacing:-.7px;margin:0}
.welcome p{color:var(--el-text-color-secondary);font-size:15px;margin:6px 0 0}
.usecase-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:40px}
.usecase-panel{border-radius:16px;background:var(--el-bg-color);border:1px solid var(--el-border-color-lighter);box-shadow:0 2px 12px rgba(15,23,42,.04);display:flex;flex-direction:column;overflow:hidden}
.panel-header{display:flex;align-items:flex-start;gap:16px;padding:24px 24px 0}
.panel-icon{display:grid;width:48px;height:48px;flex-shrink:0;color:#fff;border-radius:14px;background:linear-gradient(135deg,var(--el-color-primary),var(--el-color-primary-light-3));box-shadow:0 6px 16px rgba(15,108,189,.25);place-items:center}
.panel-title h3{font-size:18px;font-weight:700;color:var(--el-text-color-primary);margin:0 0 6px}
.panel-title p{font-size:13px;color:var(--el-text-color-secondary);line-height:1.6;margin:0}
.panel-body{padding:20px 24px 24px;flex:1;display:flex;flex-direction:column}
.usecase-label{font-size:12px;font-weight:700;color:var(--el-text-color-placeholder);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.usecase-list{display:flex;flex-direction:column;gap:6px;flex:1;overflow-y:auto;max-height:420px;padding-right:4px}
.usecase-list::-webkit-scrollbar{width:4px}
.usecase-list::-webkit-scrollbar-thumb{background:var(--el-border-color);border-radius:2px}
.usecase-item{display:flex;align-items:center;gap:12px;width:100%;padding:12px 14px;border:none;border-radius:10px;background:transparent;cursor:pointer;font-family:inherit;font-size:14px;color:var(--el-text-color-primary);text-align:left;transition:background .2s,transform .15s}
.usecase-item:hover{background:var(--el-fill-color-lighter);transform:translateX(4px)}
.usecase-bullet{display:grid;width:24px;height:24px;flex-shrink:0;border-radius:6px;background:var(--el-color-primary-light-9);color:var(--el-color-primary);font-size:12px;font-weight:700;place-items:center}
.usecase-text{flex:1;min-width:0;line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.usecase-arrow{color:var(--el-text-color-placeholder);flex-shrink:0;transition:transform .2s,color .2s}
.usecase-item:hover .usecase-arrow{color:var(--el-color-primary);transform:translateX(3px)}
.usecase-status{font-size:14px;flex-shrink:0}
.panel-empty{display:flex;flex:1;min-height:120px;flex-direction:column;gap:10px;align-items:center;justify-content:center;color:var(--el-text-color-placeholder);font-size:13px;line-height:1.8;text-align:center}
@media(max-width:900px){.usecase-grid{grid-template-columns:1fr}}

@media(max-width:640px){.dashboard-content{padding:24px 16px 40px}.welcome h2{font-size:24px}}
</style>
