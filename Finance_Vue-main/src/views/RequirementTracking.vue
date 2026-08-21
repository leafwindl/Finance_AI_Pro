<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const agentStore = useAgentStore()

const searchQuery = ref('')

const AGENT_PRE_REVIEW = 'requirement-pre-review'
const AGENT_TEST_ANALYSIS = 'ai-test-analysis'

function statusTagType(status) {
  if (status === '通过') return 'success'
  if (status === '未通过') return 'danger'
  if (status === '待审批') return 'warning'
  if (status === '进行中') return ''
  return 'info'
}

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

const filteredData = computed(() => {
  if (!searchQuery.value.trim()) return requirementData.value
  const q = searchQuery.value.trim().toLowerCase()
  return requirementData.value.filter(item => item.name.toLowerCase().includes(q) || item.id.toLowerCase().includes(q))
})

function openConv(conv) {
  if (!conv) return
  agentStore.setActiveAgent(conv.agentId, conv.conversationId)
  agentStore.requestFocus()
  router.push({ path: `/chat/${conv.agentId}`, query: { conversationId: conv.conversationId } })
}

// ---------- 删除某条需求的全部记录 ----------
// 一行需求可能对应多个智能体的多条同名会话，删除时全部清理：
// 远程会话调 Gateway DELETE 并同步移除 store；本地临时会话（无后端记录）直接从 store 移除。
async function deleteRow(row) {
  const targets = []
  let localRemoved = 0
  for (const [agentId, data] of Object.entries(agentStore.conversations)) {
    if (!data?.sessions) continue
    for (const [convKey, session] of Object.entries(data.sessions)) {
      if ((session.title || '').trim() !== row.name) continue
      const convId = session.conversationId || (convKey.startsWith('local_') ? '' : convKey)
      if (convId) {
        targets.push({ agentId, conversationId: convId })
      } else {
        delete data.sessions[convKey]
        if (data.activeSessionId === convKey) data.activeSessionId = null
        localRemoved++
      }
    }
  }

  const failed = []
  for (const t of targets) {
    try {
      await agentStore.deleteRemoteConversation(t.agentId, t.conversationId)
    } catch {
      failed.push(t.conversationId)
    }
  }
  const okCount = targets.length - failed.length + localRemoved
  if (failed.length) {
    ElMessage.warning(`已删除 ${okCount} 条记录，${failed.length} 条删除失败`)
  } else {
    ElMessage.success('该需求的全部记录已删除')
  }
}

