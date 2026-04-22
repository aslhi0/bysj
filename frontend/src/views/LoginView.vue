<script setup>
import { onMounted, onUnmounted, reactive, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { TrendCharts, Lightning, Finished } from '@element-plus/icons-vue'
import { apiFetch, setTokens } from '../api'
import { loadCurrentUser, resetCurrentUserCache } from '../auth'
import { PLATFORM_NAME, THESIS_TITLE_FULL } from '../branding'

const router = useRouter()
const route = useRoute()
const mode = ref('login')
const loading = ref(false)

const formModel = reactive({
  username: '',
  password: '',
})

const safeRedirect = computed(() => {
  const q = route.query.redirect
  if (typeof q !== 'string' || !q.startsWith('/') || q.startsWith('//')) return '/'
  return q
})

const heroPoints = [
  { icon: TrendCharts, text: 'Flaky 风险量化与趋势' },
  { icon: Lightning, text: '自适应重试与执行聚合' },
  { icon: Finished, text: '接口 · UI · 性能一体化' },
]

onMounted(() => {
  // 全局 body 在 style.css 中为 overflow:hidden，登录页在窄屏可能高于一屏，需允许整页滚动
  document.body.style.overflow = 'auto'
})

onUnmounted(() => {
  document.body.style.overflow = ''
})

async function submit() {
  const username = formModel.username.trim()
  const password = formModel.password
  if (!username || !password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'register') {
      const regRes = await apiFetch('/api/auth/register/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const regData = await regRes.json().catch(() => ({}))
      if (!regRes.ok) {
        ElMessage.error(regData.detail || '注册失败')
        return
      }
      ElMessage.success('注册成功，请登录')
      mode.value = 'login'
      return
    }

    const res = await apiFetch('/api/auth/token/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      ElMessage.error(data.detail || '登录失败')
      return
    }
    resetCurrentUserCache()
    setTokens({ access: data.access, refresh: data.refresh })
    await loadCurrentUser(true)
    await router.replace(safeRedirect.value)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="bg-base" aria-hidden="true" />
    <div class="bg-orb bg-orb-a" aria-hidden="true" />
    <div class="bg-orb bg-orb-b" aria-hidden="true" />
    <div class="bg-orb bg-orb-c" aria-hidden="true" />
    <div class="bg-grid" aria-hidden="true" />

    <div class="login-frame">
      <section class="hero" aria-label="产品说明">
        <div class="hero-inner">
          <h1 class="hero-title">{{ PLATFORM_NAME }}</h1>
          <p class="hero-thesis">
            {{ THESIS_TITLE_FULL }}
          </p>

          <ul class="hero-list">
            <li v-for="(item, i) in heroPoints" :key="i" class="hero-list-item">
              <span class="hero-list-icon" aria-hidden="true">
                <el-icon :size="18"><component :is="item.icon" /></el-icon>
              </span>
              <span class="hero-list-text">{{ item.text }}</span>
            </li>
          </ul>
        </div>
        <footer class="hero-foot">本地部署 · 数据不入公网</footer>
      </section>

      <section class="panel" aria-label="登录与注册">
        <div class="panel-card">
          <header class="panel-head">
            <h2 class="panel-title">{{ mode === 'login' ? '欢迎回来' : '创建账号' }}</h2>
            <p class="panel-desc">使用本机账号进入控制台，管理项目与用例</p>
          </header>

          <el-segmented
            v-model="mode"
            class="mode-seg"
            :options="[
              { label: '登录', value: 'login' },
              { label: '注册', value: 'register' },
            ]"
            block
            size="large"
          />

          <el-form
            class="login-form"
            label-position="top"
            :model="formModel"
            @submit.prevent="submit"
          >
            <el-form-item label="用户名" required>
              <el-input
                v-model="formModel.username"
                autocomplete="username"
                placeholder="用户名"
                size="large"
                clearable
              />
            </el-form-item>
            <el-form-item label="密码" required>
              <el-input
                v-model="formModel.password"
                type="password"
                show-password
                autocomplete="current-password"
                placeholder="密码"
                size="large"
                @keyup.enter="submit"
              />
            </el-form-item>
            <el-button
              type="primary"
              native-type="submit"
              :loading="loading"
              class="submit-btn"
            >
              {{ mode === 'login' ? '进入控制台' : '完成注册' }}
            </el-button>
          </el-form>

          <p class="panel-hint">登录后可从左侧导航使用项目、用例、套件与性能任务。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  --lp-navy-0: #060d18;
  --lp-navy-1: #0c1829;
  --lp-navy-2: #132337;
  --lp-accent: #3b82f6;
  --lp-accent-soft: rgba(59, 130, 246, 0.22);
  --lp-mint: #34d399;
  --lp-text: #e2e8f0;
  --lp-muted: #94a3b8;
  --lp-card: rgba(255, 255, 255, 0.78);
  --lp-card-border: rgba(255, 255, 255, 0.55);
  --lp-shadow: 0 25px 60px rgba(2, 8, 23, 0.35);

  position: relative;
  min-height: 100vh;
  width: 100%;
  overflow: hidden;
  color: var(--lp-text);
  background: var(--lp-navy-0);
}

.bg-base {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse 80% 60% at 20% 20%, rgba(59, 130, 246, 0.15), transparent 55%),
    radial-gradient(ellipse 70% 50% at 80% 70%, rgba(52, 211, 153, 0.1), transparent 50%),
    linear-gradient(165deg, var(--lp-navy-0) 0%, var(--lp-navy-1) 40%, #0a1424 100%);
  pointer-events: none;
}

.bg-grid {
  position: absolute;
  inset: 0;
  opacity: 0.35;
  background-image: linear-gradient(rgba(148, 163, 184, 0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.12) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 70% 60% at 50% 40%, #000 20%, transparent 70%);
  pointer-events: none;
}

.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(64px);
  pointer-events: none;
  will-change: transform, opacity;
}

.bg-orb-a {
  width: 420px;
  height: 420px;
  left: -12%;
  top: 10%;
  background: rgba(59, 130, 246, 0.45);
  animation: lp-float 18s ease-in-out infinite;
}

.bg-orb-b {
  width: 360px;
  height: 360px;
  right: -8%;
  bottom: 8%;
  background: rgba(99, 102, 241, 0.35);
  animation: lp-float 22s ease-in-out infinite reverse;
}

.bg-orb-c {
  width: 280px;
  height: 280px;
  left: 40%;
  top: 55%;
  background: rgba(52, 211, 153, 0.2);
  animation: lp-float 26s ease-in-out 2s infinite;
}

.login-frame {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(360px, 0.95fr);
  min-height: 100vh;
  max-width: 1200px;
  margin: 0 auto;
}

.hero {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: clamp(2rem, 4vw, 3.5rem) clamp(1.5rem, 3vw, 2.5rem) 2rem;
  border-right: 1px solid rgba(148, 163, 184, 0.12);
}

.hero-inner {
  max-width: 32rem;
}

.hero-title {
  margin: 0 0 0.75rem;
  font-size: clamp(1.75rem, 2.4vw, 2.25rem);
  font-weight: 800;
  letter-spacing: 0.02em;
  line-height: 1.25;
  text-shadow: 0 1px 24px rgba(15, 23, 42, 0.5);
}

.hero-thesis {
  margin: 0 0 1.5rem;
  font-size: 0.9375rem;
  line-height: 1.65;
  color: var(--lp-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.hero-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.hero-list-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  font-size: 0.9rem;
  color: #cbd5e1;
}

.hero-list-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.15);
  color: #7dd3fc;
  flex-shrink: 0;
}

