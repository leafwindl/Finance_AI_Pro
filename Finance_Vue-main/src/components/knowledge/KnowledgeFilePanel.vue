<script setup>
import { computed } from 'vue'

const props = defineProps({
  kbCode: { type: String, default: '' },
  kbName: { type: String, default: '' },
  docCount: { type: Number, default: 0 },
  documents: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['select-doc', 'back', 'retry'])

const listTitle = computed(() =>
  props.kbCode ? `${props.kbCode} · ${props.kbName || '知识库'}` : '知识库文件'
)
</script>

<template>
  <section class="file-panel" aria-label="知识库文件列表">
    <header class="panel-head">
      <div class="heading">
        <div class="icon"><el-icon><FolderOpened /></el-icon></div>
        <div class="title-wrap">
          <span class="eyebrow">KNOWLEDGE BASE FILES</span>
          <h3 :title="listTitle">{{ listTitle }}</h3>
        </div>
        <el-button v-if="kbCode" text class="back-btn" @click="emit('back')">
          <el-icon><Back /></el-icon> 返回全图
        </el-button>
      </div>
      <div v-if="docCount >= 0" class="meta">共 {{ docCount }} 个文件</div>
    </header>

    <div class="panel-body">
      <div v-if="loading" class="state" aria-live="polite">
        <el-icon :size="24" class="is-loading"><Loading /></el-icon>
        <span>正在加载文件列表…</span>
      </div>
      <div v-else-if="error" class="state error" role="alert">
        <el-icon :size="24"><WarningFilled /></el-icon>
        <span>{{ error }}</span>
        <el-button size="small" @click="emit('retry')">重试</el-button>
      </div>
      <el-empty v-else-if="!documents.length" description="该知识库暂无文件" :image-size="72" />
      <ul v-else class="doc-list">
        <li v-for="doc in documents" :key="doc.doc_id">
          <button class="doc-item" type="button" :title="doc.title" @click="emit('select-doc', doc)">
            <span class="doc-icon"><el-icon><Document /></el-icon></span>
            <span class="doc-info">
              <span class="doc-title">{{ doc.title || '未命名文档' }}</span>
              <span class="doc-sub">
                <el-tag size="small" type="primary" effect="plain">{{ doc.chunk_count ?? 0 }} 块</el-tag>
                <span class="doc-source" :title="doc.source_file">{{ doc.source_file || '未提供来源文件名' }}</span>
              </span>
            </span>
            <el-icon class="doc-arrow"><ArrowRight /></el-icon>
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.file-panel { display:flex; flex-direction:column; width:100%; height:100%; min-height:0; overflow:hidden; border:1px solid var(--el-border-color-lighter); border-radius:16px; background:var(--el-bg-color); box-shadow:0 12px 32px rgba(15,23,42,.07); }
.panel-head { padding:18px 20px 14px; border-bottom:1px solid var(--el-border-color-extra-light); flex-shrink:0; }
.heading { display:flex; align-items:center; gap:12px; min-width:0; }
.title-wrap { min-width:0; flex:1; }
.eyebrow { display:block; margin-bottom:3px; color:var(--el-color-primary); font-size:10px; font-weight:800; letter-spacing:.15em; }
h3 { margin:0; overflow:hidden; color:var(--el-text-color-primary); font-size:17px; line-height:1.25; text-overflow:ellipsis; white-space:nowrap; }
.back-btn { flex-shrink:0; padding:0 8px; }
.meta { margin-top:10px; color:var(--el-text-color-secondary); font-size:12px; }
.icon { display:grid; width:40px; height:40px; flex-shrink:0; color:#fff; border-radius:12px; background:linear-gradient(135deg,#0f6cbd,#3d90d6); box-shadow:0 6px 16px rgba(15,108,189,.28); place-items:center; }
.panel-body { flex:1; min-height:0; overflow-y:auto; padding:8px 12px 12px; }
.state { display:flex; min-height:160px; align-items:center; justify-content:center; flex-direction:column; gap:10px; color:var(--el-text-color-placeholder); font-size:13px; text-align:center; }
.state.error { color:var(--el-color-danger); }
.doc-list { display:flex; flex-direction:column; gap:4px; margin:0; padding:0; list-style:none; }
.doc-item { display:flex; width:100%; align-items:center; gap:12px; padding:11px 12px; border:0; border-radius:10px; background:transparent; color:inherit; cursor:pointer; font-family:inherit; text-align:left; transition:background .15s; }
.doc-item:hover { background:var(--el-fill-color-light); }
.doc-item:focus-visible { outline:2px solid var(--el-color-primary); outline-offset:-2px; }
.doc-icon { display:grid; width:34px; height:34px; flex-shrink:0; color:var(--el-color-primary); border-radius:9px; background:var(--el-color-primary-light-9); place-items:center; }
.doc-info { min-width:0; flex:1; }
.doc-title { display:block; overflow:hidden; color:var(--el-text-color-primary); font-size:13px; font-weight:600; text-overflow:ellipsis; white-space:nowrap; }
.doc-sub { display:flex; min-width:0; align-items:center; gap:8px; margin-top:4px; }
.doc-source { overflow:hidden; color:var(--el-text-color-secondary); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.doc-arrow { flex-shrink:0; color:var(--el-text-color-placeholder); }
</style>
