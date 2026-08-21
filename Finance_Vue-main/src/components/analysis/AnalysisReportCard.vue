<script setup>
import { renderMarkdown } from '@/composables/useMarkdown'

defineProps({ message: { type:Object, default:null }, hideNext: { type: Boolean, default: false } })
const emit = defineEmits(['download','home','next'])
</script>

<template>
  <section v-if="message" class="analysis-report">
    <header>
      <div class="heading"><div class="icon"><el-icon><DataAnalysis /></el-icon></div><div><span>AI TEST ANALYSIS REPORT</span><h2>六维测试分析报告</h2></div></div>
      <div class="complete"><el-icon><CircleCheckFilled /></el-icon>分析完成</div>
    </header>
    <div class="meta"><span><el-icon><Document /></el-icon>{{ message.content?.length || 0 }} 字</span><span><el-icon><Connection /></el-icon>业务 · 功能 · 数据 · 接口 · 性能 · 安全</span><span><el-icon><FolderChecked /></el-icon>数据库已归档</span></div>
    <article class="report-body markdown-body" v-html="renderMarkdown(message.content)"></article>
    <footer>
      <span class="hint"><el-icon><InfoFilled /></el-icon>报告已生成，可下载归档或继续进入测试流程</span>
      <div class="actions"><el-button @click="emit('home')">返回首页</el-button><el-button @click="emit('download',message)"><el-icon><Download /></el-icon>下载报告</el-button><el-button v-if="!hideNext" type="primary" @click="emit('next',message)">进入测试流程<el-icon><Right /></el-icon></el-button></div>
    </footer>
  </section>
</template>

<style scoped>
.analysis-report{overflow:hidden;border:1px solid #cfc5f5;border-radius:18px;background:var(--el-bg-color);box-shadow:0 16px 44px rgba(72,52,150,.09)}header{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:22px 26px;border-bottom:1px solid var(--el-border-color-extra-light);background:linear-gradient(120deg,#f2efff,var(--el-bg-color) 58%)}.heading{display:flex;align-items:center;gap:13px}.heading span{display:block;margin-bottom:3px;color:#7257d9;font-size:10px;font-weight:800;letter-spacing:.12em}.heading h2{margin:0;color:var(--el-text-color-primary);font-size:20px}.icon{display:grid;width:44px;height:44px;color:#fff;border-radius:13px;background:linear-gradient(135deg,#7257d9,#438bd3);box-shadow:0 8px 20px rgba(90,68,180,.25);place-items:center}.complete{display:flex;align-items:center;gap:6px;padding:7px 12px;color:var(--el-color-success);border-radius:999px;background:var(--el-color-success-light-9);font-size:12px;font-weight:700}.meta{display:flex;flex-wrap:wrap;gap:20px;padding:13px 26px;color:var(--el-text-color-secondary);border-bottom:1px solid var(--el-border-color-extra-light);background:var(--el-fill-color-extra-light);font-size:12px}.meta span,.hint{display:inline-flex;align-items:center;gap:6px}.report-body{max-width:900px;min-height:260px;margin:0 auto;padding:34px 38px 44px;color:var(--el-text-color-regular);font-size:15px;line-height:1.75}.report-body :deep(h1){margin:0 0 22px;font-size:27px}.report-body :deep(h2){margin:30px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--el-border-color-lighter);font-size:20px}.report-body :deep(h3){margin:22px 0 10px;font-size:17px}.report-body :deep(table){width:100%;margin:18px 0;border-collapse:collapse;font-size:13px}.report-body :deep(th),.report-body :deep(td){padding:9px 11px;border:1px solid var(--el-border-color-lighter);text-align:left}.report-body :deep(th){background:var(--el-fill-color-light)}footer{position:sticky;bottom:0;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:16px 22px;border-top:1px solid var(--el-border-color-lighter);background:color-mix(in srgb,var(--el-bg-color) 94%,transparent);backdrop-filter:blur(10px)}.hint{color:var(--el-text-color-secondary);font-size:12px}.actions{display:flex;gap:8px}@media(max-width:720px){header,footer{align-items:flex-start;flex-direction:column}.report-body{padding:24px 20px 32px}.actions{width:100%;flex-wrap:wrap}.actions .el-button{flex:1;margin-left:0}}
</style>
