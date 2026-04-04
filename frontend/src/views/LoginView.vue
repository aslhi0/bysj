<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiFetch, setTokens } from '../api'

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
    setTokens({ access: data.access, refresh: data.refresh })
    await router.replace('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="card" shadow="always">
      <div class="title">AutoTest Platform</div>
      <el-radio-group v-model="mode">
        <el-radio-button value="login">登录</el-radio-button>
        <el-radio-button value="register">注册</el-radio-button>
      </el-radio-group>
      <el-form label-width="80px" style="margin-top: 16px" @submit.prevent="submit">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="submit">
          {{ mode === 'login' ? '登录' : '注册' }}
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-bg-color-page);
}

.card {
  width: 420px;
}

.title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 12px;
  text-align: center;
}
</style>
