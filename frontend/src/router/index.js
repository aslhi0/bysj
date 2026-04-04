import { createRouter, createWebHistory } from 'vue-router'

const routes = [
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
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
