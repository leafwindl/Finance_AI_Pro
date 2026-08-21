<script setup>
/**
 * GlobalAssistant — 全局悬浮智能对话助手（agent5 前端）
 * 右下角悬浮球（可拖拽）→ 对话框 → SSE 流式对话 → 表情状态切换
 * 集成 FlowVisualizer 业务流程可视化（真实 SSE 节点驱动）+ 多轮记忆会话持久化
 */
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { sendChatMessage } from '@/services/api'
import { useFileUpload } from '@/composables/useFileUpload'
import FlowVisualizer from './FlowVisualizer.vue'
import assistantIcon from '@/assets/agent5/智能体助手.png'

// 跳转调度（2026-08-20）：agent5 确认后跳转到目标 agent 页
const router = useRouter()

// ===== 状态 =====
const open = ref(false)          // 对话框开关
const messages = ref([])         // 消息列表 [{role, content}]
const input = ref('')            // 输入框
const sending = ref(false)       // 是否在回复中
const convId = ref('')           // 会话 ID（多轮记忆用；localStorage 持久化，刷新不丢）

// ===== 会话 ID 持久化：刷新页面后仍能接上多轮记忆 =====
const CONV_STORAGE_KEY = 'agent5_conv_id'
const savedConvId = localStorage.getItem(CONV_STORAGE_KEY)
if (savedConvId) convId.value = savedConvId
function saveConvId (id) {
  if (!id) return
  convId.value = id
  localStorage.setItem(CONV_STORAGE_KEY, id)
}
function clearConvId () {
  convId.value = ''
  localStorage.removeItem(CONV_STORAGE_KEY)
}

// ===== 流程可视化（FlowVisualizer 驱动状态，真实 SSE 事件点亮）=====
const flowActive = ref(false)    // 请求执行中
const flowNode = ref('')         // 当前 progress node（精确匹配 server.py 映射表）
const flowDone = ref(false)      // completed 到达
const flowFailed = ref(false)    // error 到达

// ===== 文件上传（agent5 文档问答用） =====
const { files: uploadFiles, doneFiles, hasUploading, addFiles, removeFile, clearFiles, formatSize, ALLOWED_EXTENSIONS, MAX_FILE_COUNT } = useFileUpload('ai-assistant')
const fileInput = ref(null)

function triggerFilePick() {
  fileInput.value?.click()
}

async function onFileChange(e) {
  const list = e.target.files
  if (list && list.length) {
    const results = await addFiles(list)
    const errors = results.filter(r => r && !r.success).map(r => r.error)
    if (errors.length) {
      messages.value.push({ role: 'assistant', content: `（上传失败：${errors.join('；')}）` })
    }
  }
  e.target.value = ''
}

// 智能体状态文字：welcome / creating / happy / sad（固定头像，不再切心情图）
const mood = ref('welcome')
const moodText = {
  welcome: '嗨！我是智能助手，有什么可以帮你？',
  creating: '创作中…',
  happy: '完成啦！',
  sad: '出错了…',
}

// ===== 方法 =====
// ===== 悬浮球拖拽 =====
const dragging = ref(false)
const fabPos = ref({ x: 0, y: 0 })           // 当前偏移（通过 style 控制）
let _dragStart = { x: 0, y: 0 }               // 鼠标按下时的位置
let _fabStart = { x: 0, y: 0 }                // 按下时球的偏移

let _dragged = false

function onDragStart(e) {
  if (e.button !== 0) return
  _dragged = false
  dragging.value = true
  _dragStart = { x: e.clientX, y: e.clientY }
  _fabStart = { ...fabPos.value }
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
  e.preventDefault()
}

function onDragMove(e) {
  if (!dragging.value) return
  const dx = e.clientX - _dragStart.x
  const dy = e.clientY - _dragStart.y
  if (Math.abs(dx) > 2 || Math.abs(dy) > 2) _dragged = true
  fabPos.value = { x: _fabStart.x + dx, y: _fabStart.y + dy }
}

function onDragEnd() {
  dragging.value = false
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  if (!_dragged) toggle()
}

function toggle() {
  open.value = !open.value
  if (open.value) {
    mood.value = 'welcome'
    if (messages.value.length === 0) {
      messages.value.push({ role: 'assistant', content: '你好！我是你的智能助手，可以随便聊聊，也可以问我证券测试相关问题，还能上传文档让我分析哦～' })
    }
  }
}

