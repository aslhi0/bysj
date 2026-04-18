<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { HomeFilled, Files, List, Collection, Operation as Odometer, Monitor, DataLine, Document } from '@element-plus/icons-vue'
import { clearTokens, getAccessToken } from './api'
import { useCurrentUser } from './auth'
import { INNOVATION_TAGLINE, PLATFORM_NAME } from './branding'

const route = useRoute()
const router = useRouter()
const { currentUser, isAdminUser, loadCurrentUser, resetCurrentUserCache } = useCurrentUser()

const menuItems = [
  { path: '/', name: '首页', icon: HomeFilled, label: '概览' },
  { path: '/projects', name: 'projects', icon: Files, label: '测试项目' },
  { path: '/cases', name: 'cases', icon: List, label: '测试用例' },
  { path: '/suites', name: 'suites', icon: Collection, label: '测试套件' },
  { path: '/perf', name: 'perf', icon: DataLine, label: '性能测试' },
  { path: '/envs', name: 'envs', icon: Monitor, label: '环境配置', adminOnly: true },
  { path: '/audit', name: 'audit', icon: Document, label: '审计日志', adminOnly: true },
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

const visibleMenuItems = computed(() => menuItems.filter((item) => !item.adminOnly || isAdminUser.value))

const isLoginPage = computed(() => route.path === '/login')

onMounted(() => {
  loadCurrentUser()
})

function logout() {
  clearTokens()
  resetCurrentUserCache()
  router.replace('/login')
}
</script>

<template>
  <router-view v-if="isLoginPage" />
  <el-container v-else class="layout-container">
    <el-aside width="220px" class="aside">
      <div class="logo-container">
        <el-icon :size="24" color="#409eff"><Odometer /></el-icon>
        <div class="logo-brand">
          <span class="logo-text">{{ PLATFORM_NAME }}</span>
          <span class="logo-tagline">{{ INNOVATION_TAGLINE }}</span>
        </div>
      </div>
      
      <el-menu
        :default-active="route.path"
        router
        class="menu"
      >
        <el-menu-item v-for="item in visibleMenuItems" :key="item.path" :index="item.path">
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
              <el-tag size="small" :type="isAdminUser ? 'danger' : 'info'">{{ isAdminUser ? '管理员' : '普通用户' }}</el-tag>
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
  width: 100%;
  height: 100vh;
  background-color: var(--el-bg-color-page);
  overflow: hidden;
}

.aside {
  width: 220px;
  flex: 0 0 220px;
  background: linear-gradient(180deg, #001529 0%, #001223 100%);
  border-right: none;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.logo-container {
  min-height: 60px;
  padding: 10px 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background-color: #002140;
}

.logo-brand {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.logo-text {
  color: white;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.3px;
  line-height: 1.25;
}

.logo-tagline {
  color: rgba(255, 255, 255, 0.72);
  font-size: 10px;
  line-height: 1.3;
  font-weight: 400;
  letter-spacing: 0.02em;
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
  min-height: 60px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(6px);
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
  overflow-x: auto;
  overflow-y: auto;
}

.page-container {
  background-color: #fff;
  width: 100%;
  max-width: 100%;
  padding: 24px;
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 42, 0.05);
  min-height: calc(100vh - 140px);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
  transition: box-shadow 0.2s ease;
}

.page-container:hover {
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
}

@media (max-width: 1200px) {
  .aside {
    width: 180px;
    flex-basis: 180px;
  }

  .logo-text {
    font-size: 13px;
  }

  .logo-tagline {
    font-size: 9px;
  }

  .header {
    padding: 0 12px;
  }

  .main-content {
    padding: 12px;
  }

  .page-container {
    padding: 12px;
  }

  .username {
    display: none;
  }
}
</style>
