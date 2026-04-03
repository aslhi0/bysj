<script setup>
import { onMounted, ref } from 'vue'

const apiStatus = ref('加载中…')
const apiOk = ref(false)

onMounted(async () => {
  try {
    const res = await fetch('/api/health/')
    const data = await res.json()
    if (res.ok && data.status === 'ok') {
      apiOk.value = true
      apiStatus.value = `后端已连通：${data.service}`
    } else {
      apiStatus.value = '后端响应异常'
    }
  } catch {
    apiStatus.value = '无法连接后端（请先启动 Django: python manage.py runserver）'
  }
})
</script>

<template>
  <div>
    <el-alert
      :title="apiStatus"
      :type="apiOk ? 'success' : 'warning'"
      show-icon
      style="margin-bottom: 20px; max-width: 640px"
    />
    <p style="color: var(--el-text-color-secondary); line-height: 1.6">
      流程建议：测试项目 → 测试用例（支持 HTTP/UI 混跑、OpenAPI 导入、<strong>单条执行历史</strong>）→
      <strong>测试套件</strong>按顺序批量同步执行，可选遇败即停。调度与报告可在后续接入 Celery / Allure。
    </p>
  </div>
</template>
