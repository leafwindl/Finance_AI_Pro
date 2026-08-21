<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAgentStore } from '@/stores/agents'
import { sendApproval, sendChatMessage } from '@/services/api'
import { useTypewriter } from '@/composables/useTypewriter'
import { downloadReport } from '@/utils/downloadReport'
import { readScopedMap, writeScopedMap } from '@/utils/userStorage'
import ChatHeader from '@/components/chat/ChatHeader.vue'
import ChatMessages from '@/components/chat/ChatMessages.vue'
import RequirementSummaryCard from '@/components/review/RequirementSummaryCard.vue'
import ReviewProgress from '@/components/review/ReviewProgress.vue'
import ReviewReportCard from '@/components/review/ReviewReportCard.vue'
import AnalysisProgress from '@/components/analysis/AnalysisProgress.vue'
import AnalysisReportCard from '@/components/analysis/AnalysisReportCard.vue'

const props = defineProps({
  agentId: { type: String, required: true }
})

const route = useRoute()
const router = useRouter()
const agentStore = useAgentStore()

agentStore.loadAgents()
agentStore.setActiveAgent(props.agentId, route.query.conversationId)

const agent = computed(() => agentStore.agentById(props.agentId))
const messages = ref([])
const loading = ref(false)
// 需求名称，随链路传递：Dashboard → Agent 1 → Agent 2 → TestCaseEditor
const requirementTitle = ref('')
const isRequirementReview = computed(() => props.agentId === 'requirement-pre-review')
const isRequirementAnalysis = computed(() => props.agentId === 'ai-test-analysis')

const typewriter = useTypewriter(30)
let _twMsg = null
let _lastRequestKey = null

const initMessages = () => {
  const stored = agentStore.getMessages(props.agentId)
  messages.value = stored.length > 0 ? [...stored] : []

  if (agentStore.isProcessingAgent(props.agentId)) {
    const state = agentStore.streamingState
    if (state) {
      loading.value = true
      if (state.streamingStarted) {
        const msg = { id: Date.now(), role: 'assistant', content: state.fullAnswer }
        messages.value.push(msg)
        _twMsg = msg
        typewriter.reset()
        typewriter.source.value = state.fullAnswer
        typewriter.start()
      } else {
        messages.value.push({
          id: Date.now(),
          role: 'pending',
          status: state.status || '处理中...',
          node: state.node || 'requirement_parser'
        })
        _twMsg = null
      }
    }
  }
}

const initializeConversation = async () => {
  // 捕获需求名称（来自 Dashboard），传递到下游
  if (route.query.title) requirementTitle.value = route.query.title

  // Snapshot the auto-submit query before changing the route. `route.query` is
  // reactive: after router.replace() it becomes empty. The old flow then ran
  // initMessages() after an await and replaced the live SSE message with a
  // static copy, so the UI stayed at "处理中..." while the detached object kept
  // receiving progress and the final answer.
  const autoQuery = typeof route.query.q === 'string' ? route.query.q : ''
  if (autoQuery) {
    const pid = route.query.pid || ''
    const requestKey = pid ? `${props.agentId}:${pid}` : ''
    if (pid && requestKey !== _lastRequestKey) {
      _lastRequestKey = requestKey
      agentStore.newConversation(props.agentId)
      initMessages()
      void handleSend({ text: autoQuery })
    } else if (!pid) {
      void handleSend({ text: autoQuery })
    } else {
      initMessages()
    }
    await router.replace({ path: `/chat/${props.agentId}`, query: {} })
    return
  }

  try { await agentStore.syncRemoteConversations(props.agentId) } catch {}
  agentStore.setActiveAgent(props.agentId, route.query.conversationId)
  if (route.query.conversationId) {
    try { await agentStore.loadRemoteMessages(props.agentId, route.query.conversationId) } catch {}
  }
  initMessages()
}

onMounted(initializeConversation)

watch(() => props.agentId, async (newId) => {
  loading.value = false
  typewriter.reset()
  _twMsg = null
  // 在 router.replace 清理 query 之前捕获 title
  if (route.query.title) requirementTitle.value = route.query.title
  try {
    await agentStore.syncRemoteConversations(newId)
  } catch {
    // Keep local UI available.
  }
  agentStore.setActiveAgent(newId, route.query.conversationId)
  initMessages()

  if (route.query.q) {
    const pid = route.query.pid || ''
    const requestKey = pid ? `${newId}:${pid}` : ''
    if (pid && requestKey !== _lastRequestKey) {
      _lastRequestKey = requestKey
      agentStore.newConversation(props.agentId)
      initMessages()
      handleSend({ text: route.query.q })
    } else if (!pid) {
      handleSend({ text: route.query.q })
    }
    router.replace({ path: `/chat/${newId}`, query: {} })
  }
})

