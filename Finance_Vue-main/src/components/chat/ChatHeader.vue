<script setup>
const props = defineProps({
  agent: {
    type: Object,
    required: true
  },
  isOnline: {
    type: Boolean,
    default: true
  },
  hideNew: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['new-conversation'])
</script>

<template>
  <header class="chat-header">
    <div class="chat-agent-info">
      <div class="chat-agent-icon">
        <el-icon :size="22"><component :is="agent.icon" /></el-icon>
      </div>
      <div class="chat-agent-text">
        <div class="chat-agent-name">
          <h2>{{ agent.name }}</h2>
          <span :class="['status-dot', { online: isOnline }]" />
        </div>
        <p>{{ agent.category }} · AI 助手</p>
      </div>
    </div>

    <el-button v-if="!hideNew" plain @click="emit('new-conversation')">
      <el-icon><RefreshRight /></el-icon>
      新对话
    </el-button>
  </header>
</template>

<style scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 28px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}

.chat-agent-info {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.chat-agent-icon {
  display: grid;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  color: #fff;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  place-items: center;
}

.chat-agent-name {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chat-agent-name h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #94a3b8;
}

.status-dot.online {
  background: #22c55e;
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.12);
}

.chat-agent-text p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 640px) {
  .chat-header {
    padding: 14px 16px;
  }

  .chat-header .el-button {
    padding: 8px 12px;
    font-size: 12px;
  }
}
</style>
