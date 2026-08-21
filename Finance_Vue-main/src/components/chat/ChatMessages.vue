<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { renderMarkdown } from '@/composables/useMarkdown'

const props = defineProps({
  messages: {
    type: Array,
    required: true
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const formatFileSize = (bytes) => {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const messagesRef = ref(null)
const elapsed = ref(0)
let timer = null

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

watch(() => props.messages.length, scrollToBottom)
watch(() => props.loading, (val) => {
  if (val) {
    elapsed.value = 0
    timer = setInterval(() => elapsed.value++, 1000)
    scrollToBottom()
  } else {
    clearInterval(timer)
    timer = null
  }
}, { immediate: true })

onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div ref="messagesRef" class="chat-messages" aria-live="polite">
    <template v-for="msg in messages" :key="msg.id">
      <!-- pending 进度提示：独立行，不继承 message-row -->
      <div v-if="msg.role === 'pending'" class="pending-row">
        <span class="pending-dot"></span>
        <span class="pending-status">{{ msg.status }}</span>
        <span class="pending-elapsed">已等待 {{ elapsed }} 秒</span>
      </div>

      <!-- 正常消息 -->
      <div v-else :class="['message-row', `is-${msg.role}`]">
        <!-- AI avatar -->
        <div v-if="msg.role !== 'user'" class="message-avatar">
          <el-icon :size="16"><MagicStick /></el-icon>
        </div>

        <!-- Message bubble -->
        <div class="message-bubble">
          <div class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
          <!-- File attachments -->
          <div v-if="msg.files && msg.files.length > 0" class="msg-file-list">
            <div v-for="f in msg.files" :key="f.name" class="msg-file-tag">
              <el-icon :size="12"><Document /></el-icon>
              <span class="msg-file-name" :title="f.name">{{ f.name }}</span>
              <span class="msg-file-size">{{ formatFileSize(f.size) }}</span>
            </div>
          </div>

        </div>

        <!-- User avatar (placeholder for symmetry) -->
        <div v-if="msg.role === 'user'" class="message-avatar is-user-avatar">
          <el-icon :size="16"><UserFilled /></el-icon>
        </div>
      </div>
    </template>

    <!-- Typing indicator (fallback when no pending message) -->
    <div v-if="loading" class="message-row is-assistant">
      <div class="message-avatar">
        <el-icon :size="16"><MagicStick /></el-icon>
      </div>
      <div class="message-bubble typing">
        <span />
        <span />
        <span />
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-messages {
  flex: 1;
  min-height: 0;
  padding: 24px 28px;
  overflow-y: auto;
  background:
    radial-gradient(circle at 12% 8%, rgba(15, 108, 189, 0.05), transparent 28%),
    var(--el-bg-color-page);
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 20px;
}

.message-row.is-user {
  justify-content: flex-end;
}

/* ---- Pending progress (independent row, never pollutes .message-row) ---- */
.pending-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  margin-bottom: 20px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.pending-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-primary);
  flex-shrink: 0;
  animation: pending-blink 1s infinite;
}

@keyframes pending-blink {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.pending-status {
  flex-shrink: 0;
}

.pending-elapsed {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  margin-left: 4px;
}

.message-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  color: #fff;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  place-items: center;
}

.message-avatar.is-user-avatar {
  background: linear-gradient(135deg, var(--el-color-primary-dark-2), var(--el-color-primary));
}

.message-bubble {
  max-width: min(76%, 560px);
  padding: 12px 16px;
  color: var(--el-text-color-primary);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px 16px 16px;
  background: var(--el-bg-color);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
  font-size: 14px;
  overflow-wrap: anywhere;
}

.is-user .message-bubble {
  color: #fff;
  border: none;
  border-radius: 16px 6px 16px 16px;
  background: linear-gradient(135deg, var(--el-color-primary), #3d90d6);
}

.is-error .message-bubble {
  color: var(--el-color-danger);
  border-color: var(--el-color-danger-light-7);
  background: var(--el-color-danger-light-9);
}

/* ---- File attachments in message bubbles ---- */
.msg-file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-extra-light);
}

.is-user .msg-file-list {
  border-top-color: rgba(255, 255, 255, 0.2);
}

.msg-file-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 5px;
  background: var(--el-fill-color);
}

.is-user .msg-file-tag {
  background: rgba(255, 255, 255, 0.18);
  color: rgba(255, 255, 255, 0.9);
}

.msg-file-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-file-size {
  opacity: 0.7;
  flex-shrink: 0;
}

/* Typing dots animation */
.typing {
  display: flex;
  gap: 5px;
  align-items: center;
  min-height: 42px;
}

.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-text-color-secondary);
  animation: typing-bounce 1s infinite ease-in-out;
}

.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.3s; }

@keyframes typing-bounce {
  0%, 80%, 100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-4px);
  }
}

/* ---- Markdown 内容样式（最小化，与 qwen 一致） ---- */

/* 表格 — 宽表横向滚动 */
.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.3em 0;
  font-size: 13px;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--el-border-color-lighter);
  padding: 6px 10px;
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}
.markdown-body :deep(tr:nth-child(even)) {
  background: var(--el-fill-color-lighter);
}

/* 行内代码 */
.markdown-body :deep(code) {
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 12.5px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  background: var(--el-fill-color);
  color: var(--el-color-danger);
}
/* 代码块 */
.markdown-body :deep(pre) {
  margin: 0.3em 0;
  border-radius: 8px;
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  display: block;
  overflow-x: auto;
  max-width: 100%;
}

/* 链接 */
.markdown-body :deep(a) {
  color: var(--el-color-primary);
}

/* 图片自适应 */
.markdown-body :deep(img) {
  max-width: 100%;
  height: auto;
}

/* 代码块 */
.markdown-body :deep(pre) {
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 0.9em;
}

.markdown-body p {
  margin: 0;
}

/* 深色模式代码块 */
html.dark .markdown-body :deep(pre code) {
  background: #1e1e1e;
  color: #e5eaf3;
}

@media (max-width: 640px) {
  .chat-messages {
    padding: 20px 16px;
  }

  .message-bubble {
    max-width: 86%;
  }
}
</style>