watch(() => route.query.conversationId, async (newConvId) => {
  if (newConvId && newConvId !== agentStore.activeSessionKey) {
    agentStore.switchSession(props.agentId, newConvId)
    // 同路由切换会话也要补拉远端消息，避免显示 store 中的过期快照
    // （如实时流程刚跑完、审批字段尚未回填时跳转到该会话）。
    try { await agentStore.loadRemoteMessages(props.agentId, newConvId) } catch {}
    initMessages()
  }
})

const reviewRequirementMessage = computed(() =>
  [...messages.value].reverse().find(message => message.role === 'user') || null
)
const reviewPendingMessage = computed(() =>
  [...messages.value].reverse().find(message => message.role === 'pending') || null
)
const reviewErrorMessage = computed(() =>
  [...messages.value].reverse().find(message => message.role === 'error') || null
)
const reviewReportCandidate = computed(() => {
  const reports = [...messages.value].reverse().filter(message =>
    message.role === 'assistant'
    && typeof message.content === 'string'
    && message.content.length > 200
    && !message.content.startsWith('你好，我是')
  )
  // 优先展示已决策（已通过/已驳回）的报告，避免被驳回后新产生的
  // 待审批报告把状态顶成"待审批"；全部未决策时才取最新一条。
  return reports.find(m => m.approved === true || m.approved === false) || reports[0] || null
})
const reviewReportMessage = computed(() => {
  const message = reviewReportCandidate.value
  if (!message) return null
  return message.needApproval || !loading.value ? message : null
})
const reviewNode = computed(() =>
  agentStore.streamingState?.node
  || reviewPendingMessage.value?.node
  || (reviewReportMessage.value ? 'report_generator' : 'requirement_parser')
)
const reviewStatus = computed(() =>
  agentStore.streamingState?.status || reviewPendingMessage.value?.status || ''
)
const reviewDisplayTitle = computed(() =>
  requirementTitle.value
  || agentStore.activeConversation?.title
  || '待评审需求'
)

const analysisRequirementMessage = computed(() =>
  [...messages.value].reverse().find(message => message.role === 'user') || null
)
const analysisPendingMessage = computed(() =>
  [...messages.value].reverse().find(message => message.role === 'pending') || null
)
const analysisErrorMessage = computed(() =>
  [...messages.value].reverse().find(message => message.role === 'error') || null
)
const analysisReportMessage = computed(() =>
  [...messages.value].reverse().find(message =>
    message.role === 'assistant'
    && typeof message.content === 'string'
    && message.content.length > 100
    && !message.content.startsWith('你好，我是')
  ) || null
)
const analysisNode = computed(() =>
  agentStore.streamingState?.node
  || analysisPendingMessage.value?.node
  || (analysisReportMessage.value ? 'rag_response' : 'extract_keywords')
)
const analysisStatus = computed(() =>
  agentStore.streamingState?.status || analysisPendingMessage.value?.status || ''
)

watch(() => typewriter.display.value, (val) => {
  if (_twMsg) _twMsg.content = val
})

/* ——— 审批方法 ——— */

const handleDownload = (msg) => {
  const prefix = props.agentId === 'ai-test-analysis' ? '六维测试分析报告' : '预评审报告'
  const filename = `${prefix}-${new Date().toISOString().slice(0, 10)}.md`
  downloadReport(msg.content, filename)
}

