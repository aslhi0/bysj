<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(false)
const rows = ref([])
const dialogVisible = ref(false)
const form = reactive({ name: '', description: '' })

async function load() {
  loading.value = true
  try {
    const res = await fetch('/api/projects/')
    rows.value = await res.json()
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCreate() {
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写项目名称')
    return
  }
  const res = await fetch('/api/projects/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: form.name.trim(),
      description: form.description.trim(),
    }),
  })
  if (!res.ok) {
    ElMessage.error('创建失败')
    return
  }
  ElMessage.success('已创建')
  dialogVisible.value = false
  load()
}

async function removeRow(row) {
  await ElMessageBox.confirm(`确定删除项目「${row.name}」？关联用例将一并删除。`, '确认', {
    type: 'warning',
  })
  const res = await fetch(`/api/projects/${row.id}/`, { method: 'DELETE' })
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
    <div style="margin-bottom: 16px">
      <el-button type="primary" @click="openCreate">新建项目</el-button>
    </div>
    <el-table v-loading="loading" :data="rows" stripe style="width: 100%; max-width: 960px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link @click="removeRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建项目" width="480px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如：电商回归" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
