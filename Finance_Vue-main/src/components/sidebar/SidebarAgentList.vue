<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'

const router = useRouter()
const agentStore = useAgentStore()
const items = [
  { id:'req', label:'需求流程', icon:'Memo', path:'/chat/requirement-pre-review' },
  { id:'tc', label:'测试用例流程', icon:'DocumentCopy', path:'/test-case/write' }
]
const isMain = computed(() => router.currentRoute.value.path === '/')
const isTracking = computed(() => router.currentRoute.value.path === '/requirement-tracking')
const isGraph = computed(() => router.currentRoute.value.path === '/knowledge-graph')
const active = computed(() => {
  const p = router.currentRoute.value.path
  if(p.includes('requirement-pre-review')||p.includes('ai-test-analysis')) return 'req'
  if(p.includes('/test-case/')) return 'tc'
  return null
})

// —— 需求追踪侧边列表：与需求追踪表格同一数据源（store.requirementRows），按更新时间倒序 ——
const trackingRows = computed(() => agentStore.requirementRows)

// 按钮文案：取需求名称前 10 个字；超出部分以 '...' 替代，不足部分以空白补齐
function shortLabel(name) {
  if (name.length > 10) return name.slice(0, 10) + '...'
  return name.padEnd(10, ' ')
}

function openRequirement(row) {
  // 进入对应状态界面：打开该需求最近活跃的真实会话（当前阶段所在的 agent，
  // 如待审批 → 预评审待审批界面；已进入六维/用例/步骤阶段 → 对应 agent 的会话）。
  // 无真实会话（仅本地临时记录）时回退到需求追踪页。
  const conv = row.latestConv
  if (conv?.conversationId) {
    agentStore.setActiveAgent(conv.agentId, conv.conversationId)
    agentStore.requestFocus()
    router.push({ path: `/chat/${conv.agentId}`, query: { conversationId: conv.conversationId } })
  } else {
    router.push('/requirement-tracking')
  }
}
</script>
<template>
<div class="agent-list-section">
  <nav class="agent-nav main-nav">
    <router-link to="/" :class="['wf-btn',{active:isMain}]">
      <el-icon :size="18"><component :is="'HomeFilled'"/></el-icon>
      <span class="wf-label">主界面</span>
    </router-link>
  </nav>
  <div class="section-label">工作流</div>
  <nav class="agent-nav">
    <router-link v-for="it in items" :key="it.id" :to="it.path" :class="['wf-btn',{active:active===it.id}]">
      <el-icon :size="18"><component :is="it.icon"/></el-icon>
      <span class="wf-label">{{it.label}}</span>
    </router-link>
  </nav>
  <nav class="agent-nav tracking-nav">
    <router-link to="/knowledge-graph" :class="['wf-btn',{active:isGraph}]">
      <el-icon :size="18"><component :is="'Share'"/></el-icon>
      <span class="wf-label">知识图谱</span>
    </router-link>
    <router-link to="/requirement-tracking" :class="['wf-btn',{active:isTracking}]">
      <el-icon :size="18"><component :is="'List'"/></el-icon>
      <span class="wf-label">需求追踪</span>
    </router-link>
    <div v-if="trackingRows.length" class="tracking-list sidebar-scrollbar">
      <button
        v-for="row in trackingRows"
        :key="row.name"
        class="tracking-item"
        :title="row.name"
        @click="openRequirement(row)"
      >{{ shortLabel(row.name) }}</button>
    </div>
  </nav>
</div>
</template>
<style scoped>
.agent-list-section{padding:0 12px;flex-shrink:0}
.main-nav{margin:2px 0 10px}
.tracking-nav{margin-top:10px;padding-top:10px;border-top:1px solid var(--sidebar-border)}
.section-label{padding:8px 16px 4px;color:var(--sidebar-text-muted);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.agent-nav{display:flex;flex-direction:column;gap:4px}
.wf-btn{display:flex;align-items:center;gap:12px;padding:12px 14px;border-radius:10px;text-decoration:none;color:var(--sidebar-text);transition:background .15s}
.wf-btn:hover{background:var(--sidebar-hover-bg)}
.wf-btn.active{background:var(--sidebar-active-bg);color:var(--el-color-primary)}
.wf-label{font-size:14px;font-weight:600}
.tracking-list{display:flex;flex-direction:column;gap:2px;max-height:170px;overflow-y:auto;margin-top:2px}
.tracking-item{flex:0 0 auto;width:100%;padding:6px 14px;border:none;border-radius:8px;background:transparent;color:var(--sidebar-text);font-size:12px;font-family:inherit;text-align:left;cursor:pointer;white-space:pre;overflow:hidden;transition:background .15s}
.tracking-item:hover{background:var(--sidebar-hover-bg)}
</style>