const handleApprove = async (conversationId, messageId) => {
  const msg = messages.value.find(m => m.messageId === messageId)
  if (!msg) return
  try {
    await sendApproval({
      conversation_id: conversationId,
      approval_id: msg.approvalId,
      decision: 'approve'
    })
  } catch (e) {
    ElMessage.error(`审批失败：${e.message || '请稍后重试'}`)
    return
  }
  msg.approved = true

  const pid = route.query.pid || (_lastRequestKey?.split(':').slice(1).join(':') || '')
  if (pid) {
    // 按用户隔离存储（换账号不残留）
    const s = readScopedMap('card_status')
    s[pid] = 'approved'
    writeScopedMap('card_status', s)
  }

  // Agent 1 只负责预评审；人工通过后，将原始需求交给独立的 Agent 2
  // 生成六维分析报告。两个 Agent 分别建立并持久化自己的会话。
  if (props.agentId === 'requirement-pre-review') {
    const requirement = reviewRequirementMessage.value?.content || ''
    await router.push({
      path: '/chat/ai-test-analysis',
      query: {
        q: requirement,
        pid,
        title: requirementTitle.value || agentStore.activeConversation?.title || ''
      }
    })
  }
}

const handleReject = async (conversationId, messageId, reason = '') => {
  const msg = messages.value.find(m => m.messageId === messageId)
  if (!msg) return
  try {
    await sendApproval({
      conversation_id: conversationId,
      approval_id: msg.approvalId,
      decision: 'reject',
      reason
    })
  } catch (e) {
    ElMessage.error(`驳回失败：${e.message || '请稍后重试'}`)
    return
  }
  msg.approved = false

  const pid = route.query.pid || (_lastRequestKey?.split(':').slice(1).join(':') || '')
  if (pid) {
    // 按用户隔离存储（换账号不残留）
    const s = readScopedMap('card_status')
    s[pid] = 'rejected'
    writeScopedMap('card_status', s)
  }

  if (props.agentId === 'requirement-pre-review') {
    setTimeout(() => {
      router.push('/')
    }, 500)
  }
}

const handleToTestFlow = (msg) => {
  router.push({
    path: '/test-case/write',
    query: {
      title: requirementTitle.value,
      requirement: msg?.content || '',
      pid: route.query.pid || (_lastRequestKey?.split(':').slice(1).join(':') || '')
    }
  })
}

const handleViewSixDim = async () => {
  // 从预评审报告"查看六维分析"按钮：优先复用该需求已有的六维分析会话，
  // 跳转到独立的六维报告查看页（只读已生成的报告，不会重新跑 Agent2）；
  // 找不到已有会话时才发起新的六维分析（与"通过并继续"一致，自动提交需求文本触发 Agent2）。
  const agentId = 'ai-test-analysis'
  const title = (requirementTitle.value || agentStore.activeConversation?.title || '').trim()
  // 会话标题由后端按"需求文本前 100 字"生成（chat.py: title=payload.query[:100]），
  // 因此用需求文本匹配（与 Dashboard openPreReview 的匹配方式一致），
  // 需求名称仅作兜底（手动创建、首条消息即需求名的会话）。
  const requirement = reviewRequirementMessage.value?.content || ''
  const contentKey = requirement.slice(0, 100)
  try {
    await agentStore.syncRemoteConversations(agentId)
    const sessions = agentStore.conversations[agentId]?.sessions || {}
    const existing = Object.values(sessions).find(s => {
      const st = (s.title || '').trim()
      return (contentKey && st === contentKey) || st === title
    })
    if (existing) {
      await agentStore.loadRemoteMessages(agentId, existing.conversationId)
      router.push({
        path: '/six-dim-report',
        query: { conversationId: existing.conversationId, title }
      })
      return
    }
  } catch { /* 网关不可用时按无已有会话处理，发起新分析 */ }
  if (requirement) {
    // 尚无该需求的六维分析会话：跳转到 Agent2 工作台自动发起分析（同"通过并继续"）。
    const pid = route.query.pid || (_lastRequestKey?.split(':').slice(1).join(':') || '')
    router.push({
      path: '/chat/ai-test-analysis',
      query: { q: requirement, pid, title }
    })
    return
  }
  router.push({ path: '/six-dim-report', query: { title } })
}

/* ——— 发消息 ——— */

