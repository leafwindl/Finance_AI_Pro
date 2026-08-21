<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/composables/useMarkdown'

const props = defineProps({
  doc: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['back', 'show-files', 'retry'])

const charsLabel = computed(() => {
  const chars = Number(props.doc?.chars)
  return Number.isFinite(chars) && chars > 0 ? `${Math.round(chars / 1000)}k 字` : '0 字'
})
const html = computed(() => renderMarkdown(props.doc?.content_markdown || ''))
</script>

<template>
  <section class="doc-content" aria-label="知识库文档内容">
    <header class="content-head">
      <div class="heading">
        <div class="icon"><el-icon><Document /></el-icon></div>
        <div class="head-text">
          <span class="eyebrow">DOCUMENT CONTENT</span>
          <h3 :title="doc?.title">{{ doc?.title || '文件内容' }}</h3>
          <div v-if="doc" class="meta">
            <el-tag size="small" type="primary" effect="plain">{{ doc.kb_code || '--' }}</el-tag>
            <el-tag size="small" effect="plain">{{ doc.chunk_count ?? 0 }} 块</el-tag>
            <span>{{ charsLabel }}</span>
          </div>
        </div>
        <div class="head-actions">
          <el-button size="small" @click="emit('show-files')"><el-icon><FolderOpened /></el-icon> 文件列表</el-button>
          <el-button size="small" text @click="emit('back')"><el-icon><Back /></el-icon> 返回全图</el-button>
        </div>
      </div>
    </header>

    <div class="content-body">
      <div v-if="loading" class="state" aria-live="polite">
        <el-icon :size="26" class="is-loading"><Loading /></el-icon>
        <span>正在加载文件内容…</span>
      </div>
      <div v-else-if="error" class="state error" role="alert">
        <el-icon :size="28"><WarningFilled /></el-icon>
        <strong>{{ error }}</strong>
        <div><el-button size="small" @click="emit('retry')">重试</el-button><el-button size="small" @click="emit('show-files')">文件列表</el-button></div>
      </div>
      <article v-else-if="doc" class="markdown-body" v-html="html" />
      <div v-else class="state"><el-icon :size="28"><Document /></el-icon><span>请选择文件查看内容</span></div>
    </div>
  </section>
</template>

<style scoped>
.doc-content { display:flex; flex-direction:column; width:100%; height:100%; min-height:0; overflow:hidden; border:1px solid var(--el-border-color-lighter); border-radius:16px; background:var(--el-bg-color); box-shadow:0 12px 32px rgba(15,23,42,.07); }
.content-head { padding:18px 20px 14px; border-bottom:1px solid var(--el-border-color-extra-light); flex-shrink:0; }
.heading { display:flex; align-items:flex-start; gap:12px; }
.eyebrow { display:block; margin-bottom:3px; color:var(--el-color-primary); font-size:10px; font-weight:800; letter-spacing:.15em; }
h3 { margin:0; overflow:hidden; color:var(--el-text-color-primary); font-size:16px; line-height:1.3; text-overflow:ellipsis; white-space:nowrap; }
.icon { display:grid; width:40px; height:40px; flex-shrink:0; color:#fff; border-radius:12px; background:linear-gradient(135deg,#0f6cbd,#3d90d6); box-shadow:0 6px 16px rgba(15,108,189,.28); place-items:center; }
.head-text { min-width:0; flex:1; }
.meta { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:8px; color:var(--el-text-color-secondary); font-size:12px; }
.head-actions { display:flex; flex-shrink:0; flex-direction:column; align-items:flex-end; gap:6px; }
.content-body { flex:1; min-height:0; overflow:auto; padding:14px 16px 18px; }
.state { display:flex; min-height:200px; align-items:center; justify-content:center; flex-direction:column; gap:10px; color:var(--el-text-color-placeholder); font-size:13px; text-align:center; }
.state.error { color:var(--el-color-danger); }
.state.error strong { color:var(--el-text-color-secondary); }
.markdown-body { overflow-wrap:anywhere; color:var(--el-text-color-regular); font-size:13.5px; line-height:1.7; }
.markdown-body :deep(pre), .markdown-body :deep(table) { display:block; max-width:100%; overflow-x:auto; }
.markdown-body :deep(img) { max-width:100%; height:auto; }
@media (max-width: 480px) { .heading { flex-wrap:wrap; } .head-actions { width:100%; flex-direction:row; align-items:center; } }
</style>
