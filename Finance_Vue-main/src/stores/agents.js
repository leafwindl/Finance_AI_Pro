import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import agentsData from '@/data/agents.json'
import { fetchAgentCapabilities } from '@/services/api'
import {
  listConversations,
  getConversationMessages,
  deleteConversation
} from '@/services/api/conversations'

export const useAgentStore = defineStore('agents', () => {
  const agents = ref([])
  const activeAgentId = ref(null)
  const conversations = ref({})
  const recentConversations = computed(() => {
    const all = []
    for (const [agentId, data] of Object.entries(conversations.value)) {
      if (!data?.sessions) continue
      for (const [convId, session] of Object.entries(data.sessions)) {
        // 远程会话在点击前不会加载消息，但仍应出现在刷新后的历史列表中。
        if (convId.startsWith('local_') && session.title === '新对话' && (session.messages?.length || 0) <= 1) continue
        all.push({
          agentId,
          conversationId: convId,
          title: session.title || '',
          updatedAt: session.updatedAt || 0
        })
      }
    }
    return all.sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 10)
  })

  // 从需求流程的会话中提取已完成的需求名称，供测试流程下拉选择
  const requirementNames = computed(() => {
    const names = new Set()
    for (const agentId of ['requirement-pre-review']) {
      const data = conversations.value[agentId]
      if (!data?.sessions) continue
      for (const session of Object.values(data.sessions)) {
        const title = (session.title || '').trim()
        if (title && title !== '新对话') names.add(title)
      }
    }
    return [...names].sort()
  })

  // 需求追踪行数据：跨智能体按需求标题聚合（与 RequirementTracking.vue 的
  // requirementData 同一分组口径），按更新时间倒序。供侧边栏需求列表等使用。
  const requirementRows = computed(() => {
    const groupMap = {}
    for (const [agentId, data] of Object.entries(conversations.value)) {
      if (!data?.sessions) continue
      for (const [convId, session] of Object.entries(data.sessions)) {
        if (convId.startsWith('local_') && session.title === '新对话' && (session.messages?.length || 0) <= 1) continue
        const key = (session.title || '').trim() || '未知需求'
        if (!groupMap[key]) groupMap[key] = {}
        const realId = session.conversationId || (convId.startsWith('local_') ? '' : convId)
        groupMap[key][agentId] = {
          agentId,
          conversationId: realId,
          title: key,
          updatedAt: session.updatedAt || 0
        }
      }
    }
    const rows = []
    for (const [title, agentConvs] of Object.entries(groupMap)) {
      const convs = Object.values(agentConvs)
      // latestConv = 该需求最近活跃的真实会话（当前阶段所在 agent）；
      // 优先有后端 ID 的会话，其次按更新时间取最新。
      const real = convs.filter(c => c.conversationId)
      const latest = (real.length ? real : convs)
        .slice().sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))[0] || null
      rows.push({
        name: title,
        preReviewConv: agentConvs['requirement-pre-review'] || null,
        latestConv: latest,
        updatedAt: Math.max(...convs.map(c => c.updatedAt || 0))
      })
    }
    rows.sort((a, b) => b.updatedAt - a.updatedAt)
    return rows
  })
  const focusRequestToken = ref(0)
  const processingAgentId = ref(null)
  const streamingState = ref(null)

  const activeAgent = computed(() =>
    agents.value.find(a => a.id === activeAgentId.value) || null
  )

  const agentById = computed(() =>
    (id) => agents.value.find(a => a.id === id) || null
  )

  const activeConversation = computed(() => {
    if (!activeAgentId.value) return null
    const agentConvs = conversations.value[activeAgentId.value]
    if (!agentConvs?.sessions) return null
    const activeId = agentConvs.activeSessionId
    return activeId ? agentConvs.sessions[activeId] || null : null
  })

  const activeSessionKey = computed(() => {
    if (!activeAgentId.value) return null
    return conversations.value[activeAgentId.value]?.activeSessionId || null
  })

  function loadAgents() {
    if (agents.value.length === 0) {
      agents.value = agentsData
    }
  }

  function setUserScope(_userId) {
    conversations.value = {}
    activeAgentId.value = null
  }

  async function loadAgentCapabilities() {
    try {
      const { agents: capabilities } = await fetchAgentCapabilities()
      const byId = Object.fromEntries(capabilities.map(item => [item.agent_id, item]))
      agents.value = agents.value.map(agent => ({
        ...agent,
        enabled: byId[agent.id]?.enabled ?? false,
        stateful: byId[agent.id]?.stateful ?? false
      }))
    } catch {
      // 网关不可用时保守禁用，避免把请求错误路由到旧链路。
      agents.value = agents.value.map(agent => ({ ...agent, enabled: false }))
    }
  }

  async function syncRemoteConversations(agentId) {
    const { conversations: remoteItems } = await listConversations({ agentId, limit: 100 })
    if (!conversations.value[agentId]?.sessions) {
      conversations.value[agentId] = { sessions: {}, activeSessionId: null }
    }
    const agentConvs = conversations.value[agentId]
    for (const item of remoteItems) {
      const id = item.conversation_id
      const existing = agentConvs.sessions[id]
      agentConvs.sessions[id] = {
        conversationId: id,
        title: item.title || '新对话',
        reviewDecision: item.review_decision || null,
        reviewDecidedAt: item.review_decided_at || null,
        messages: existing?.messages || [],
        messagesLoaded: existing?.messagesLoaded || false,
        updatedAt: Date.parse(item.updated_at) || Date.now()
      }
    }
  }

  async function syncAllRemoteConversations() {
    await Promise.allSettled(agents.value.map(agent => syncRemoteConversations(agent.id)))
  }

  async function loadRemoteMessages(agentId, conversationId) {
    const agentConvs = conversations.value[agentId]
    const session = agentConvs?.sessions?.[conversationId]
    if (!session || session.messagesLoaded) return
    const { messages } = await getConversationMessages(conversationId)
    session.messages = messages.map(message => ({
      id: message.message_id,
      messageId: String(message.message_id),
      role: message.role,
      content: message.content,
      createdAt: message.created_at,
      needApproval: message.review_decision === 'pending',
      approvalId: message.approval_id || '',
      conversationId,
      approved: message.review_decision === 'approve'
        ? true
        : ['reject', 'revise'].includes(message.review_decision) ? false : null,
      rejectionReason: message.rejection_reason || '',
      decidedAt: message.decided_at || null
    }))
    session.messagesLoaded = true
  }

  // 实时 SSE 流程结束时把审批元数据补写到 store 的最后一条 assistant 消息，
  // 避免"同路由切换会话不重新拉取"时显示成历史报告。
  function enrichLastMessage(agentId, fields) {
    const agentConvs = conversations.value[agentId]
    if (!agentConvs?.sessions) return
    const activeId = agentConvs.activeSessionId
    const session = activeId ? agentConvs.sessions[activeId] : null
    const msgs = session?.messages || []
    if (msgs.length) Object.assign(msgs[msgs.length - 1], fields)
  }

  async function deleteRemoteConversation(agentId, conversationId) {
    await deleteConversation(conversationId)
    const agentConvs = conversations.value[agentId]
    if (agentConvs?.sessions?.[conversationId]) {
      delete agentConvs.sessions[conversationId]
      if (agentConvs.activeSessionId === conversationId) {
        agentConvs.activeSessionId = null
      }
    }

  }

  function clearUserScope() {
    conversations.value = {}
    activeAgentId.value = null
  }

  function setActiveAgent(agentId, conversationId) {
    activeAgentId.value = agentId
    if (!conversations.value[agentId]?.sessions) {
      initConversation(agentId)
      return
    }
    const agentConvs = conversations.value[agentId]
    // 按 conversationId 字段查找匹配的 session
    if (conversationId) {
      const match = findSessionByConversationId(agentConvs, conversationId)
      if (match) {
        agentConvs.activeSessionId = match[0]
        return
      }
    }
    if (!agentConvs.activeSessionId || !agentConvs.sessions[agentConvs.activeSessionId]) {
      initConversation(agentId)
    }
  }

  function requestFocus() {
    focusRequestToken.value++
  }

  function startProcessing(agentId, _sessionKey) {
    processingAgentId.value = agentId
    streamingState.value = {
      status: '处理中...',
      node: 'init',
      fullAnswer: '',
      streamingStarted: false,
      convId: '',
      failed: false
    }
  }

  function updateStreaming(updates) {
    if (!streamingState.value) return
    Object.assign(streamingState.value, updates)
  }

  function clearProcessingAgent(agentId) {
    if (processingAgentId.value === agentId) {
      processingAgentId.value = null
      streamingState.value = null
    }
  }

  function isProcessingAgent(agentId) {
    return processingAgentId.value === agentId
  }

  // 按 Gateway conversationId 查找 session，返回 [key, session] 或 null
  function findSessionByConversationId(agentConvs, conversationId) {
    if (!conversationId) return null
    // 优先按 session key 查找。
    if (agentConvs.sessions[conversationId]) {
      return [conversationId, agentConvs.sessions[conversationId]]
    }
    // 兜底：兼容旧缓存中 key 与 conversationId 不一致的情况。
    const found = Object.entries(agentConvs.sessions).find(
      ([, s]) => s.conversationId === conversationId
    )
    return found || null
  }

  function initConversation(agentId) {
    const agent = agents.value.find(a => a.id === agentId)
    if (!agent) return

    if (!conversations.value[agentId]?.sessions) {
      conversations.value[agentId] = { sessions: {}, activeSessionId: null }
    }

    const agentConvs = conversations.value[agentId]
    // 每次新建会话都用唯一临时 ID，避免多个新会话互相覆盖
    const tempId = 'local_' + Date.now()
    agentConvs.activeSessionId = tempId
    agentConvs.sessions[tempId] = {
      conversationId: '',
      title: '新对话',
      messages: [{
        id: 1,
        role: 'assistant',
        content: `你好，我是${agent.name}。你可以直接描述需求，也可以点击下方的示例问题开始。`
      }],
      updatedAt: Date.now()
    }

  }

  /** 从当前智能体的问题池中随机提供最多三条示例问题。 */
  function getSuggestedQuestions(agentId) {
    const agent = agents.value.find(a => a.id === agentId)
    if (!agent) return []

    const pool = agent.questionPool || agent.suggestedQuestions
    if (!pool || pool.length === 0) return []

    if (pool.length <= 3) return [...pool]

    const shuffled = [...pool]
    // Fisher-Yates 洗牌
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }
    return shuffled.slice(0, 3)
  }

  function getMessages(agentId) {
    const agentConvs = conversations.value[agentId]
    if (!agentConvs?.sessions) return []
    const activeId = agentConvs.activeSessionId
    return activeId ? agentConvs.sessions[activeId]?.messages || [] : []
  }

  function addMessage(agentId, role, content, files = null) {
    if (!conversations.value[agentId]?.sessions) {
      initConversation(agentId)
    }
    const agentConvs = conversations.value[agentId]
    const activeId = agentConvs.activeSessionId
    if (!activeId || !agentConvs.sessions[activeId]) {
      initConversation(agentId)
      // retry after init
      const newActiveId = conversations.value[agentId].activeSessionId
      const session = conversations.value[agentId].sessions[newActiveId]
      const maxId = session.messages.reduce((max, m) => Math.max(max, m.id), 0)
      session.messages.push({ id: maxId + 1, role, content, files: files || undefined })
      session.updatedAt = Date.now()

      return
    }
    const session = agentConvs.sessions[activeId]
    const maxId = session.messages.reduce((max, m) => Math.max(max, m.id), 0)
    session.messages.push({ id: maxId + 1, role, content, files: files || undefined })
    session.updatedAt = Date.now()
    // 第一条用户消息作为会话标题
    if (session.title === '新对话' && role === 'user') {
      session.title = content.length > 30 ? content.slice(0, 30) + '...' : content
    }

  }

  function updateConversationId(agentId, conversationId) {
    // 后端没返回或是空值，保持前端生成的 key
    if (!conversationId) return

    const agentConvs = conversations.value[agentId]
    if (!agentConvs?.sessions) return

    const activeId = agentConvs.activeSessionId
    const session = activeId ? agentConvs.sessions[activeId] : null
    if (!session) return

    // 用 Gateway 返回的会话 ID 替换临时 key，一个 ID 走到底。
    delete agentConvs.sessions[activeId]
    session.conversationId = conversationId
    agentConvs.sessions[conversationId] = session
    agentConvs.activeSessionId = conversationId

  }

  function newConversation(agentId) {
    initConversation(agentId)
  }

  /**
   * 获取指定智能体的所有会话列表，供侧边栏历史展示
   */
  function getSessions(agentId) {
    const agentConvs = conversations.value[agentId]
    if (!agentConvs?.sessions) return []
    return Object.values(agentConvs.sessions)
      .filter(s => s.conversationId || (s.messages && s.messages.length > 1))
      .sort((a, b) => b.updatedAt - a.updatedAt)
  }

  /**
   * 切换到指定会话
   */
  function switchSession(agentId, conversationId) {
    const agentConvs = conversations.value[agentId]
    if (!agentConvs?.sessions) return
    const match = findSessionByConversationId(agentConvs, conversationId)
    if (match) {
      agentConvs.activeSessionId = match[0]

    }
  }

  return {
    agents,
    activeAgentId,
    conversations,
    recentConversations,
    requirementNames,
    requirementRows,
    activeAgent,
    agentById,
    activeConversation,
    activeSessionKey,
    loadAgents,
    setUserScope,
    loadAgentCapabilities,
    syncRemoteConversations,
    syncAllRemoteConversations,
    loadRemoteMessages,
    enrichLastMessage,
    deleteRemoteConversation,
    clearUserScope,
    setActiveAgent,
    getMessages,
    getSuggestedQuestions,
    addMessage,
    updateConversationId,
    newConversation,
    getSessions,
    switchSession,
    focusRequestToken,
    requestFocus,
    processingAgentId,
    streamingState,
    startProcessing,
    updateStreaming,
    clearProcessingAgent,
    isProcessingAgent
  }
})