const handleSend = async ({ text, files = [] }) => {
  const agentId = props.agentId

  if (agentStore.processingAgentId && agentStore.processingAgentId !== agentId) {
    const hintMsg = { id: Date.now(), role: 'assistant', content: '暂不支持此功能，有其他智能体正在运转，请等待。' }
    messages.value.push(hintMsg)
    agentStore.addMessage(agentId, 'assistant', '暂不支持此功能，有其他智能体正在运转，请等待。')
    return
  }

  agentStore.startProcessing(agentId, agentStore.activeSessionKey)

  messages.value.push({
    id: Date.now(),
    role: 'user',
    content: text,
    files: files.length > 0 ? files : undefined
  })
  agentStore.addMessage(agentId, 'user', text, files.length > 0 ? files : null)
  loading.value = true

  // Keep the same reactive object reference while SSE events mutate its
  // status/role/content. Mutating the original raw object after pushing it
  // into a reactive array does not reliably trigger a Vue render.
  const pendingMsg = reactive({
    id: Date.now() + 1,
    role: 'pending',
    status: '正在启动评审流程...',
    node: agentId === 'requirement-pre-review' ? 'requirement_parser' : 'init'
  })
  messages.value.push(pendingMsg)
  _twMsg = messages.value[messages.value.length - 1]
  typewriter.reset()

  let fullAnswer = '', convId = '', msgId = '', streamingStarted = false, failed = false

  try {
    const stream = await sendChatMessage({
      query: text,
      conversation_id: agentStore.activeConversation?.conversationId || '',
      agent_id: agentId,
      file_ids: files.map(f => f.file_id).filter(Boolean)
    })

    for await (const { event, data } of stream) {
      switch (event) {
        case 'progress':
          pendingMsg.status = data.message || '正在处理...'
          pendingMsg.node = data.node || pendingMsg.node
          agentStore.updateStreaming({ status: pendingMsg.status, node: pendingMsg.node })
          break

        case 'delta': {
          const chunkText = data.text || ''
          if (!streamingStarted) { streamingStarted = true; pendingMsg.role = 'assistant'; pendingMsg.content = '' }
          fullAnswer += chunkText
          typewriter.source.value = fullAnswer
          typewriter.start()
          agentStore.updateStreaming({ fullAnswer, streamingStarted: true, status: '' })
          break
        }

        case 'completed':
          fullAnswer = data.answer || fullAnswer
          convId = data.conversation_id || ''
          msgId = data.message_id || ''
          if (!streamingStarted && fullAnswer) {
            streamingStarted = true
            pendingMsg.role = 'assistant'
            pendingMsg.content = ''
          }
          typewriter.source.value = fullAnswer
          typewriter.start()
          agentStore.updateStreaming({ fullAnswer, convId, streamingStarted: true, status: '' })
          break

        case 'approval_required':
          fullAnswer = data.answer || fullAnswer
          convId = data.conversation_id || convId
          msgId = data.message_id || msgId
          pendingMsg.role = 'assistant'
          pendingMsg.content = fullAnswer
          pendingMsg.needApproval = true
          pendingMsg.messageId = msgId
          pendingMsg.approvalId = data.approval_id || ''
          pendingMsg.conversationId = convId
          pendingMsg.approved = null
          streamingStarted = true
          agentStore.updateStreaming({ fullAnswer, convId, streamingStarted: true, status: '' })
          break

        case 'message_end':
          convId = data.conversation_id || convId
          break

        case 'error':
          failed = true
          typewriter.reset()
          pendingMsg.role = 'error'
          pendingMsg.content = `请求失败：${data.message || '未知错误'}`
          convId = ''
          agentStore.updateStreaming({ failed: true, status: '错误' })
          break

        default: {
          const txt = data.content || data.data?.text || data.text || ''
          if (txt) {
            if (!streamingStarted) { streamingStarted = true; pendingMsg.role = 'assistant'; pendingMsg.content = '' }
            fullAnswer += txt; typewriter.source.value = fullAnswer; typewriter.start()
          }
          break
        }
      }
    }

    if (fullAnswer && !failed) {
      agentStore.addMessage(agentId, 'assistant', fullAnswer)
      // 审批元数据同步进 store（侧边栏/追踪表再进入时不显示成历史报告）
      if (pendingMsg.needApproval) {
        agentStore.enrichLastMessage(agentId, {
          needApproval: pendingMsg.needApproval,
          approvalId: pendingMsg.approvalId,
          messageId: pendingMsg.messageId,
          conversationId: pendingMsg.conversationId,
          approved: null
        })
      }
    }
    if (convId) {
      agentStore.updateConversationId(agentId, convId)
    }

    if (props.agentId !== agentId) return

    if (convId) {
      router.replace({
        path: `/chat/${agentId}`,
        query: { conversationId: convId }
      })
    }

  } catch (error) {
    typewriter.reset()
    pendingMsg.role = 'error'
    pendingMsg.content = `请求失败：${error.message}`
  } finally {
    loading.value = false
    agentStore.clearProcessingAgent(agentId)
  }
}

