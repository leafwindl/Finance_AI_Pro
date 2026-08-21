<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAgentStore } from '@/stores/agents'
import { useFileUpload } from '@/composables/useFileUpload'
import './file-upload.css'

const agentStore = useAgentStore()

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  agentId: {
    type: String,
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  },
  suggestions: {
    type: Array,
    default: () => []
  },
  showSuggestions: {
    type: Boolean,
    default: false
  },
  placeholder: {
    type: String,
    default: '输入你的问题，Enter 发送，Shift + Enter 换行，Ctrl+Enter 也可发送'
  }
})

const emit = defineEmits(['update:modelValue', 'send'])

const {
  files,
  doneFiles,
  hasUploading,
  addFile,
  removeFile,
  clearFiles,
  retryFile,
  formatSize,
  MAX_FILE_COUNT,
  ALLOWED_EXTENSIONS
} = useFileUpload(props.agentId)

/* ---- v-model ---- */
const text = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

/* ---- refs ---- */
const textareaRef = ref(null)
const fileInputRef = ref(null)

/* ---- computed ---- */
const accept = computed(() => ALLOWED_EXTENSIONS.join(','))

const canSend = () => {
  return text.value.trim().length > 0 && !props.loading && !hasUploading.value
}

/* ---- file extension → badge label ---- */
const extLabel = (ext) => {
  const map = {
    '.pdf': 'PDF', '.docx': 'DOC', '.xlsx': 'XLS', '.csv': 'CSV',
    '.md': 'MD', '.txt': 'TXT', '.json': 'JSON',
    '.png': 'PNG', '.jpg': 'JPG', '.jpeg': 'JPG', '.webp': 'WEBP', '.bmp': 'BMP'
  }
  return map[ext] || ext.replace('.', '').toUpperCase()
}

/* ---- file extension → Element Plus icon ---- */
const extIcon = (ext) => {
  const map = {
    '.pdf': 'Document',
    '.docx': 'Document',
    '.xlsx': 'DataAnalysis',
    '.csv': 'DataAnalysis', '.json': 'Notebook',
    '.md': 'Tickets', '.txt': 'Tickets',
    '.png': 'Picture', '.jpg': 'Picture', '.jpeg': 'Picture', '.webp': 'Picture', '.bmp': 'Picture'
  }
  return map[ext] || 'Document'
}

/* ---- file extension → badge colour ---- */
const extColor = (ext) => {
  const map = {
    '.pdf': '#e74c3c',
    '.docx': '#2980b9',
    '.xlsx': '#27ae60', '.csv': '#27ae60',
    '.md': '#6366f1', '.txt': '#6366f1',
    '.json': '#f39c12',
    '.png': '#e67e22', '.jpg': '#e67e22', '.jpeg': '#e67e22', '.webp': '#e67e22', '.bmp': '#e67e22'
  }
  return map[ext] || 'var(--el-color-info)'
}

/* ---- drag & drop upload ---- */
const onDrop = async (e) => {
  e.preventDefault()
  const dropped = Array.from(e.dataTransfer?.files || [])
  if (dropped.length === 0) return
  for (const file of dropped) {
    const result = await addFile(file)
    if (!result.success && result.error) ElMessage.warning(result.error)
  }
}

/* ---- paste upload ---- */
const onPaste = async (e) => {
  const items = Array.from(e.clipboardData?.items || [])
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) {
        e.preventDefault()
        const result = await addFile(file)
        if (!result.success && result.error) {
          ElMessage.warning(result.error)
        }
      }
    }
  }
}

/* ---- file picker ---- */
const triggerFileInput = () => {
  fileInputRef.value?.click()
}

const onFileChange = async (e) => {
  const selected = Array.from(e.target.files)
  if (selected.length === 0) return

  for (const file of selected) {
    const result = await addFile(file)
    if (!result.success && result.error) {
      ElMessage.warning(result.error)
    }
  }

  // Reset so the same file can be re-selected after removal
  e.target.value = ''
}

/* ---- send ---- */
const handleSend = (suggested) => {
  const query = (typeof suggested === 'string' ? suggested : text.value).trim()
  if (!query || props.loading || hasUploading.value) return

  const filePayload = doneFiles.value.map(f => ({
    name: f.name,
    size: f.size,
    ext: f.ext,
    file_id: f.result?.file_id || '',
    url: f.result?.url || ''
  }))

  emit('send', { text: query, files: filePayload })

  // Clear state
  if (typeof suggested !== 'string') {
    text.value = ''
  }
  clearFiles()
}

/* ---- keyboard ---- */
const onKeydown = (e) => {
  // Ctrl+Enter or Cmd+Enter
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    handleSend()
    return
  }

  // Enter (without Shift) -> send
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
  // Shift+Enter -> native newline
}

/* ---- focus management (preserve existing ChatComposer behaviour) ---- */
const focus = () => {
  nextTick(() => textareaRef.value?.focus())
}

