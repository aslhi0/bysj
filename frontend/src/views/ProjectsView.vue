<script setup>
import { onMounted, reactive, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { apiFetch } from '../api'

const loading = ref(false)
const rows = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const searchQuery = ref('')
const form = reactive({ name: '', description: '', webhook_url: '' })

const filteredRows = computed(() => {
  if (!searchQuery.value) return rows.value
  const q = searchQuery.value.toLowerCase()
  return rows.value.filter(r => 
    r.name.toLowerCase().includes(q) || 
    (r.description && r.description.toLowerCase().includes(q))
  )
})

async function load() {
  loading.value = true
  try {
    const res = await apiFetch('/api/projects/')
    rows.value = await res.json()
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCreate() {
  isEdit.value = false
  editId.value = null
  form.name = ''
  form.description = ''
  form.webhook_url = ''
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  editId.value = row.id
  form.name = row.name
  form.description = row.description
  form.webhook_url = row.webhook_url || ''
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写项目名称')
    return
  }
  
  const url = isEdit.value ? `/api/projects/${editId.value}/` : '/api/projects/'
  const method = isEdit.value ? 'PUT' : 'POST'

  const res = await apiFetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: form.name.trim(),
      description: form.description.trim(),
      webhook_url: form.webhook_url.trim(),
    }),
  })
  if (!res.ok) {
    ElMessage.error(isEdit.value ? '修改失败' : '创建失败')
    return
  }
  ElMessage.success(isEdit.value ? '已修改' : '已创建')
  dialogVisible.value = false
  load()
}

async function removeRow(row) {
  await ElMessageBox.confirm(`确定删除项目「${row.name}」？关联用例将一并删除。`, '确认', {
    type: 'warning',
  })
  const res = await apiFetch(`/api/projects/${row.id}/`, {
    method: 'DELETE',
  })
  if (res.status === 204 || res.ok) {
    ElMessage.success('已删除')
    load()
  } else {
    ElMessage.error('删除失败')
  }
}
</script>

<template>
  <div>
    <div style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; max-width: 960px">
      <el-button type="primary" @click="openCreate">新建项目</el-button>
      <el-input
        v-model="searchQuery"
        placeholder="搜索项目名称或描述..."
        clearable
        style="width: 280px"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>
    
    <el-table v-loading="loading" :data="filteredRows" stripe style="width: 100%; max-width: 960px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="160">
        <template #default="{ row }">
          <span style="font-weight: bold; color: var(--el-color-primary)">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button type="danger" link @click="removeRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑项目' : '新建项目'" width="480px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如：电商回归" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" rows="2" />
        </el-form-item>
        <el-form-item label="Webhook">
          <el-input v-model="form.webhook_url" placeholder="钉钉/企微机器人地址" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
