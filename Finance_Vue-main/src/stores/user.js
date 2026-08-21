import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe, login as apiLogin, register as apiRegister, logout as apiLogout } from '@/services/api/auth'
import { useAgentStore } from '@/stores/agents'

export const useUserStore = defineStore('user', () => {
  const user = ref(null)       // { name: 'zhangsan' } 或 null
  const loading = ref(false)   // 恢复登录态中
  const initialized = ref(false)

  const isLoggedIn = computed(() => !!user.value)
  const username = computed(() => user.value?.name || '')

  async function init() {
    loading.value = true
    try {
      const data = await getMe()
      user.value = data
      useAgentStore().setUserScope(data.user_id)
    } catch {
      user.value = null
      useAgentStore().clearUserScope()
    } finally {
      loading.value = false
      initialized.value = true
    }
  }

  async function login(name, password) {
    const data = await apiLogin(name, password)
    user.value = data.user
    const agentStore = useAgentStore()
    agentStore.setUserScope(data.user.user_id)
    agentStore.loadAgents()
    await agentStore.loadAgentCapabilities()
    await agentStore.syncAllRemoteConversations()
  }

  async function register(name, email, password) {
    const data = await apiRegister(name, email, password)
    user.value = data.user
    const agentStore = useAgentStore()
    agentStore.setUserScope(data.user.user_id)
    agentStore.loadAgents()
    await agentStore.loadAgentCapabilities()
    await agentStore.syncAllRemoteConversations()
  }

  async function logout() {
    await apiLogout()
    useAgentStore().clearUserScope()
    user.value = null
  }

  return { user, loading, initialized, isLoggedIn, username, init, login, register, logout }
})
