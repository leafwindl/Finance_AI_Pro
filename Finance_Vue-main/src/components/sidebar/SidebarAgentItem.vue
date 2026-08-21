<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'

const props = defineProps({
  agent: {
    type: Object,
    required: true
  }
})

const route = useRoute()
const router = useRouter()
const agentStore = useAgentStore()

const isActive = computed(() =>
  route.params.agentId === props.agent.id
)

const handleClick = () => {
  if (props.agent.enabled === false) return
  agentStore.setActiveAgent(props.agent.id)
  agentStore.requestFocus()
  router.push(`/chat/${props.agent.id}`)
}
</script>

<template>
  <button
    :class="['agent-item', { 'is-active': isActive, 'is-disabled': agent.enabled === false }]"
    :disabled="agent.enabled === false"
    @click="handleClick"
  >
    <span class="active-bar" />
    <span class="agent-icon">
      <el-icon :size="20"><component :is="agent.icon" /></el-icon>
    </span>
    <span class="agent-info">
      <span class="agent-name">{{ agent.name }}</span>
      <span class="agent-category">{{ agent.enabled === false ? '待接入' : agent.category }}</span>
    </span>
  </button>
</template>

<style scoped>
.agent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 16px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--sidebar-text);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  position: relative;
  transition: background 0.2s;
}

.agent-item:hover {
  background: var(--sidebar-hover-bg);
}

.agent-item.is-disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.agent-item.is-active {
  background: var(--sidebar-active-bg);
}

.active-bar {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 24px;
  border-radius: 0 3px 3px 0;
  background: var(--el-color-primary);
  opacity: 0;
  transition: opacity 0.2s;
}

.agent-item.is-active .active-bar {
  opacity: 1;
}

.agent-icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  color: #fff;
  border-radius: 10px;
  background: rgba(15, 108, 189, 0.4);
  place-items: center;
  transition: background 0.2s;
}

.agent-item.is-active .agent-icon {
  background: var(--el-color-primary);
}

.agent-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--sidebar-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-category {
  font-size: 11px;
  color: var(--sidebar-text-muted);
}
</style>
