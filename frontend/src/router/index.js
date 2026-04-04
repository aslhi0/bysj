import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '../api'

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
    path: '/schedules',
    name: 'schedules',
    component: () => import('../views/SchedulesView.vue'),
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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.path === '/login') return true
  const token = getAccessToken()
  if (!token) return { path: '/login', query: { redirect: to.fullPath } }
  return true
})

export default router