async function send() {
  const text = input.value.trim()
  if ((!text && doneFiles.value.length === 0) || sending.value) return
  // 上传还没完成就发送 → file_ids 为空，agent 看不到文件（踩过坑）
  if (hasUploading.value) {
    messages.value.push({ role: 'assistant', content: '（文件还在上传中，请稍候再发送）' })
    return
  }
  input.value = ''

  // 收集已上传成功的 file_id
  const fileIds = doneFiles.value.map(f => f.result?.file_id).filter(Boolean)
  const attachLabel = doneFiles.value.map(f => `[附件] ${f.name}`).join(' ')
  const userContent = [text, attachLabel].filter(Boolean).join('\n\n')
  messages.value.push({ role: 'user', content: userContent })
  clearFiles()

  await runChat({ query: text, fileIds })
}

async function runChat(payload, retried = false) {
  const pending = { role: 'assistant', content: '', streaming: true }
  messages.value.push(pending)
  sending.value = true
  mood.value = 'creating'
  // 流程可视化：请求发出（真实动作）
  flowActive.value = true
  flowNode.value = ''
  flowDone.value = false
  flowFailed.value = false
  await nextTick()
  scrollBottom()

  let retrying = false
  try {
    const stream = await sendChatMessage({
      query: payload.query,
      conversation_id: convId.value || null,
      agent_id: 'ai-assistant',
      file_ids: payload.fileIds,
    })
    let full = ''
    for await (const { event, data } of stream) {
      if (event === 'progress') {
        // 真实节点驱动（对齐 server.py ASSISTANT_NODE_PROGRESS 节点名）
        flowNode.value = data.node || ''
      } else if (event === 'delta') {
        full += data.text || ''
        pending.content = full
        await nextTick()
        scrollBottom()
      } else if (event === 'completed') {
        // 网关转发的事件用 conversation_id（不是 thread_id），兼容两者
        if (data.conversation_id) saveConvId(data.conversation_id)
        else if (data.thread_id) saveConvId(data.thread_id)
        if (!full && data.answer) {
          full = data.answer
          pending.content = full
        }
        // 跳转调度（2026-08-20）：agent5 确认后 metadata.transfer → 两段确认②弹窗（内容可编辑）→ 跳转
        const transfer = data.metadata && data.metadata.transfer
        if (transfer && transfer.target) {
          const content = window.prompt(`将跳转到「${transfer.target}」智能体，确认内容（可编辑）：`, transfer.query || '')
          if (content !== null && content.trim()) {
            router.push({ path: `/chat/${transfer.target}`, query: { q: content.trim(), pid: `custom_${Date.now()}` } })
          }
        }
        flowActive.value = false
        flowDone.value = true
        mood.value = 'happy'
      } else if (event === 'error') {
        pending.content = `（出错了：${data.message || '未知错误'}）`
        flowActive.value = false
        flowFailed.value = true
        mood.value = 'sad'
      }
    }
  } catch (e) {
    const msg = e.message || e
    // localStorage 保存的旧会话 ID 已失效（会话不存在，如换账号登录/网关会话重建）
    // → 清掉旧 ID，自动以新会话重试一次，避免助手因此永远不可用
    if (!retried && String(msg).includes('会话不存在')) {
      retrying = true
      clearConvId()
      messages.value.pop()
      await runChat(payload, true)
      return
    }
    pending.content = `（请求失败：${msg}）`
    flowActive.value = false
    flowFailed.value = true
    mood.value = 'sad'
  } finally {
    if (!retrying) {
      pending.streaming = false
      sending.value = false
      await nextTick()
      scrollBottom()
    }
  }
}

function scrollBottom() {
  const box = document.querySelector('.ga-chat-body')
  if (box) box.scrollTop = box.scrollHeight
}
</script>

