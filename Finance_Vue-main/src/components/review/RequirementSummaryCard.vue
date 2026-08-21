<script setup>
defineProps({
  title: { type: String, default: '待评审需求' },
  content: { type: String, default: '' },
  files: { type: Array, default: () => [] },
  stageLabel: { type: String, default: '预评审输入' },
  stageType: { type: String, default: 'info' }
})
</script>

<template>
  <section class="summary-card">
    <div class="summary-heading">
      <div class="summary-icon"><el-icon><Document /></el-icon></div>
      <div>
        <span class="eyebrow">需求摘要</span>
        <h2>{{ title || '待评审需求' }}</h2>
      </div>
      <el-tag :type="stageType" effect="plain" round>{{ stageLabel }}</el-tag>
    </div>
    <p class="summary-content">{{ content || '尚未提交需求内容。' }}</p>
    <div v-if="files.length" class="summary-files">
      <span v-for="file in files" :key="file.name" class="file-chip">
        <el-icon><Paperclip /></el-icon>{{ file.name }}
      </span>
    </div>
  </section>
</template>

<style scoped>
.summary-card { padding:22px 24px; border:1px solid var(--el-border-color-lighter); border-radius:16px; background:var(--el-bg-color); box-shadow:0 8px 28px rgba(15,23,42,.045) }
.summary-heading { display:flex; align-items:center; gap:12px }
.summary-heading > div:nth-child(2) { min-width:0; flex:1 }
.summary-icon { display:grid; width:42px; height:42px; color:var(--el-color-primary); border-radius:12px; background:var(--el-color-primary-light-9); place-items:center }
.eyebrow { display:block; margin-bottom:3px; color:var(--el-text-color-secondary); font-size:12px; font-weight:600; letter-spacing:.08em }
h2 { overflow:hidden; margin:0; color:var(--el-text-color-primary); font-size:18px; text-overflow:ellipsis; white-space:nowrap }
.summary-content { margin:18px 0 0; color:var(--el-text-color-regular); font-size:14px; line-height:1.8; white-space:pre-wrap }
.summary-files { display:flex; flex-wrap:wrap; gap:8px; margin-top:16px }
.file-chip { display:inline-flex; align-items:center; gap:5px; padding:6px 10px; color:var(--el-text-color-secondary); border-radius:8px; background:var(--el-fill-color-light); font-size:12px }
@media (max-width:720px) { .summary-card { padding:18px } .summary-heading .el-tag { display:none } }
</style>
