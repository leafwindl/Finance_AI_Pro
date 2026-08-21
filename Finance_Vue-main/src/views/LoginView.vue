<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const mode = ref('login')

const loginName = ref('')
const loginPassword = ref('')

const regName = ref('')
const regEmail = ref('')
const regPassword = ref('')

const firstInputRef = ref(null)
const error = ref('')
const submitting = ref(false)

async function handleLogin() {
  if (!loginName.value.trim() || !loginPassword.value) {
    error.value = '请填写用户名和密码'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    await userStore.login(loginName.value.trim(), loginPassword.value)
    router.push(typeof router.currentRoute.value.query.redirect === 'string'
      ? router.currentRoute.value.query.redirect
      : '/')
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}

async function handleRegister() {
  if (!regName.value.trim() || !regEmail.value.trim() || !regPassword.value) {
    error.value = '请填写所有字段'
    return
  }
  if (regPassword.value.length < 6) {
    error.value = '密码最少 6 位'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    await userStore.register(regName.value.trim(), regEmail.value.trim(), regPassword.value)
    router.push(typeof router.currentRoute.value.query.redirect === 'string'
      ? router.currentRoute.value.query.redirect
      : '/')
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}

function switchMode() {
  error.value = ''
  mode.value = mode.value === 'login' ? 'register' : 'login'
  nextTick(() => firstInputRef.value?.focus())
}

onMounted(() => firstInputRef.value?.focus())
</script>

<template>
  <div class="login-page">
    <router-link to="/" class="back-link">← 返回首页</router-link>

    <div class="login-card">
      <h2 class="title">{{ mode === 'login' ? '登录' : '注册' }}</h2>

      <template v-if="mode === 'login'">
        <el-input ref="firstInputRef" v-model="loginName" placeholder="用户名" class="field" />
        <el-input
          v-model="loginPassword"
          type="password"
          placeholder="密码"
          show-password
          class="field"
          @keydown.enter="handleLogin"
        />
        <div v-if="error" class="error-msg">{{ error }}</div>
        <el-button type="primary" :loading="submitting" class="submit-btn" @click="handleLogin">登录</el-button>
        <div class="switch-text">没有账号？<span class="link" @click="switchMode">去注册</span></div>
      </template>

      <template v-else>
        <el-input ref="firstInputRef" v-model="regName" placeholder="用户名" class="field" />
        <el-input v-model="regEmail" placeholder="邮箱" class="field" />
        <el-input v-model="regPassword" type="password" placeholder="密码（最少6位）" show-password class="field" />
        <div v-if="error" class="error-msg">{{ error }}</div>
        <el-button type="primary" :loading="submitting" class="submit-btn" @click="handleRegister">注册</el-button>
        <div class="switch-text">已有账号？<span class="link" @click="switchMode">去登录</span></div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: var(--el-bg-color-page);
  position: relative;
}

.back-link {
  position: absolute;
  top: 24px;
  left: 28px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
  text-decoration: none;
}

.back-link:hover {
  color: var(--el-color-primary);
}

.login-card {
  width: 380px;
  padding: 40px 36px;
  border-radius: 12px;
  background: var(--el-bg-color);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
}

.title {
  margin: 0 0 28px;
  font-size: 22px;
  font-weight: 700;
  text-align: center;
  color: var(--el-text-color-primary);
}

.field { margin-bottom: 14px; }
.submit-btn { width: 100%; }
.error-msg { color: var(--el-color-danger); font-size: 12px; margin-bottom: 10px; }

.switch-text {
  text-align: center;
  margin-top: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.link { color: var(--el-color-primary); cursor: pointer; }
</style>