watch(() => props.loading, (val, prev) => {
  if (prev && !val) focus()
})

onMounted(focus)

watch(() => props.agentId, () => {
  clearFiles()
  focus()
})

watch(() => agentStore.focusRequestToken, () => {
  focus()
})
</script>

<template>
  <div
    class="chat-composer"
    @paste="onPaste"
    @dragover.prevent
    @dragenter.prevent
    @drop="onDrop"
  >
    <!-- ===== actions-prefix slot (reserved for "新对话" button) ===== -->
    <div v-if="$slots['actions-prefix']" class="fu-actions-prefix">
      <slot name="actions-prefix" />
    </div>

    <!-- ===== Suggestions ===== -->
    <div v-if="showSuggestions && suggestions.length > 0" class="suggestions">
      <button
        v-for="q in suggestions"
        :key="q"
        type="button"
        class="suggestion-chip"
        @click="handleSend(q)"
      >
        {{ q }}
      </button>
    </div>

    <!-- ===== File chips ===== -->
    <div v-if="files.length > 0" class="fu-file-chips">
      <div
        v-for="f in files"
        :key="f.id"
        :class="['fu-file-chip', {
          'is-uploading': f.status === 'uploading',
          'is-error': f.status === 'error'
        }]"
        :title="f.name"
      >
        <!-- Left: file icon -->
        <span class="fu-file-chip__icon" :style="{ color: extColor(f.ext), background: extColor(f.ext) + '18' }">
          <el-icon :size="20"><component :is="extIcon(f.ext)" /></el-icon>
        </span>
        <!-- Right: content (two rows) -->
        <span class="fu-file-chip__body">
          <span class="fu-file-chip__row">
            <span class="fu-file-chip__name">{{ f.name }}</span>
            <span class="fu-file-chip__status">
              <span v-if="f.status === 'uploading'" class="fu-spin" />
              <el-icon v-else-if="f.status === 'done'" :size="14" color="var(--el-color-success)"><CircleCheck /></el-icon>
              <el-icon v-else-if="f.status === 'error'" :size="14" color="var(--el-color-danger)"><CircleClose /></el-icon>
            </span>
            <button
              v-if="f.status === 'error'"
              class="fu-chip-retry"
              @click="retryFile(f.id)"
              aria-label="重新上传"
            >
              <el-icon :size="14"><RefreshRight /></el-icon>
            </button>
            <button
              class="fu-chip-remove"
              :disabled="f.status === 'uploading'"
              @click="removeFile(f.id)"
              aria-label="移除文件"
            >&times;</button>
          </span>
          <span class="fu-file-chip__row fu-file-chip__sub">
            <span class="fu-file-chip__type">{{ extLabel(f.ext) }}</span>
            <span class="fu-file-chip__size">{{ formatSize(f.size) }}</span>
          </span>
        </span>
      </div>
    </div>

    <!-- ===== Textarea ===== -->
    <div class="input-row">
      <el-input
        ref="textareaRef"
        v-model="text"
        type="textarea"
        :rows="3"
        resize="none"
        maxlength="2000"
        show-word-limit
        :placeholder="placeholder"
        :disabled="loading"
        @keydown="onKeydown"
      />
    </div>

    <!-- ===== Footer ===== -->
    <div class="composer-footer">
      <div class="footer-left">
        <el-button
          :disabled="loading || files.length >= MAX_FILE_COUNT"
          @click="triggerFileInput"
        >
          <el-icon><Upload /></el-icon>
          上传文件
        </el-button>
        <span class="hint">Ctrl+Enter 发送 · 最多 {{ MAX_FILE_COUNT }} 个文件 · 单文件 ≤10 MB</span>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!canSend()"
        @click="handleSend()"
      >
        发送
        <el-icon class="send-icon"><Promotion /></el-icon>
      </el-button>
    </div>

    <!-- Hidden file input -->
    <input
      ref="fileInputRef"
      class="fu-file-trigger"
      type="file"
      multiple
      :accept="accept"
      @change="onFileChange"
    />
  </div>
</template>

<style scoped>
.chat-composer {
  padding: 16px 28px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}

/* ---- actions-prefix ---- */
.fu-actions-prefix {
  margin-bottom: 10px;
}

/* ---- suggestions ---- */
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.suggestion-chip {
  padding: 7px 14px;
  color: var(--el-color-primary);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  text-align: left;
  transition: all 0.2s;
}

.suggestion-chip:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-1px);
}

/* ---- textarea ---- */
.input-row :deep(.el-textarea__inner) {
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

/* ---- footer ---- */
.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.send-icon {
  margin-left: 4px;
}

@media (max-width: 640px) {
  .chat-composer {
    padding: 14px 16px 16px;
  }

  .hint {
    display: none;
  }

  .composer-footer {
    justify-content: flex-end;
  }
}
</style>