.hero-list-text {
  line-height: 1.45;
}

.hero-foot {
  margin-top: auto;
  padding-top: 2rem;
  font-size: 0.75rem;
  color: rgba(148, 163, 184, 0.65);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1.5rem, 3vw, 2.5rem) clamp(1rem, 2.5vw, 2rem);
  background: linear-gradient(180deg, rgba(6, 13, 24, 0.2) 0%, transparent 30%);
}

.panel-card {
  width: 100%;
  max-width: 28rem;
  padding: 2rem 1.75rem 1.75rem;
  border-radius: 20px;
  background: var(--lp-card);
  border: 1px solid var(--lp-card-border);
  box-shadow: var(--lp-shadow);
  backdrop-filter: blur(16px) saturate(160%);
  -webkit-backdrop-filter: blur(16px) saturate(160%);
}

.panel-head {
  margin-bottom: 1.25rem;
}

.panel-title {
  margin: 0 0 0.35rem;
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: #0f172a;
}

.panel-desc {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
  color: #64748b;
}

.mode-seg {
  width: 100%;
  margin-bottom: 1.25rem;
}

.mode-seg :deep(.el-segmented) {
  --el-border-radius-base: 12px;
  padding: 4px;
  background: rgba(241, 245, 249, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.mode-seg :deep(.el-segmented__item) {
  font-weight: 700;
  font-size: 0.95rem;
}

.mode-seg :deep(.el-segmented__item-selected) {
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.login-form {
  margin-top: 0.25rem;
}

.login-form :deep(.el-form-item__label) {
  font-size: 0.875rem;
  font-weight: 700;
  color: #475569;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.28) inset;
  transition: box-shadow 0.2s ease, background 0.2s ease;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--lp-accent) inset, 0 0 0 3px var(--lp-accent-soft);
}

.submit-btn {
  width: 100%;
  margin-top: 0.5rem;
  height: 46px;
  border-radius: 12px;
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  border: none;
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.35);
  transition: transform 0.15s ease, box-shadow 0.2s ease;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.42);
}

.panel-hint {
  margin: 1.1rem 0 0;
  font-size: 0.75rem;
  line-height: 1.5;
  color: #94a3b8;
  text-align: center;
}

@media (prefers-reduced-motion: reduce) {
  .bg-orb-a,
  .bg-orb-b,
  .bg-orb-c {
    animation: none;
  }
}

@keyframes lp-float {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
    opacity: 0.9;
  }
  50% {
    transform: translate(2%, 3%) scale(1.04);
    opacity: 0.7;
  }
}

@media (max-width: 960px) {
  .login-frame {
    grid-template-columns: 1fr;
  }

  .hero {
    border-right: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    min-height: auto;
    padding-bottom: 1.5rem;
  }

  .hero-thesis {
    -webkit-line-clamp: 3;
  }

  .hero-foot {
    display: none;
  }
}

@media (max-width: 480px) {
  .panel-card {
    padding: 1.5rem 1.15rem 1.35rem;
  }

  .hero-title {
    font-size: 1.5rem;
  }
}
</style>