const handleNewConversation = () => {
  agentStore.newConversation(props.agentId)
  initMessages()
  router.replace(`/chat/${props.agentId}`)
}
</script>

<template>
  <div v-if="agent && isRequirementReview" class="review-view">
    <ChatHeader :agent="agent" :is-online="true" :hide-new="true" @new-conversation="handleNewConversation" />
    <main class="review-scroll">
      <div class="review-container">
        <div class="review-intro">
          <div><span>REQUIREMENT REVIEW</span><h1>需求预评审工作台</h1></div>
          <p>基于业务知识、合规规则和历史案例完成结构化评审，报告生成后由人工确认。</p>
        </div>
        <RequirementSummaryCard
          :title="reviewDisplayTitle"
          :content="reviewRequirementMessage?.content || ''"
          :files="reviewRequirementMessage?.files || []"
        />
        <ReviewProgress
          :loading="loading"
          :node="reviewNode"
          :status="reviewStatus"
          :has-report="Boolean(reviewReportMessage)"
          :failed="Boolean(reviewErrorMessage)"
        />
        <div v-if="reviewErrorMessage" class="review-error">
          <div class="error-icon"><el-icon><WarningFilled /></el-icon></div>
          <div><strong>预评审执行失败</strong><p>{{ reviewErrorMessage.content }}</p></div>
          <el-button type="primary" plain @click="handleSend({ text: reviewRequirementMessage?.content || '' })">重新执行</el-button>
        </div>
        <ReviewReportCard
          v-if="reviewReportMessage"
          :message="reviewReportMessage"
          @download="handleDownload"
          @approve="msg => handleApprove(msg.conversationId || '', msg.messageId)"
          @reject="(msg, reason) => handleReject(msg.conversationId || '', msg.messageId, reason)"
          @viewSixDim="handleViewSixDim"
        />
        <div v-else-if="!loading && !reviewErrorMessage" class="report-placeholder">
          <el-icon :size="30"><DocumentChecked /></el-icon>
          <strong>报告将在评审完成后显示</strong>
          <span>提交需求后，系统会在这里展示唯一的预评审报告。</span>
        </div>
      </div>
    </main>
  </div>

  <div v-else-if="agent && isRequirementAnalysis" class="analysis-view">
    <ChatHeader :agent="agent" :is-online="true" :hide-new="true" @new-conversation="handleNewConversation" />
    <main class="analysis-scroll">
      <div class="analysis-container">
        <div class="analysis-intro">
          <div><span>REQUIREMENT TEST ANALYSIS</span><h1>六维测试分析工作台</h1></div>
          <p>预评审已通过。六维分析智能体将结合业务知识、测试规范和监管要求，生成结构化测试分析报告。</p>
        </div>
        <RequirementSummaryCard
          :title="requirementTitle || agentStore.activeConversation?.title || '已通过预评审的需求'"
          :content="analysisRequirementMessage?.content || ''"
          :files="analysisRequirementMessage?.files || []"
          stage-label="预评审已通过"
          stage-type="success"
        />
        <AnalysisProgress
          :loading="loading"
          :node="analysisNode"
          :status="analysisStatus"
          :has-report="Boolean(analysisReportMessage)"
          :failed="Boolean(analysisErrorMessage)"
        />
        <div v-if="analysisErrorMessage" class="review-error">
          <div class="error-icon"><el-icon><WarningFilled /></el-icon></div>
          <div><strong>六维分析执行失败</strong><p>{{ analysisErrorMessage.content }}</p></div>
          <el-button type="primary" plain @click="handleSend({ text: analysisRequirementMessage?.content || '' })">重新执行</el-button>
        </div>
        <AnalysisReportCard
          v-if="analysisReportMessage"
          :message="analysisReportMessage"
          @download="handleDownload"
          @home="router.push('/')"
          @next="handleToTestFlow"
        />
        <div v-else-if="!loading && !analysisErrorMessage" class="report-placeholder analysis-placeholder">
          <el-icon :size="30"><DataAnalysis /></el-icon>
          <strong>六维报告将在分析完成后显示</strong>
          <span>智能体将从六个测试维度识别范围、风险和测试重点。</span>
        </div>
      </div>
    </main>
  </div>

  <div v-else-if="agent" class="chat-view">
    <ChatHeader :agent="agent" :is-online="true" @new-conversation="handleNewConversation" />
    <ChatMessages
      :messages="messages"
      :loading="loading"
    />
  </div>

  <div v-else class="chat-view is-empty">
    <div class="not-found">
      <el-icon :size="48" color="var(--el-text-color-placeholder)"><Warning /></el-icon>
      <h2>智能体不存在</h2>
      <p>未找到 ID 为 "{{ props.agentId }}" 的智能体</p>
      <el-button type="primary" @click="$router.push('/')">返回首页</el-button>
    </div>
  </div>
