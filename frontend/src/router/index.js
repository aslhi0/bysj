import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '../api'
import { loadCurrentUser } from '../auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
  },
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
  },
  {
    path: '/projects',
    name: 'projects',
    component: () => import('../views/ProjectsView.vue'),
  },
  {
    path: '/cases',
    name: 'cases',
    component: () => import('../views/CasesView.vue'),
  },
  {
    path: '/suites',
    name: 'suites',
    component: () => import('../views/SuitesView.vue'),
  },
  {
    path: '/envs',
    name: 'envs',
    component: () => import('../views/EnvsView.vue'),
  },
  {
    path: '/perf',
    name: 'perf',
    component: () => import('../views/PerfView.vue'),
  },
  {
    path: '/audit',
    name: 'audit',
    component: () => import('../views/AuditLogsView.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const adminOnlyPaths = new Set(['/envs', '/audit'])

router.beforeEach(async (to) => {
  if (to.path === '/login') return true
  const token = getAccessToken()
  if (!token) return { path: '/login', query: { redirect: to.fullPath } }
  if (adminOnlyPaths.has(to.path)) {
    const me = await loadCurrentUser()
    const isAdmin = Boolean(me && (me.is_staff || me.is_superuser))
    if (!isAdmin) return { path: '/' }
  }
  return true
})

export default router
