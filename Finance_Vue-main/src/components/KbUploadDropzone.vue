<script setup>
/**
 * KbUploadDropzone — 知识库文档入库拖拽框
 * 主界面两个流程面板下方的合并长条框：拖入/点击选择文件 → 上传入知识库。
 * V2 自动分类：默认不传 kb_code（后台按块全自动分类）；也可在下拉里手动指定 KB01~KB06
 * （整篇归入指定库）。提交后轮询任务接口直到终态，再展示块级多库结果。
 */
import { ref } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { uploadDocumentAndWait } from '@/services/api/knowledge'

const ALLOWED_EXTENSIONS = ['.md', '.txt', '.pdf', '.docx']
const MAX_SIZE = 10 * 1024 * 1024
const KB_OPTIONS = Array.from({ length: 6 }, (_, i) => `KB${String(i + 1).padStart(2, '0')}`)

const dragging = ref(false)   // 拖拽悬停高亮
const uploading = ref(false)  // 入库中（异步轮询）
const progressText = ref('')  // 任务阶段进度文案
const fileInput = ref(null)
const selectedKb = ref('')    // '' = 全自动分类；KB01~KB06 = 人工指定

const accept = ALLOWED_EXTENSIONS.join(',')
const hint = `自动分类入库 · 支持 ${ALLOWED_EXTENSIONS.join(' / ')}，单文件 ≤10MB`

function validate(file) {
  const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `不支持的文件类型：${file.name}（仅支持 ${ALLOWED_EXTENSIONS.join(' / ')}）`
  }
  if (file.size === 0) return `文件为空：${file.name}`
  if (file.size > MAX_SIZE) return `文件超过 10MB 限制：${file.name}`
  return ''
}

/** 依据 V2 任务结果生成入库结果文案（kb_distribution / total_chunks / blocks / kb_code）。 */
function resultSummary(name, task) {
  const result = task?.result || {}
  const dist = result.kb_distribution || {}
  const chunks = result.total_chunks != null
    ? result.total_chunks
    : (Array.isArray(result.blocks) ? result.blocks.length : 0)
  const distText = Object.entries(dist)
    .filter(([, n]) => n)
    .map(([k, n]) => `${k}×${n}`)
    .join('、')
  if (result.kb_code) {
    return `「${name}」已入库到 ${result.kb_code}，共 ${chunks} 个知识块`
  }
  return `「${name}」已入库 ${chunks} 个知识块${distText ? `：${distText}` : ''}`
}

async function handleFiles(list) {
  const files = Array.from(list || [])
  if (!files.length) return

  for (const f of files) {
    const err = validate(f)
    if (err) {
      ElMessage.warning(err)
      return
    }
  }

  uploading.value = true
  const kb = selectedKb.value
  const results = []
  for (const f of files) {
    try {
      progressText.value = `正在解析与分类 ${f.name}…`
      const task = await uploadDocumentAndWait(f, {
        kbCode: kb,
        onProgress: (t) => {
          const p = t?.progress
          if (p?.stage) {
            progressText.value = `${f.name} · ${p.stage}${Number.isFinite(p.percent) ? ` ${p.percent}%` : ''}`
          }
        }
      })
      results.push({ ok: true, name: f.name, task })
    } catch (e) {
      const aborted = e?.name === 'AbortError'
      results.push({ ok: false, name: f.name, aborted, error: aborted ? '已取消' : (e.message || e) })
    }
  }
  uploading.value = false
  progressText.value = ''

  const okCount = results.filter(r => r.ok).length
  const failCount = results.length - okCount
  const failures = results.filter(r => !r.ok)
  if (failCount === 0 && okCount > 0) {
    if (okCount === 1 && results[0].task) {
      ElNotification.success({
        title: '入库成功',
        message: resultSummary(results[0].name, results[0].task),
        duration: 4500
      })
    } else {
      ElMessage.success(`已成功入库 ${okCount} 个文档，稍后可被知识库检索`)
    }
  } else if (okCount > 0) {
    ElMessage.warning(`入库完成：成功 ${okCount} 个，失败 ${failCount} 个（${failures.map(r => r.error).join('；')}）`)
  } else {
    ElMessage.error(`入库失败：${failures.map(r => `${r.name}（${r.error}）`).join('；')}，可重试`)
  }

  // 重置 input，使同一文件可再次选择
  if (fileInput.value) fileInput.value.value = ''
}

function onDrop(e) {
  dragging.value = false
  e.preventDefault()
  handleFiles(e.dataTransfer?.files)
}

function onFileChange(e) {
  handleFiles(e.target.files)
}

function triggerPick() {
  if (uploading.value) return
  fileInput.value?.click()
}
</script>

<template>
  <div
    class="kb-dropzone"
    :class="{ 'is-dragging': dragging, 'is-uploading': uploading }"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
    @click="triggerPick"
  >
    <div class="kb-dropzone__icon">
      <el-icon :size="26"><UploadFilled /></el-icon>
    </div>
    <div class="kb-dropzone__text">
      <template v-if="uploading">
        <span class="kb-dropzone__title">正在入库…</span>
        <span class="kb-dropzone__sub">{{ progressText || '文档解析与分类由服务端处理，请稍候' }}</span>
      </template>
      <template v-else>
        <span class="kb-dropzone__title">拖拽文档到此处，或点击选择</span>
        <span class="kb-dropzone__sub">上传后自动解析并按内容分类入库，供智能体检索 · {{ hint }}</span>
      </template>
    </div>
    <div class="kb-dropzone__aside" @click.stop.prevent>
      <el-select
        v-model="selectedKb"
        class="kb-dropzone__select"
        :disabled="uploading"
        aria-label="入库分类方式"
      >
        <el-option label="自动分类（推荐）" value="" />
        <el-option v-for="code in KB_OPTIONS" :key="code" :label="code" :value="code" />
      </el-select>
    </div>
    <input
      ref="fileInput"
      class="kb-dropzone__input"
      type="file"
      multiple
      :accept="accept"
      @change="onFileChange"
    />
  </div>
</template>

<style scoped>
.kb-dropzone {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 22px 24px;
  border: 1.5px dashed var(--el-border-color);
  border-radius: 16px;
  background: var(--el-bg-color);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
}
.kb-dropzone:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.kb-dropzone.is-dragging {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: 0 0 0 4px var(--el-color-primary-light-8);
}
.kb-dropzone.is-uploading {
  cursor: progress;
  pointer-events: none;
}
.kb-dropzone__icon {
  display: grid;
  width: 52px;
  height: 52px;
  flex-shrink: 0;
  color: var(--el-color-primary);
  border-radius: 14px;
  background: var(--el-color-primary-light-9);
  place-items: center;
}
.kb-dropzone__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.kb-dropzone__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.kb-dropzone__sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.kb-dropzone__aside {
  margin-left: auto;
  flex-shrink: 0;
}
.kb-dropzone__select {
  width: 168px;
}
.kb-dropzone__input {
  display: none;
}
</style>
