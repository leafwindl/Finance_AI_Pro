import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录' }
    },
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { title: '东方证券 - 仪表盘', requiresAuth: true }
    },
    {
      path: '/requirement-tracking',
      name: 'requirementTracking',
      component: () => import('@/views/RequirementTracking.vue'),
      meta: { title: '需求追踪', requiresAuth: true }
    },
    {
      path: '/chat/:agentId',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      props: true,
      meta: { title: '对话', requiresAuth: true }
    },
    {
      path: '/test-case/write',
      name: 'testCaseEditor',
      component: () => import('@/views/TestCaseEditor.vue'),
      meta: { title: '测试用例编写', requiresAuth: true }
    },
    {
      path: '/six-dim-report',
      name: 'sixDimReport',
      component: () => import('@/views/SixDimReportView.vue'),
      meta: { title: '六维分析报告', requiresAuth: true }
    },
    {
      path: '/knowledge-graph',
      name: 'knowledgeGraph',
      component: () => import('@/views/KnowledgeGraphView.vue'),
      meta: { title: '知识图谱', requiresAuth: true }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

router.beforeEach(async (to) => {
  const userStore = useUserStore()
  if (!userStore.initialized) await userStore.init()
  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && userStore.isLoggedIn) return { name: 'dashboard' }
  return true
})

export default router
