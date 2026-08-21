<script setup>
/**
 * FlowVisualizer — agent5 业务流程可视化（真实关联版，MVP）
 *
 * 数据源（三处一致，契约 §6.2）：
 *   server.py ASSISTANT_NODE_PROGRESS（权威节点名 + 文案）
 *   /Finance_Agent/docs/规范与解释/接口契约总表.md §6.2
 *   本组件 stages 定义（改 agent 图必须同步这三处）
 *
 * 点亮机制（真实，非假定时器）：
 *   - 网关阶段：前端真实动作（请求发出/流开始/流结束）本地状态机
 *   - agent 阶段：SSE progress 事件 data.node 精确匹配 → 点亮当前节点
 *   - completed → 全部完成；error → 当前节点标红
 */
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  active: { type: Boolean, default: false },   // 正在执行（请求已发出）
  node: { type: String, default: '' },          // 当前 SSE progress node
  done: { type: Boolean, default: false },      // completed 到达
  failed: { type: Boolean, default: false },    // error 到达
})

// ===== 阶段定义（对齐 server.py ASSISTANT_NODE_PROGRESS，勿改节点名）=====
const stages = [
  { node: 'intent_recognition', label: '意图识别', detail: '理解你想做什么' },
  { node: 'kb_retrieve',        label: '知识库检索', detail: '查找相关业务知识' },
  { node: 'answer_generate',    label: '生成回答', detail: '组织最终回复' },
  { node: 'transfer_agent',     label: '转交智能体', detail: '交给专业 agent 处理' },
]

// ===== 各阶段状态（computed 驱动）=====
const state = reactive({
  activeIndex: -1,
})

watch(() => props.node, (node) => {
  const idx = stages.findIndex(s => s.node === node)
  if (idx >= 0) state.activeIndex = idx
}, { immediate: true })

const stageState = (index) => {
  if (props.failed && index === state.activeIndex) return 'failed'
  if (props.done) return 'done'
  if (props.active && index === state.activeIndex) return 'active'
  if (index < state.activeIndex) return 'done'
  return 'waiting'
}

const percent = computed(() => {
  if (props.done) return 100
  if (props.active && state.activeIndex >= 0) {
    return Math.round(((state.activeIndex + 1) / stages.length) * 100)
  }
  return 0
})
</script>

<template>
  <div class="fv-wrap">
    <div class="fv-head">
      <span class="fv-title">处理流程</span>
      <span class="fv-percent">{{ done ? '✓ 完成' : failed ? '失败' : percent + '%' }}</span>
    </div>
    <div class="fv-bar"><div class="fv-bar-fill" :style="{ width: percent + '%' }"></div></div>
    <div class="fv-stages">
      <div v-for="(s, i) in stages" :key="s.node"
           :class="['fv-stage', stageState(i)]">
        <span class="fv-dot"></span>
        <span class="fv-label">{{ s.label }}</span>
        <span class="fv-detail">{{ s.detail }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fv-wrap {
  background: #f6f8fa;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 4px;
  font-size: 12px;
}
.fv-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.fv-title { font-weight: 600; color: #333; }
.fv-percent { color: #888; font-variant-numeric: tabular-nums; }
.fv-bar {
  height: 4px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 8px;
}
.fv-bar-fill {
  height: 100%;
  background: #409eff;
  border-radius: 2px;
  transition: width .3s ease;
}
.fv-stages { display: flex; flex-direction: column; gap: 6px; }
.fv-stage {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #999;
  transition: color .2s;
}
.fv-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #d1d5db;
  flex-shrink: 0;
  transition: background .2s;
}
.fv-stage.active { color: #409eff; font-weight: 600; }
.fv-stage.active .fv-dot { background: #409eff; box-shadow: 0 0 0 3px rgba(64,158,255,.2); }
.fv-stage.done { color: #67c23a; }
.fv-stage.done .fv-dot { background: #67c23a; }
.fv-stage.failed { color: #f56c6c; }
.fv-stage.failed .fv-dot { background: #f56c6c; }
.fv-label { flex-shrink: 0; }
.fv-detail { color: #bbb; font-size: 11px; }
</style>
