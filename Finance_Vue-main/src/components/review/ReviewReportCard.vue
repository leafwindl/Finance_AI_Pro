<script setup>
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { renderMarkdown } from '@/composables/useMarkdown'

const props = defineProps({
  message: { type: Object, default: null }
})
const emit = defineEmits(['approve','reject','download','viewSixDim'])

const status = computed(() => props.message?.approved === true ? 'passed' : props.message?.approved === false ? 'rejected' : 'pending')
const canDecide = computed(() => Boolean(
  props.message?.approvalId && props.message?.messageId && props.message?.conversationId
  && props.message?.approved == null
))
const statusLabel = computed(() => status.value === 'passed'
  ? '已通过'
  : status.value === 'rejected' ? '已驳回' : canDecide.value ? '待审批' : '历史报告'
)
const wordCount = computed(() => props.message?.content?.length || 0)

async function requestReject() {
  try {
    const { value } = await ElMessageBox.prompt('请填写驳回原因，便于后续修改需求。', '驳回预评审报告', {
      confirmButtonText:'确认驳回', cancelButtonText:'取消', inputType:'textarea',
      inputValidator:value => value?.trim() ? true : '请输入驳回原因'
    })
    emit('reject', props.message, value.trim())
  } catch { /* cancelled */ }
}
</script>

<template>
  <section v-if="message" class="report-card" :class="`is-${status}`">
    <header class="report-header">
      <div class="report-heading">
        <div class="report-icon"><el-icon><Tickets /></el-icon></div>
        <div><span class="eyebrow">AI REVIEW REPORT</span><h2>需求预评审报告</h2></div>
      </div>
      <span class="status-pill" :class="`is-${status}`">{{ statusLabel }}</span>
    </header>
    <div class="report-meta">
      <span><el-icon><Document /></el-icon>{{ wordCount }} 字</span>
      <span><el-icon><Clock /></el-icon>报告已生成</span>
      <span><el-icon><CircleCheck /></el-icon>{{ canDecide ? '等待人工决策' : '已归档' }}</span>
      <span v-if="message.decidedAt"><el-icon><Clock /></el-icon>{{ new Date(message.decidedAt).toLocaleString('zh-CN') }}</span>
      <span v-if="message.rejectionReason">驳回原因：{{ message.rejectionReason }}</span>
    </div>
    <article class="report-body markdown-body" v-html="renderMarkdown(message.content)"></article>
    <footer class="report-actions">
      <div class="decision-hint"><el-icon><InfoFilled /></el-icon>{{ canDecide ? '请确认报告结论后执行审批操作' : '历史报告仅供查看和下载' }}</div>
      <div class="action-buttons">
        <el-button v-if="status === 'passed'" type="primary" plain @click="emit('viewSixDim')"><el-icon><DataAnalysis /></el-icon>查看六维分析</el-button>
        <el-button @click="emit('download', message)"><el-icon><Download /></el-icon>下载报告</el-button>
        <template v-if="canDecide && status === 'pending'">
          <el-button type="danger" plain @click="requestReject"><el-icon><Close /></el-icon>驳回</el-button>
          <el-button type="success" @click="emit('approve', message)"><el-icon><Check /></el-icon>通过并继续</el-button>
        </template>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.report-card { overflow:hidden; border:1px solid var(--el-color-primary-light-7); border-radius:18px; background:var(--el-bg-color); box-shadow:0 14px 42px rgba(15,23,42,.07) }
.report-card.is-passed { border-color:var(--el-color-success-light-5) }
.report-card.is-rejected { border-color:var(--el-color-danger-light-5) }
.report-header { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:22px 26px; border-bottom:1px solid var(--el-border-color-extra-light); background:linear-gradient(120deg,var(--el-color-primary-light-9),var(--el-bg-color) 55%) }
.report-heading { display:flex; align-items:center; gap:13px }
.report-icon { display:grid; width:44px; height:44px; color:#fff; border-radius:13px; background:linear-gradient(135deg,var(--el-color-primary),#3d90d6); box-shadow:0 8px 20px rgba(15,108,189,.22); place-items:center }
.eyebrow { display:block; margin-bottom:3px; color:var(--el-color-primary); font-size:10px; font-weight:800; letter-spacing:.12em }
h2 { margin:0; color:var(--el-text-color-primary); font-size:20px }
.status-pill { padding:6px 12px; color:var(--el-color-warning); border-radius:999px; background:var(--el-color-warning-light-9); font-size:12px; font-weight:700 }
.status-pill.is-passed { color:var(--el-color-success); background:var(--el-color-success-light-9) }
.status-pill.is-rejected { color:var(--el-color-danger); background:var(--el-color-danger-light-9) }
.report-meta { display:flex; flex-wrap:wrap; gap:20px; padding:13px 26px; color:var(--el-text-color-secondary); border-bottom:1px solid var(--el-border-color-extra-light); background:var(--el-fill-color-extra-light); font-size:12px }
.report-meta span { display:inline-flex; align-items:center; gap:6px }
.report-body { max-width:880px; min-height:240px; margin:0 auto; padding:34px 38px 42px; color:var(--el-text-color-regular); font-size:15px; line-height:1.75 }
.report-body :deep(h1) { margin:0 0 22px; color:var(--el-text-color-primary); font-size:26px; line-height:1.3 }
.report-body :deep(h2) { margin:30px 0 14px; padding-bottom:8px; color:var(--el-text-color-primary); border-bottom:1px solid var(--el-border-color-lighter); font-size:20px }
.report-body :deep(h3) { margin:22px 0 10px; color:var(--el-text-color-primary); font-size:17px }
.report-body :deep(p), .report-body :deep(ul), .report-body :deep(ol) { margin:10px 0 }
.report-body :deep(table) { width:100%; margin:18px 0; border-collapse:collapse; font-size:13px }
.report-body :deep(th), .report-body :deep(td) { padding:9px 11px; border:1px solid var(--el-border-color-lighter); text-align:left }
.report-body :deep(th) { background:var(--el-fill-color-light) }
.report-body :deep(blockquote) { margin:16px 0; padding:12px 16px; color:var(--el-text-color-secondary); border-left:3px solid var(--el-color-warning); background:var(--el-color-warning-light-9) }
.report-actions { position:sticky; bottom:0; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:16px 22px; border-top:1px solid var(--el-border-color-lighter); background:color-mix(in srgb,var(--el-bg-color) 94%,transparent); backdrop-filter:blur(10px) }
.decision-hint { display:flex; align-items:center; gap:7px; color:var(--el-text-color-secondary); font-size:12px }
.action-buttons { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px }
@media (max-width:720px) { .report-header,.report-actions { align-items:flex-start; flex-direction:column } .report-meta { gap:10px } .report-body { padding:24px 20px 32px } .action-buttons { width:100% } .action-buttons .el-button { flex:1; margin-left:0 } }
</style>
