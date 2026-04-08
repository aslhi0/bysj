<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiFetch, setTokens } from '../api'
import { loadCurrentUser, resetCurrentUserCache } from '../auth'

const router = useRouter()
const mode = ref('login')
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

async function submit() {
  const username = form.username.trim()
  const password = form.password
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
    // 切换账号后强制刷新角色缓存，避免沿用上一次登录身份。
    resetCurrentUserCache()
    setTokens({ access: data.access, refresh: data.refresh })
    await loadCurrentUser(true)
    await router.replace('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="bg-glow bg-glow-left" />
    <div class="bg-glow bg-glow-right" />
    <el-card class="card" shadow="never">
      <div class="brand">AutoTest Platform</div>
      <div class="title">欢迎回来</div>
      <div class="subtitle">自动化测试平台 · 稳定、清晰、高效</div>

      <el-radio-group v-model="mode" class="mode-switch">
        <el-radio-button value="login">登录</el-radio-button>
        <el-radio-button value="register">注册</el-radio-button>
      </el-radio-group>

      <el-form class="login-form" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" autocomplete="username" placeholder="请输入用户名" size="large" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            placeholder="请输入密码"
            size="large"
          />
        </el-form-item>
        <el-button type="primary" :loading="loading" class="submit-btn" @click="submit">
          {{ mode === 'login' ? '登录' : '注册' }}
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  --lp-title: #0f172a;
  --lp-subtitle: #64748b;
  --lp-brand-text: #1d4ed8;
  --lp-brand-bg: rgba(59, 130, 246, 0.12);
  --lp-card-bg: rgba(255, 255, 255, 0.86);
  --lp-card-border: rgba(255, 255, 255, 0.7);
  --lp-card-shadow: 0 18px 45px rgba(18, 38, 63, 0.12);
  --lp-glow-left: rgba(59, 130, 246, 0.45);
  --lp-glow-right: rgba(99, 102, 241, 0.4);

  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow: hidden;
  background:
    radial-gradient(circle at 15% 20%, rgba(64, 158, 255, 0.14), transparent 35%),
    radial-gradient(circle at 85% 80%, rgba(103, 194, 58, 0.12), transparent 35%),
    linear-gradient(135deg, #f5f8ff 0%, #f8f9fc 45%, #f3f6ff 100%);
}

.card {
  position: relative;
  z-index: 2;
  width: 440px;
  max-width: 100%;
  border-radius: 16px;
  border: 1px solid var(--lp-card-border);
  background: var(--lp-card-bg);
  backdrop-filter: blur(8px);
  box-shadow: var(--lp-card-shadow);
  transition: transform 0.22s ease, box-shadow 0.22s ease;
}

.card:hover {
  transform: translateY(-2px);
}

.brand {
  display: inline-flex;
  padding: 4px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--lp-brand-text);
  border-radius: 999px;
  background: var(--lp-brand-bg);
  margin-bottom: 12px;
}

.title {
  font-size: 34px;
  font-weight: 800;
  color: var(--lp-title);
  letter-spacing: 0.2px;
}

.subtitle {
  margin-top: 4px;
  margin-bottom: 18px;
  font-size: 16px;
  font-weight: 500;
  color: var(--lp-subtitle);
}

.mode-switch {
  width: 100%;
}

.mode-switch :deep(.el-radio-button__inner) {
  background: transparent;
  border-color: rgba(148, 163, 184, 0.35);
  color: var(--lp-subtitle);
  font-size: 15px;
  font-weight: 600;
  min-width: 92px;
}

.mode-switch :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  color: #fff;
  border-color: var(--el-color-primary);
  box-shadow: -1px 0 0 0 var(--el-color-primary);
}

.login-form {
  margin-top: 16px;
}

.login-form :deep(.el-form-item__label) {
  font-size: 16px;
  font-weight: 600;
  color: var(--lp-subtitle);
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.25) inset;
  transition: box-shadow 0.2s ease, background-color 0.2s ease;
}

.login-form :deep(.el-input__inner) {
  font-size: 16px;
  font-weight: 500;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px rgba(59, 130, 246, 0.55) inset,
    0 0 0 3px rgba(59, 130, 246, 0.12);
}

.submit-btn {
  width: 100%;
  margin-top: 4px;
  height: 42px;
  border-radius: 10px;
}

.submit-btn :deep(span) {
  font-size: 17px;
  font-weight: 700;
}

.bg-glow {
  position: absolute;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.45;
  pointer-events: none;
  z-index: 1;
}

.bg-glow-left {
  left: -80px;
  top: 80px;
  background: var(--lp-glow-left);
}

.bg-glow-right {
  right: -100px;
  bottom: 40px;
  background: var(--lp-glow-right);
}

@media (prefers-color-scheme: dark) {
  .login-page {
    --lp-title: #e2e8f0;
    --lp-subtitle: #94a3b8;
    --lp-brand-text: #93c5fd;
    --lp-brand-bg: rgba(59, 130, 246, 0.2);
    --lp-card-bg: rgba(15, 23, 42, 0.72);
    --lp-card-border: rgba(148, 163, 184, 0.18);
    --lp-card-shadow: 0 20px 52px rgba(2, 6, 23, 0.45);
    --lp-glow-left: rgba(37, 99, 235, 0.35);
    --lp-glow-right: rgba(79, 70, 229, 0.32);

    background:
      radial-gradient(circle at 18% 20%, rgba(37, 99, 235, 0.2), transparent 38%),
      radial-gradient(circle at 82% 78%, rgba(99, 102, 241, 0.18), transparent 36%),
      linear-gradient(135deg, #0b1020 0%, #0f172a 45%, #111827 100%);
  }

  .mode-switch :deep(.el-radio-button__inner) {
    border-color: rgba(148, 163, 184, 0.28);
  }

  .login-form :deep(.el-input__wrapper) {
    background: rgba(15, 23, 42, 0.45);
    box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.22) inset;
  }

  .login-form :deep(.el-input__inner) {
    color: #e2e8f0;
  }
}

@media (max-width: 640px) {
  .title {
    font-size: 30px;
  }

  .subtitle {
    font-size: 14px;
  }
}
</style>
