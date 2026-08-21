<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'

const router = useRouter()
const agentStore = useAgentStore()

const recent = computed(() => agentStore.recentConversations.slice(0, 10))

const formatTime = (timestamp) => {
  const now = Date.now()
  const diff = now - timestamp
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  return new Date(timestamp).toLocaleDateString('zh-CN')
}

const agentName = (agentId) => {
  const agent = agentStore.agentById(agentId)
  return agent?.name || '未知'
}

const goToChat = (item) => {
  agentStore.requestFocus()
  if (item.conversationId) {
    router.push(`/chat/${item.agentId}?conversationId=${item.conversationId}`)
  } else {
    router.push(`/chat/${item.agentId}`)
  }
}

const handleDelete = async (item) => {
  try {
    await agentStore.deleteRemoteConversation(item.agentId, item.conversationId)
  } catch {
    // 删除失败静默处理
  }
}
</script>

<template>
  <div class="history-section">
    <div class="section-label">最近对话</div>
    <div v-if="recent.length > 0" class="history-list sidebar-scrollbar">
      <button
        v-for="item in recent"
        :key="item.agentId + item.conversationId"
        class="history-item"
        @click="goToChat(item)"
      >
        <span class="history-icon">
          <el-icon :size="14"><ChatDotRound /></el-icon>
        </span>
        <span class="history-info">
          <span class="history-title">{{ item.title }}</span>
          <span class="history-meta">
            {{ agentName(item.agentId) }} · {{ formatTime(item.updatedAt) }}
          </span>
        </span>
        <el-dropdown trigger="click" @command="() => handleDelete(item)" class="history-more-dropdown">
          <el-icon :size="16" class="history-more" @click.stop><MoreFilled /></el-icon>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="delete">
                <el-icon :size="14"><Delete /></el-icon>
                删除会话
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </button>
    </div>
    <div v-else class="history-empty">
      <p>暂无对话记录</p>
    </div>
  </div>
</template>

<style scoped>
.history-section {
  flex: 1;
  min-height: 0;
  padding: 0 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.section-label {
  padding: 16px 16px 6px;
  color: var(--sidebar-text-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  flex-shrink: 0;
}

.history-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.history-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--sidebar-text);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  transition: background 0.2s;
}

.history-item:hover {
  background: var(--sidebar-hover-bg);
}

.history-icon {
  color: var(--sidebar-text-muted);
  margin-top: 2px;
  flex-shrink: 0;
}

.history-info {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.history-title {
  font-size: 13px;
  color: var(--sidebar-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  font-size: 11px;
  color: var(--sidebar-text-muted);
}

.history-more-dropdown {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.history-item:hover .history-more-dropdown {
  opacity: 1;
}

.history-more {
  color: var(--sidebar-text-muted);
  padding: 4px;
  border-radius: 4px;
  cursor: pointer;
}

.history-more:hover {
  color: var(--el-color-danger);
  background: var(--sidebar-hover-bg);
}

.history-empty {
  padding: 16px;
}

.history-empty p {
  margin: 0;
  font-size: 12px;
  color: var(--sidebar-text-muted);
}
</style>
