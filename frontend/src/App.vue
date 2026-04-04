<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { HomeFilled, Files, List, Collection, Operation as Odometer, Calendar, Monitor, DataLine } from '@element-plus/icons-vue'
import { clearTokens, getAccessToken } from './api'

const route = useRoute()
const router = useRouter()

const menuItems = [
  { path: '/', name: '首页', icon: HomeFilled, label: '概览' },
  { path: '/projects', name: 'projects', icon: Files, label: '测试项目' },
  { path: '/cases', name: 'cases', icon: List, label: '测试用例' },
  { path: '/suites', name: 'suites', icon: Collection, label: '测试套件' },
  { path: '/schedules', name: 'schedules', icon: Calendar, label: '定时任务' },
  { path: '/perf', name: 'perf', icon: DataLine, label: '性能测试' },
  { path: '/envs', name: 'envs', icon: Monitor, label: '环境配置' },
]

function parseJwtUsername(token) {
  try {
    const p = token.split('.')[1]
    const json = atob(p.replace(/-/g, '+').replace(/_/g, '/'))
    const obj = JSON.parse(decodeURIComponent(escape(json)))
    return obj.username || obj.user || obj.sub || ''
  } catch {
    return ''
  }
}

const username = computed(() => {
  const token = getAccessToken()
  const u = token ? parseJwtUsername(token) : ''
  return u || 'User'
})

const isLoginPage = computed(() => route.path === '/login')

function logout() {
  clearTokens()
  router.replace('/login')
}
</script>

<template>
  <router-view v-if="isLoginPage" />
  <el-container v-else class="layout-container">
    <el-aside width="220px" class="aside">
      <div class="logo-container">
        <el-icon :size="24" color="#409eff"><Odometer /></el-icon>
        <span class="logo-text">AutoTest Platform</span>
      </div>
      
      <el-menu
        :default-active="route.path"
        router
        class="menu"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.name === '首页' ? '项目首页' : item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">控制台</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.path !== '/'">{{ 
              menuItems.find(i => i.path === route.path)?.label || '详情' 
            }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-dropdown>
            <span class="user-info">
              <el-avatar :size="32" src="https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png" />
              <span class="username">{{ username }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item divided @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <div class="page-container">
          <router-view />
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100vh;
  background-color: var(--el-bg-color-page);
}

.aside {
  background-color: #001529;
  border-right: none;
  display: flex;
  flex-direction: column;
}

.logo-container {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background-color: #002140;
}

.logo-text {
  color: white;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.menu {
  border-right: none;
  background-color: transparent;
}

.menu :deep(.el-menu-item) {
  color: #a6adb4;
  height: 50px;
}

.menu :deep(.el-menu-item.is-active) {
  color: #fff;
  background-color: var(--el-color-primary) !important;
}

.menu :deep(.el-menu-item:hover) {
  color: #fff;
  background-color: rgba(255, 255, 255, 0.05);
}

.header {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.username {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.main-content {
  padding: 20px;
  overflow-y: auto;
}

.page-container {
  background-color: #fff;
  padding: 24px;
  border-radius: 8px;
  min-height: calc(100vh - 120px);
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}
</style>
