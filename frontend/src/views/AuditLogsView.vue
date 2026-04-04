<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { apiFetch } from '../api'

const loading = ref(false)
const logs = ref([])

const filters = reactive({
  action: '',
  q: '',
})

const filtered = computed(() => {
  const q = (filters.q || '').trim().toLowerCase()
  const act = (filters.action || '').trim().toLowerCase()
  return logs.value.filter((r) => {
    if (act && String(r.action || '').toLowerCase() !== act) return false
    if (!q) return true
    const t = `${r.object_repr || ''} ${r.change_message || ''} ${r.content_type || ''}`.toLowerCase()
    return t.includes(q)
  })
})

function formatAction(a) {
  if (a === 'add') return '新增'
  if (a === 'change') return '修改'
  if (a === 'delete') return '删除'
  return a || '-'
}

async function loadLogs() {
  loading.value = true
  try {
    const url = `/api/audit-logs/?limit=500`
    const res = await apiFetch(url)
    const data = await res.json().catch(() => [])
    if (!res.ok) {
      return ElMessage.error(data.detail || '加载失败')
    }
    logs.value = Array.isArray(data) ? data : []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadLogs()
})
</script>

<template>
  <div class="audit-logs-view">
    <div class="page-header">
      <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap">
        <el-select v-model="filters.action" placeholder="操作类型" style="width: 160px" clearable>
          <el-option label="新增" value="add" />
          <el-option label="修改" value="change" />
          <el-option label="删除" value="delete" />
        </el-select>
        <el-input v-model="filters.q" placeholder="关键词：对象/内容/模型" style="width: 260px" clearable />
        <el-button @click="loadLogs">刷新</el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="filtered" stripe>
      <el-table-column prop="action_time" label="时间" width="180" />
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.action === 'delete' ? 'danger' : row.action === 'add' ? 'success' : 'warning'">
            {{ formatAction(row.action) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="content_type" label="模型" width="180" show-overflow-tooltip />
      <el-table-column prop="object_repr" label="对象" min-width="180" show-overflow-tooltip />
      <el-table-column prop="change_message" label="变更内容" min-width="260" show-overflow-tooltip />
    </el-table>
  </div>
</template>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
</style>
