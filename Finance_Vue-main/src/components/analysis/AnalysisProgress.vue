<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  loading: { type: Boolean, default: false },
  node: { type: String, default: '' },
  status: { type: String, default: '' },
  hasReport: { type: Boolean, default: false },
  failed: { type: Boolean, default: false }
})

const stages = [
  { node:'extract_keywords', label:'需求理解', detail:'提取业务、测试与监管关键词' },
  { node:'retrieve_all', label:'知识检索', detail:'并行检索业务、规范和法规知识库' },
  { node:'rag_response', label:'六维分析', detail:'生成结构化测试分析报告' }
]

const elapsed = ref(0)
let timer
watch(() => props.loading, value => {
  clearInterval(timer)
  if (value) {
    elapsed.value = 0
    timer = setInterval(() => elapsed.value += 1, 1000)
  }
}, { immediate:true })
onUnmounted(() => clearInterval(timer))

const activeIndex = computed(() => {
  if (props.hasReport) return stages.length
  if (props.node === 'chat_response') return 2
  const index = stages.findIndex(stage => stage.node === props.node)
  return index >= 0 ? index : 0
})
const percent = computed(() => props.hasReport
  ? 100
  : Math.max(6, Math.round((activeIndex.value / stages.length) * 100))
)
const stateOf = index => {
  if (props.failed && index === activeIndex.value) return 'failed'
  if (props.hasReport || index < activeIndex.value) return 'done'
  if (props.loading && index === activeIndex.value) return 'active'
  return 'waiting'
}
</script>

<template>
  <section class="analysis-progress" :class="{ 'is-failed': failed }">
    <div class="progress-heading">
      <div><span class="eyebrow">AGENT 2 · TEST ANALYSIS</span><h3>{{ failed ? '六维分析执行失败' : hasReport ? '六维分析已完成' : loading ? (status || '正在启动六维分析智能体...') : '等待开始' }}</h3></div>
      <div class="progress-meta"><span v-if="loading">已用时 {{ elapsed }} 秒</span><strong>{{ percent }}%</strong></div>
    </div>
    <el-progress :percentage="percent" :show-text="false" :status="failed ? 'exception' : hasReport ? 'success' : undefined" />
    <div class="stage-list">
      <div v-for="(stage,index) in stages" :key="stage.node" class="stage" :class="`is-${stateOf(index)}`">
        <div class="stage-number"><el-icon v-if="stateOf(index)==='done'"><Check /></el-icon><el-icon v-else-if="stateOf(index)==='failed'"><Close /></el-icon><span v-else>0{{ index + 1 }}</span></div>
        <div><strong>{{ stage.label }}</strong><p>{{ stage.detail }}</p></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.analysis-progress{padding:24px;border:1px solid var(--el-border-color-lighter);border-radius:18px;background:var(--el-bg-color);box-shadow:0 10px 30px rgba(15,23,42,.05)}
.progress-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:17px}.eyebrow{display:block;margin-bottom:5px;color:#7257d9;font-size:10px;font-weight:800;letter-spacing:.14em}h3{margin:0;color:var(--el-text-color-primary);font-size:17px}.progress-meta{display:flex;align-items:center;gap:14px;color:var(--el-text-color-secondary);font-size:12px}.progress-meta strong{color:#7257d9;font-size:20px}
.stage-list{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:24px}.stage{display:flex;gap:13px;padding:16px;border:1px solid var(--el-border-color-extra-light);border-radius:14px;background:var(--el-fill-color-extra-light)}.stage-number{display:grid;width:32px;height:32px;flex:none;color:var(--el-text-color-placeholder);border:1px solid var(--el-border-color);border-radius:10px;background:var(--el-bg-color);font-size:11px;font-weight:800;place-items:center}.stage strong{color:var(--el-text-color-regular);font-size:13px}.stage p{margin:5px 0 0;color:var(--el-text-color-placeholder);font-size:11px;line-height:1.5}.stage.is-active{border-color:#a999e8;background:#f4f1ff}.stage.is-active .stage-number{color:#fff;border-color:#7257d9;background:#7257d9;animation:pulse 1.5s infinite}.stage.is-done .stage-number{color:#fff;border-color:var(--el-color-success);background:var(--el-color-success)}.stage.is-failed{border-color:var(--el-color-danger-light-5);background:var(--el-color-danger-light-9)}.stage.is-failed .stage-number{color:#fff;background:var(--el-color-danger)}
@keyframes pulse{50%{box-shadow:0 0 0 6px rgba(114,87,217,.13)}}@media(max-width:720px){.progress-heading{align-items:flex-start;flex-direction:column}.stage-list{grid-template-columns:1fr}}
</style>
