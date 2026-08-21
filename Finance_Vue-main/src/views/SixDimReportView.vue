<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'
import { renderMarkdown } from '@/composables/useMarkdown'
import { downloadReport } from '@/utils/downloadReport'

const route = useRoute()
const router = useRouter()
const agentStore = useAgentStore()

const AGENT_ID = 'ai-test-analysis'
const conversationId = computed(() => route.query.conversationId || '')
const reportTitle = computed(() => route.query.title || '六维测试分析报告')
const wordCount = computed(() => reportContent.value?.length || 0)

const loading = ref(true)
const error = ref('')
const reportContent = ref('')

const reportMessage = computed(() => {
  if (!reportContent.value) return null
  return { content: reportContent.value }
})

function handleDownload() {
  const filename = `六维测试分析报告-${new Date().toISOString().slice(0, 10)}.md`
  downloadReport(reportContent.value, filename)
}

onMounted(async () => {
  if (!conversationId.value) {
    error.value = '缺少会话 ID，无法加载报告'
    loading.value = false
    return
  }
  try {
    await agentStore.syncRemoteConversations(AGENT_ID)
    const sessions = agentStore.conversations[AGENT_ID]?.sessions || {}
    const session = sessions[conversationId.value]
    if (!session) {
      error.value = '未找到该需求的六维分析会话'
      loading.value = false
      return
    }
    if (!session.messagesLoaded) {
      await agentStore.loadRemoteMessages(AGENT_ID, conversationId.value)
    }
    // 取已有的六维分析报告：已生成的长 assistant 消息
    const msgs = session.messages || []
    const report = [...msgs].reverse().find(m =>
      m.role === 'assistant'
      && typeof m.content === 'string'
      && m.content.length > 100
      && !m.content.startsWith('你好，我是')
    )
    if (report) {
      reportContent.value = report.content
    } else {
      error.value = '该会话暂未生成六维分析报告'
    }
  } catch (e) {
    error.value = '加载报告失败：' + (e.message || '网络错误')
  }
  loading.value = false
})
</script>

<template>
  <div class="six-dim-view">
    <main class="six-dim-scroll">
      <div class="six-dim-container">
        <!-- 页面标题 -->
        <div class="six-dim-intro">
          <div>
            <span>REPORT VIEWER</span>
            <h1>{{ reportTitle }}</h1>
          </div>
          <el-button @click="router.push('/')">返回首页</el-button>
        </div>

        <!-- 加载状态 -->
        <div v-if="loading" class="loading-state">
          <el-icon :size="28" class="is-loading"><Loading /></el-icon>
          <span>正在加载六维分析报告…</span>
        </div>

        <!-- 错误状态 -->
        <div v-else-if="error" class="error-state">
          <el-icon :size="30"><WarningFilled /></el-icon>
          <strong>{{ error }}</strong>
          <el-button @click="router.push('/')">返回首页</el-button>
        </div>

        <!-- 报告卡片 -->
        <section v-else-if="reportMessage" class="analysis-report">
          <header>
            <div class="heading">
              <div class="icon"><el-icon><DataAnalysis /></el-icon></div>
              <div><span>AI TEST ANALYSIS REPORT</span><h2>六维测试分析报告</h2></div>
            </div>
            <div class="complete"><el-icon><CircleCheckFilled /></el-icon>分析完成</div>
          </header>
          <div class="meta">
            <span><el-icon><Document /></el-icon>{{ wordCount }} 字</span>
            <span><el-icon><Connection /></el-icon>业务 · 功能 · 数据 · 接口 · 性能 · 安全</span>
            <span><el-icon><FolderChecked /></el-icon>已归档查看</span>
          </div>
          <article class="report-body markdown-body" v-html="renderMarkdown(reportContent)" />
          <footer>
            <span class="hint"><el-icon><InfoFilled /></el-icon>报告仅用于查看历史分析结论</span>
            <div class="actions">
              <el-button type="primary" @click="handleDownload">
                <el-icon><Download /></el-icon>下载报告
              </el-button>
            </div>
          </footer>
        </section>

        <!-- 无报告 -->
        <div v-else class="empty-state">
          <el-icon :size="30"><Document /></el-icon>
          <strong>未找到报告内容</strong>
          <span>该会话暂未包含有效的六维分析报告。</span>
          <el-button @click="router.push('/')">返回首页</el-button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.six-dim-view { height:100vh; background: var(--el-bg-color-page) }