async function confirmDelete(row) {
  const name = row.name.length > 24 ? row.name.slice(0, 24) + '…' : row.name
  try {
    await ElMessageBox.confirm(
      `确定删除需求「${name}」的全部记录吗？删除后不可恢复。`,
      '删除确认',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return // 点击取消/关闭弹窗 → 不删除
  }
  await deleteRow(row)
}

onMounted(async () => {
  agentStore.loadAgents()
  try { await agentStore.syncAllRemoteConversations() } catch { /* 网关不可用时显示已有本地会话 */ }
})
</script>

<template>
<div class="tracking-page">
  <div class="tracking-scroll">
    <div class="tracking-content">
      <div class="page-header">
        <button class="back" @click="router.push('/')"><el-icon><ArrowLeft /></el-icon>返回首页</button>
        <div class="title-row">
          <div>
            <span class="eyebrow">REQUIREMENT TRACKING</span>
            <h1>需求追踪</h1>
            <p>查看各需求在预评审、六维分析、用例评审与步骤生成各环节的进度。</p>
          </div>
          <div class="search-bar">
            <el-input v-model="searchQuery" placeholder="搜索需求名称..." clearable :prefix-icon="'Search'" />
          </div>
        </div>
      </div>

      <div class="table-wrapper">
        <table class="req-table">
          <thead>
            <tr>
              <th class="col-id">编号</th>
              <th class="col-name">需求名称</th>
              <th class="col-status">评审报告</th>
              <th class="col-report">六维报告</th>
              <th class="col-status">用例评审</th>
              <th class="col-steps">用例步骤</th>
              <th class="col-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredData.length === 0"><td colspan="7" class="empty-row">暂无匹配的需求记录</td></tr>
            <tr v-for="row in filteredData" :key="row.id" class="data-row">
              <td class="col-id"><span class="req-id">{{ row.id }}</span></td>
              <td class="col-name">
                <button v-if="row.preReviewConv" class="cell-link name-link" @click="openConv(row.preReviewConv)">{{ row.name }}</button>
                <span v-else class="req-name">{{ row.name }}</span>
              </td>
              <td class="col-status">
                <el-tag :type="statusTagType(row.preReview)" size="small" :effect="row.preReviewConv ? 'light' : 'plain'" :class="{ 'is-clickable': row.preReviewConv }" @click="row.preReviewConv && openConv(row.preReviewConv)">{{ row.preReview }}</el-tag>
              </td>
              <td class="col-report">
                <button v-if="row.sixDimConv" class="report-link" @click="openConv(row.sixDimConv)"><el-icon :size="14"><Document /></el-icon>{{ row.sixDim }}</button>
                <span v-else class="report-na">{{ row.sixDim === '--' ? '--' : row.sixDim }}</span>
              </td>
              <td class="col-status">
                <el-tag v-if="row.caseReview !== '未开始'" :type="statusTagType(row.caseReview)" size="small" :effect="row.caseReviewConv ? 'light' : 'plain'" :class="{ 'is-clickable': row.caseReviewConv }" @click="row.caseReviewConv && openConv(row.caseReviewConv)">{{ row.caseReview }}</el-tag>
                <span v-else class="report-na">{{ row.caseReview }}</span>
              </td>
              <td class="col-steps">
                <button v-if="row.caseStepsConv && row.caseSteps !== '已生成'" class="cell-link steps-count" @click="openConv(row.caseStepsConv)">{{ row.caseSteps }} 条</button>
                <span v-else-if="row.caseSteps === '已生成'" class="steps-count">已生成</span>
                <span v-else-if="row.caseSteps > 0" class="steps-count">{{ row.caseSteps }} 条</span>
                <span v-else class="report-na">--</span>
              </td>
              <td class="col-actions">
                <button class="delete-btn" title="删除该需求的所有记录" @click="confirmDelete(row)">
                  <el-icon :size="14"><Delete /></el-icon>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>
</template>

<style scoped>
.tracking-page{height:100vh;overflow:hidden;background:radial-gradient(circle at 8% 0,rgba(15,108,189,.08),transparent 27%),var(--el-bg-color-page)}
.tracking-scroll{height:100%;overflow-y:auto}
.tracking-content{max-width:1100px;margin:0 auto;padding:40px 40px 60px}
.back{display:flex;align-items:center;gap:5px;margin:0 0 24px;padding:0;color:var(--el-text-color-secondary);border:0;background:none;cursor:pointer}
.eyebrow{display:block;margin-bottom:5px;color:var(--el-color-primary);font-size:10px;font-weight:800;letter-spacing:.14em}
.title-row{display:flex;align-items:flex-end;justify-content:space-between;gap:30px;margin-bottom:24px}
.title-row h1{margin:0;color:var(--el-text-color-primary);font-size:28px;font-weight:750;letter-spacing:-.7px}
.title-row p{margin:8px 0 0;color:var(--el-text-color-secondary);font-size:13px}
.search-bar{width:280px}
.table-wrapper{border-radius:14px;border:1px solid var(--el-border-color-lighter);background:var(--el-bg-color);overflow:hidden;box-shadow:0 2px 12px rgba(15,23,42,.04)}
.req-table{width:100%;border-collapse:collapse;font-size:14px}
.req-table thead{background:var(--el-fill-color-light)}
.req-table th{padding:14px 18px;text-align:left;font-size:13px;font-weight:700;color:var(--el-text-color-secondary);border-bottom:1px solid var(--el-border-color-lighter);white-space:nowrap}
.req-table td{padding:14px 18px;border-bottom:1px solid var(--el-border-color-extra-light);vertical-align:middle}
.data-row{transition:background .2s}
.data-row:hover{background:var(--el-fill-color-lighter)}
.data-row:last-child td{border-bottom:none}
.col-id{width:120px}
.col-name{min-width:200px}
.col-status{width:100px}
.col-report{width:160px}
.col-steps{width:100px}
.col-actions{width:70px;text-align:center}
.delete-btn{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border:none;border-radius:6px;background:transparent;color:var(--el-text-color-placeholder);cursor:pointer;transition:color .2s,background .2s}
.delete-btn:hover{color:var(--el-color-danger);background:var(--el-color-danger-light-9)}
.req-id{font-size:12px;font-weight:600;color:var(--el-text-color-placeholder);font-family:'SF Mono','Fira Code',monospace}
.req-name{color:var(--el-text-color-primary);font-weight:600}
.report-link{display:inline-flex;align-items:center;gap:6px;border:none;background:transparent;color:var(--el-color-primary);font-size:13px;cursor:pointer;padding:2px 0;font-family:inherit;transition:opacity .2s}
.report-link:hover{opacity:.75}
.cell-link{border:none;background:transparent;padding:0;font-family:inherit;cursor:pointer;transition:opacity .2s}
.cell-link:hover{opacity:.75}
.name-link{color:var(--el-text-color-primary);font-size:14px;font-weight:600;text-align:left}
.steps-count{font-size:13px;font-weight:600;color:var(--el-color-primary)}
.is-clickable{cursor:pointer !important}
.report-na{color:var(--el-text-color-placeholder);font-size:13px}
.empty-row{text-align:center;padding:40px 18px !important;color:var(--el-text-color-placeholder);font-size:14px}
@media(max-width:640px){.tracking-content{padding:24px 16px 40px}.title-row{align-items:flex-start;flex-direction:column}.search-bar{width:100%}}
</style>
