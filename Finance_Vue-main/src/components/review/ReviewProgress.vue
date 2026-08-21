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
  { node:'requirement_parser', label:'解析需求', detail:'识别范围与约束' },
  { node:'keyword_extractor', label:'提取关键词', detail:'提炼业务与测试要点' },
  { node:'kb_router', label:'路由知识库', detail:'选择关联知识域' },
  { node:'knowledge_retrieval', label:'检索知识', detail:'召回规则与历史案例' },
  { node:'six_points_eval', label:'六维评估', detail:'检查需求完整性' },
  { node:'risk_assessment', label:'风险分析', detail:'识别业务与合规风险' },
  { node:'report_generator', label:'生成报告', detail:'汇总评审结论' }
]

const elapsed = ref(0)
let timer
watch(() => props.loading, (value) => {
  clearInterval(timer)
  if (value) {
    elapsed.value = 0
    timer = setInterval(() => elapsed.value += 1, 1000)
  }
}, { immediate:true })
onUnmounted(() => clearInterval(timer))

const activeIndex = computed(() => {
  if (props.hasReport) return stages.length
  const index = stages.findIndex(stage => stage.node === props.node)
  return index >= 0 ? index : 0
})
const percent = computed(() => {
  if (props.hasReport) return 100
  return Math.max(4, Math.round((activeIndex.value / stages.length) * 100))
})
const stageState = (index) => {
  if (props.failed && index === activeIndex.value) return 'failed'
  if (props.hasReport || index < activeIndex.value) return 'done'
  if (props.loading && index === activeIndex.value) return 'active'
  return 'waiting'
}
</script>

<template>
  <section class="progress-card" :class="{ 'is-failed': failed }">
    <div class="progress-topline">
      <div>
        <span class="eyebrow">评审流程</span>
        <h3>{{ failed ? '流程执行失败' : hasReport ? '预评审已完成' : loading ? (status || '正在启动评审流程...') : '等待开始' }}</h3>
      </div>
      <div class="progress-meta">
        <span v-if="loading">已用时 {{ elapsed }} 秒</span>
        <strong>{{ percent }}%</strong>
      </div>
    </div>
    <el-progress :percentage="percent" :show-text="false" :status="failed ? 'exception' : hasReport ? 'success' : undefined" />
    <div class="stage-grid">
      <div v-for="(stage,index) in stages" :key="stage.node" class="stage" :class="`is-${stageState(index)}`">
        <div class="stage-marker">
          <el-icon v-if="stageState(index)==='done'"><Check /></el-icon>
          <el-icon v-else-if="stageState(index)==='failed'"><Close /></el-icon>
          <span v-else>{{ index + 1 }}</span>
        </div>
        <div class="stage-copy"><strong>{{ stage.label }}</strong><span>{{ stage.detail }}</span></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.progress-card { padding:22px 24px; border:1px solid var(--el-border-color-lighter); border-radius:16px; background:var(--el-bg-color); box-shadow:0 8px 28px rgba(15,23,42,.045) }
.progress-topline { display:flex; align-items:flex-end; justify-content:space-between; gap:20px; margin-bottom:16px }
.eyebrow { display:block; margin-bottom:4px; color:var(--el-text-color-secondary); font-size:12px; font-weight:600; letter-spacing:.08em }
h3 { margin:0; color:var(--el-text-color-primary); font-size:16px }
.progress-meta { display:flex; align-items:center; gap:14px; color:var(--el-text-color-secondary); font-size:12px }
.progress-meta strong { color:var(--el-color-primary); font-size:18px }
.stage-grid { display:grid; grid-template-columns:repeat(7,minmax(94px,1fr)); gap:10px; margin-top:22px }
.stage { min-width:0; padding:12px 10px; border:1px solid var(--el-border-color-extra-light); border-radius:12px; background:var(--el-fill-color-extra-light); transition:.2s ease }
.stage-marker { display:grid; width:26px; height:26px; margin-bottom:9px; color:var(--el-text-color-placeholder); border:1px solid var(--el-border-color); border-radius:50%; background:var(--el-bg-color); font-size:11px; place-items:center }
.stage-copy { display:flex; flex-direction:column; gap:4px }
.stage-copy strong { color:var(--el-text-color-regular); font-size:12px }
.stage-copy span { color:var(--el-text-color-placeholder); font-size:10px; line-height:1.45 }
.stage.is-active { border-color:var(--el-color-primary-light-5); background:var(--el-color-primary-light-9); box-shadow:0 6px 18px rgba(15,108,189,.1) }
.stage.is-active .stage-marker { color:#fff; border-color:var(--el-color-primary); background:var(--el-color-primary); animation:pulse 1.5s infinite }
.stage.is-done .stage-marker { color:#fff; border-color:var(--el-color-success); background:var(--el-color-success) }
.stage.is-failed { border-color:var(--el-color-danger-light-5); background:var(--el-color-danger-light-9) }
.stage.is-failed .stage-marker { color:#fff; border-color:var(--el-color-danger); background:var(--el-color-danger) }
@keyframes pulse { 50% { box-shadow:0 0 0 6px rgba(15,108,189,.12) } }
@media (max-width:1100px) { .stage-grid { grid-template-columns:repeat(4,1fr) } }
@media (max-width:720px) { .progress-card { padding:18px } .progress-topline { align-items:flex-start; flex-direction:column } .stage-grid { grid-template-columns:repeat(2,1fr) } }
</style>