.six-dim-scroll { height:100%; overflow-y:auto; background: radial-gradient(circle at 12% 0, rgba(114,87,217,.1), transparent 34%), radial-gradient(circle at 90% 12%, rgba(61,144,214,.06), transparent 27%), var(--el-bg-color-page) }
.six-dim-container { display:flex; flex-direction:column; gap:18px; width:min(960px, calc(100% - 48px)); margin:0 auto; padding:30px 0 56px }

.six-dim-intro { display:flex; align-items:flex-end; justify-content:space-between; gap:28px; padding:4px 2px 2px }
.six-dim-intro span { color:#7257d9; font-size:10px; font-weight:800; letter-spacing:.15em }
.six-dim-intro h1 { margin:5px 0 0; color:var(--el-text-color-primary); font-size:26px; line-height:1.25 }

.loading-state,.error-state,.empty-state { display:flex; min-height:200px; align-items:center; justify-content:center; flex-direction:column; gap:12px; color:var(--el-text-color-placeholder); border:1px dashed var(--el-border-color); border-radius:16px; background:var(--el-bg-color) }
.error-state { color:var(--el-color-danger); border-color:var(--el-color-danger-light-7) }
.error-state strong { color:var(--el-text-color-secondary) }
.empty-state strong { color:var(--el-text-color-secondary) }

/* — 报告卡片样式（复用 AnalysisReportCard 视觉效果） — */
.analysis-report { overflow:hidden; border:1px solid #cfc5f5; border-radius:18px; background:var(--el-bg-color); box-shadow:0 16px 44px rgba(72,52,150,.09) }
.analysis-report header { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:22px 26px; border-bottom:1px solid var(--el-border-color-extra-light); background:linear-gradient(120deg,#f2efff,var(--el-bg-color) 58%) }
.heading { display:flex; align-items:center; gap:13px }
.heading span { display:block; margin-bottom:3px; color:#7257d9; font-size:10px; font-weight:800; letter-spacing:.12em }
.heading h2 { margin:0; color:var(--el-text-color-primary); font-size:20px }
.icon { display:grid; width:44px; height:44px; color:#fff; border-radius:13px; background:linear-gradient(135deg,#7257d9,#438bd3); box-shadow:0 8px 20px rgba(90,68,180,.25); place-items:center }
.complete { display:flex; align-items:center; gap:6px; padding:7px 12px; color:var(--el-color-success); border-radius:999px; background:var(--el-color-success-light-9); font-size:12px; font-weight:700 }
.meta { display:flex; flex-wrap:wrap; gap:20px; padding:13px 26px; color:var(--el-text-color-secondary); border-bottom:1px solid var(--el-border-color-extra-light); background:var(--el-fill-color-extra-light); font-size:12px }
.meta span { display:inline-flex; align-items:center; gap:6px }
.report-body { max-width:860px; min-height:260px; margin:0 auto; padding:34px 38px 44px; color:var(--el-text-color-regular); font-size:15px; line-height:1.75 }
.report-body :deep(h1) { margin:0 0 22px; font-size:27px }
.report-body :deep(h2) { margin:30px 0 14px; padding-bottom:8px; border-bottom:1px solid var(--el-border-color-lighter); font-size:20px }
.report-body :deep(h3) { margin:22px 0 10px; font-size:17px }
.report-body :deep(table) { width:100%; margin:18px 0; border-collapse:collapse; font-size:13px }
.report-body :deep(th),.report-body :deep(td) { padding:9px 11px; border:1px solid var(--el-border-color-lighter); text-align:left }
.report-body :deep(th) { background:var(--el-fill-color-light) }
.analysis-report footer { position:sticky; bottom:0; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:16px 22px; border-top:1px solid var(--el-border-color-lighter); background:color-mix(in srgb,var(--el-bg-color) 94%,transparent); backdrop-filter:blur(10px) }
.hint { color:var(--el-text-color-secondary); font-size:12px; display:inline-flex; align-items:center; gap:6px }
.actions { display:flex; gap:8px }
@media (max-width:720px) { .six-dim-container { width:calc(100% - 24px); padding:18px 0 36px } .six-dim-intro { align-items:flex-start; flex-direction:column } .analysis-report footer { align-items:flex-start; flex-direction:column } .report-body { padding:24px 20px 32px } }
</style>