</template>

<style scoped>
.chat-view { display:flex; flex-direction:column; height:100vh; background:var(--el-bg-color-page) }
.review-view { display:flex; flex-direction:column; height:100vh; background:var(--el-bg-color-page) }
.analysis-view { display:flex; flex-direction:column; height:100vh; background:var(--el-bg-color-page) }
.review-scroll { flex:1; min-height:0; overflow-y:auto; background:radial-gradient(circle at 15% 0,rgba(15,108,189,.07),transparent 34%),var(--el-bg-color-page) }
.analysis-scroll { flex:1; min-height:0; overflow-y:auto; background:radial-gradient(circle at 12% 0,rgba(114,87,217,.1),transparent 34%),radial-gradient(circle at 90% 12%,rgba(61,144,214,.06),transparent 27%),var(--el-bg-color-page) }
.review-container { display:flex; flex-direction:column; gap:18px; width:min(1180px,calc(100% - 48px)); margin:0 auto; padding:30px 0 56px }
.analysis-container { display:flex; flex-direction:column; gap:18px; width:min(1180px,calc(100% - 48px)); margin:0 auto; padding:30px 0 56px }
.review-intro { display:flex; align-items:flex-end; justify-content:space-between; gap:28px; padding:4px 2px 2px }
.analysis-intro { display:flex; align-items:flex-end; justify-content:space-between; gap:28px; padding:4px 2px 2px }
.review-intro span { color:var(--el-color-primary); font-size:10px; font-weight:800; letter-spacing:.15em }
.analysis-intro span { color:#7257d9; font-size:10px; font-weight:800; letter-spacing:.15em }
.review-intro h1 { margin:5px 0 0; color:var(--el-text-color-primary); font-size:26px; line-height:1.25 }
.analysis-intro h1 { margin:5px 0 0; color:var(--el-text-color-primary); font-size:26px; line-height:1.25 }
.review-intro p { max-width:520px; margin:0; color:var(--el-text-color-secondary); font-size:13px; line-height:1.7; text-align:right }
.analysis-intro p { max-width:560px; margin:0; color:var(--el-text-color-secondary); font-size:13px; line-height:1.7; text-align:right }
.analysis-placeholder { border-color:#d9d1f5; background:linear-gradient(135deg,#f7f5ff,var(--el-bg-color)) }
.review-error { display:flex; align-items:center; gap:14px; padding:18px 20px; color:var(--el-color-danger); border:1px solid var(--el-color-danger-light-7); border-radius:14px; background:var(--el-color-danger-light-9) }
.review-error > div:nth-child(2) { min-width:0; flex:1 }
.review-error p { margin:4px 0 0; font-size:13px }
.error-icon { display:grid; width:38px; height:38px; color:#fff; border-radius:10px; background:var(--el-color-danger); place-items:center }
.report-placeholder { display:flex; min-height:180px; align-items:center; justify-content:center; flex-direction:column; gap:9px; color:var(--el-text-color-placeholder); border:1px dashed var(--el-border-color); border-radius:16px; background:var(--el-bg-color) }
.report-placeholder strong { color:var(--el-text-color-secondary); font-size:14px }
.report-placeholder span { font-size:12px }
.chat-view.is-empty { align-items:center; justify-content:center }
.not-found { text-align:center }
.not-found h2 { margin:12px 0 8px; color:var(--el-text-color-primary); font-size:20px }
.not-found p { margin:0 0 20px; color:var(--el-text-color-secondary); font-size:14px }
@media (max-width:720px) { .review-container,.analysis-container { width:calc(100% - 24px); padding:18px 0 36px } .review-intro,.analysis-intro { align-items:flex-start; flex-direction:column } .review-intro p,.analysis-intro p { text-align:left } }
</style>
