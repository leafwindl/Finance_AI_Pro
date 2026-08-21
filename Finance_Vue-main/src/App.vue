<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'
import { useAgentStore } from '@/stores/agents'
import AppSidebar from '@/components/sidebar/AppSidebar.vue'
import GlobalAssistant from '@/components/GlobalAssistant.vue'

const route = useRoute()
const themeStore = useThemeStore()
const userStore = useUserStore()
const agentStore = useAgentStore()

const hideSidebar = computed(() => route.path === '/login')

onMounted(async () => {
  themeStore.initTheme()
  agentStore.loadAgents()
  if (!userStore.initialized) await userStore.init()
  if (userStore.isLoggedIn) {
    await agentStore.loadAgentCapabilities()
    try {
      await agentStore.syncAllRemoteConversations()
    } catch {
      // 聊天页仍可显示，具体 API 错误由对应操作提示。
    }
  }
})
</script>

<template>
  <div class="app-shell">
    <AppSidebar v-if="!hideSidebar" />
    <main class="main-area">
      <RouterView />
    </main>
    <GlobalAssistant />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--el-bg-color-page);
}

.main-area {
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow: hidden;
}
</style>