<template>
  <!-- 悬浮球（可拖拽） -->
  <div class="ga-fab" :class="{ active: open, dragging: dragging }"
       :style="fabPos.x || fabPos.y ? { transform: `translate(${fabPos.x}px, ${fabPos.y}px)` } : {}"
       @mousedown="onDragStart" title="智能助手（可拖拽）">
    <img :src="assistantIcon" alt="assistant" />
  </div>

  <!-- 对话框 -->
  <transition name="ga-pop">
    <div v-if="open" class="ga-panel">
      <!-- 头部 -->
      <div class="ga-header">
        <img :src="assistantIcon" class="ga-avatar" alt="avatar" />
        <div>
          <div class="ga-title">智能助手</div>
          <div class="ga-mood">{{ moodText[mood] }}</div>
        </div>
        <button class="ga-close" @click="toggle">×</button>
      </div>

      <!-- 流程可视化（真实 SSE 节点驱动；执行中/完成/失败时显示）-->
      <FlowVisualizer
        v-if="flowActive || flowDone || flowFailed"
        :active="flowActive"
        :node="flowNode"
        :done="flowDone"
        :failed="flowFailed"
      />

      <!-- 消息区 -->
      <div class="ga-chat-body">
        <div v-for="(m, i) in messages" :key="i"
             :class="['ga-msg', m.role === 'user' ? 'ga-user' : 'ga-ai']">
          <div class="ga-bubble">{{ m.content }}</div>
        </div>
      </div>

      <!-- 附件区：上传中 / 已完成 -->
      <div v-if="uploadFiles.length" class="ga-files">
        <div v-for="f in uploadFiles" :key="f.id" class="ga-file"
             :class="{ 'is-error': f.status === 'error' }">
          <span class="ga-file-name">[附件] {{ f.name }}</span>
          <span class="ga-file-meta">
            <template v-if="f.status === 'uploading'">上传中…</template>
            <template v-else-if="f.status === 'error'">{{ f.error || '上传失败' }}</template>
            <template v-else>{{ formatSize(f.size) }}</template>
          </span>
          <button class="ga-file-del" @click="removeFile(f.id)" title="移除">×</button>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="ga-input-row">
        <button class="ga-attach" :disabled="uploadFiles.length >= MAX_FILE_COUNT || sending"
                title="上传文档（支持 {{ ALLOWED_EXTENSIONS.join(' / ') }}，单个 ≤10MB）"
                @click="triggerFilePick">[附件]</button>
        <input
          ref="fileInput"
          type="file"
          multiple
          class="ga-file-input"
          :accept="ALLOWED_EXTENSIONS.join(',')"
          @change="onFileChange"
        />
        <input
          v-model="input"
          class="ga-input"
          placeholder="输入消息…"
          :disabled="sending"
          @keyup.enter="send"
        />
        <button class="ga-send" :disabled="sending || hasUploading || (!input.trim() && !doneFiles.length)" @click="send">
          {{ sending ? '…' : hasUploading ? '上传中…' : '发送' }}
        </button>
      </div>
    </div>
  </transition>
</template>

<style scoped>
/* ===== 悬浮球 ===== */
.ga-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  overflow: hidden;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
  z-index: 1000;
  transition: transform 0.2s;
  background: #fff;
}
.ga-fab:hover { transform: scale(1.08); }
.ga-fab.active { transform: rotate(15deg); }
.ga-fab img { width: 100%; height: 100%; object-fit: cover; }
.ga-fab.dragging { cursor: grabbing; }

/* ===== 面板 ===== */
.ga-panel {
  position: fixed;
  right: 24px;
  bottom: 92px;
  width: 360px;
  max-height: 520px;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
  z-index: 1001;
  overflow: hidden;
}
.ga-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}
.ga-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
}
.ga-title { font-weight: 600; font-size: 14px; }
.ga-mood { font-size: 12px; color: #909399; }
.ga-close {
  margin-left: auto;
  border: none;
  background: none;
  font-size: 22px;
  color: #909399;
  cursor: pointer;
  line-height: 1;
}
.ga-chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
  max-height: 360px;
}
.ga-msg { display: flex; }
.ga-user { justify-content: flex-end; }
.ga-ai { justify-content: flex-start; }
.ga-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.ga-user .ga-bubble { background: #409eff; color: #fff; }
.ga-ai .ga-bubble { background: #f0f2f5; color: #303133; }

/* ===== 附件区 ===== */
.ga-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px 0;
}
.ga-file {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 3px 8px;
  border-radius: 6px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  font-size: 12px;
  color: #529b2e;
}
.ga-file.is-error {
  background: #fef0f0;
  border-color: #fde2e2;
  color: #f56c6c;
}
.ga-file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}
.ga-file-meta { flex-shrink: 0; font-size: 11px; opacity: 0.8; }
.ga-file-del {
  border: none;
  background: none;
  color: inherit;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}

/* ===== 输入区 ===== */
.ga-input-row {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid #e4e7ed;
}
.ga-attach {
  flex-shrink: 0;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  width: 32px;
  height: 32px;
  background: #fff;
  font-size: 15px;
  cursor: pointer;
  line-height: 1;
}
.ga-attach:hover { border-color: #409eff; }
.ga-attach:disabled { opacity: 0.5; cursor: not-allowed; }
.ga-file-input { display: none; }
.ga-input {
  flex: 1;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  outline: none;
}
.ga-input:focus { border-color: #409eff; }
.ga-send {
  border: none;
  border-radius: 8px;
  padding: 0 16px;
  background: #409eff;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}
.ga-send:disabled { background: #a0cfff; cursor: not-allowed; }

/* ===== 动画 ===== */
.ga-pop-enter-active, .ga-pop-leave-active { transition: opacity 0.2s, transform 0.2s; }
.ga-pop-enter-from, .ga-pop-leave-to { opacity: 0; transform: translateY(10px); }
</style>
