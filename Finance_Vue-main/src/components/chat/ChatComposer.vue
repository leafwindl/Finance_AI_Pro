<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import { useAgentStore } from '@/stores/agents'

const agentStore = useAgentStore()

const props = defineProps({
  agentId: {
    type: String,
    default: ''
  },
  suggestions: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
})

const emit = defineEmits(['send'])

const input = ref('')
const textareaRef = ref(null)

const canSend = () => {
  return input.value.trim().length > 0 && !props.loading
}

const handleSend = (suggested) => {
  const query = (typeof suggested === 'string' ? suggested : input.value).trim()
  if (!query || props.loading) return

  emit('send', query)
  input.value = ''
}

// Restore focus to textarea after loading completes
watch(() => props.loading, (val, prev) => {
  if (prev && !val) {
    nextTick(() => {
      textareaRef.value?.focus()
    })
  }
})

// Auto-focus textarea on mount
onMounted(() => {
  nextTick(() => {
    textareaRef.value?.focus()
  })
})

// Auto-focus when switching to a different agent
watch(() => props.agentId, () => {
  nextTick(() => {
    textareaRef.value?.focus()
  })
})

// Auto-focus when re-clicking the same agent / recent conversation
watch(() => agentStore.focusRequestToken, () => {
  nextTick(() => {
    textareaRef.value?.focus()
  })
})
</script>

<template>
  <div class="chat-composer">
    <!-- Suggestion chips -->
    <div v-if="suggestions.length > 0" class="suggestions">
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

    <!-- Textarea -->
    <div class="input-row">
      <el-input
        ref="textareaRef"
        v-model="input"
        type="textarea"
        :rows="3"
        resize="none"
        maxlength="2000"
        show-word-limit
        placeholder="输入你的问题，Enter 发送，Shift + Enter 换行"
        :disabled="loading"
        @keydown.enter.exact.prevent="handleSend()"
      />
    </div>

    <!-- Bottom bar -->
    <div class="composer-footer">
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
  </div>
</template>

<style scoped>
.chat-composer {
  padding: 16px 28px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}

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

.input-row :deep(.el-textarea__inner) {
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 10px;
}

.send-icon {
  margin-left: 4px;
}

@media (max-width: 640px) {
  .chat-composer {
    padding: 14px 16px 16px;
  }

  .composer-footer {
    justify-content: flex-end;
  }
}
</style>
