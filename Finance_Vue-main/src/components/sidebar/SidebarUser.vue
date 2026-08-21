<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const themeStore = useThemeStore()
const userStore = useUserStore()

const themeIcon = computed(() => themeStore.isDark ? 'Sunny' : 'Moon')
const themeLabel = computed(() => themeStore.isDark ? '切换到浅色模式' : '切换到深色模式')

async function handleLogout() {
  await userStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="sidebar-user">
    <!-- 未登录 -->
    <div
      v-if="!userStore.isLoggedIn"
      class="user-info clickable"
      @click="router.push('/login')"
    >
      <span class="user-avatar">
        <el-icon :size="18"><UserFilled /></el-icon>
      </span>
      <span class="user-name">未登录</span>
    </div>

    <!-- 已登录 -->
    <div v-else class="user-info">
      <span class="user-avatar">
        <el-icon :size="18"><UserFilled /></el-icon>
      </span>
      <span class="user-name">{{ userStore.username }}</span>
      <button class="logout-btn" @click="handleLogout">退出</button>
    </div>

    <el-tooltip :content="themeLabel" placement="top">
      <button
        :aria-label="themeLabel"
        class="theme-btn"
        @click="themeStore.toggleTheme"
      >
        <el-icon :size="18"><component :is="themeIcon" /></el-icon>
      </button>
    </el-tooltip>
  </div>
</template>

<style scoped>
.sidebar-user {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-top: 1px solid var(--sidebar-border);
  flex-shrink: 0;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.user-info.clickable {
  cursor: pointer;
}

.user-info.clickable:hover .user-name {
  color: var(--el-color-primary);
}

.user-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  color: var(--sidebar-text-muted);
  border-radius: 50%;
  background: var(--sidebar-hover-bg);
  place-items: center;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--sidebar-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logout-btn {
  padding: 3px 8px;
  border: 1px solid var(--sidebar-border);
  border-radius: 4px;
  background: transparent;
  color: var(--sidebar-text-muted);
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
  transition: all 0.2s;
}

.logout-btn:hover {
  border-color: var(--el-color-danger);
  color: var(--el-color-danger);
}

.theme-btn {
  display: grid;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--sidebar-text-muted);
  cursor: pointer;
  place-items: center;
  transition: all 0.2s;
}

.theme-btn:hover {
  background: var(--sidebar-hover-bg);
  color: var(--sidebar-text);
}
</style>
