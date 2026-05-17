<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Delete, Edit } from '@element-plus/icons-vue'
import { apiFetch } from '../api'
import { useCurrentUser } from '../auth'

const loading = ref(false)
const envs = ref([])
const projects = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const searchQuery = ref('')
const filterProject = ref(null)
const { isAdminUser } = useCurrentUser()

const form = reactive({
  project: null,
  name: '',
  base_url: '',
  variablesJson: '{}',
  dbConfigJson: '{}',
  is_default: false
})

const filteredEnvs = computed(() => {
  let res = envs.value
  if (filterProject.value) {
    res = res.filter(e => e.project === filterProject.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    res = res.filter(e => e.name.toLowerCase().includes(q) || e.base_url.toLowerCase().includes(q))
  }
  return res
})

const projectOptions = computed(() => 
  projects.value.map(p => ({ label: p.name, value: p.id }))
)

async function loadProjects() {
  const res = await apiFetch('/api/projects/')
  projects.value = await res.json()
}

async function loadEnvs() {
  loading.value = true
  try {
    const res = await apiFetch('/api/envs/')
    envs.value = await res.json()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  loadEnvs()
})

function openCreate() {
  if (!isAdminUser.value) return
  isEdit.value = false
  editId.value = null
  form.project = projectOptions.value[0]?.value || null
  form.name = ''
  form.base_url = ''
  form.variablesJson = '{}'
  form.dbConfigJson = '{}'
  form.is_default = false
  dialogVisible.value = true
}

function openEdit(row) {
  if (!isAdminUser.value) return
  isEdit.value = true
  editId.value = row.id
  form.project = row.project
  form.name = row.name
  form.base_url = row.base_url
  form.variablesJson = JSON.stringify(row.variables || {}, null, 2)
  form.dbConfigJson = JSON.stringify(row.db_config || {}, null, 2)
  form.is_default = row.is_default
  dialogVisible.value = true
}

async function submit() {
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可管理环境配置')
    return
  }
  if (!form.project) return ElMessage.warning('请选择项目')
  if (!form.name.trim()) return ElMessage.warning('请填写环境名称')
  
  let variables
  try {
    variables = JSON.parse(form.variablesJson || '{}')
  } catch {
    return ElMessage.error('环境变量须为合法 JSON 对象')
  }
  let db_config
  try {
    db_config = JSON.parse(form.dbConfigJson || '{}')
  } catch {
    return ElMessage.error('数据库配置须为合法 JSON 对象')
  }

  const url = isEdit.value ? `/api/envs/${editId.value}/` : '/api/envs/'
  const method = isEdit.value ? 'PUT' : 'POST'

  const res = await apiFetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project: form.project,
      name: form.name.trim(),
      base_url: form.base_url.trim(),
      variables,
      db_config,
      is_default: form.is_default
    })
  })

  if (res.ok) {
    ElMessage.success(isEdit.value ? '已更新' : '已创建')
    dialogVisible.value = false
    loadEnvs()
  } else {
    ElMessage.error('保存失败')
  }
}

async function removeEnv(row) {
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可管理环境配置')
    return
  }
  try {
    await ElMessageBox.confirm('确定删除该环境配置吗？', '警告', { type: 'warning' })
    const res = await apiFetch(`/api/envs/${row.id}/`, {
      method: 'DELETE',
    })
    if (res.ok) {
      ElMessage.success('已删除')
      loadEnvs()
    }
  } catch {
    // 用户取消删除时不需要提示。
  }
}
</script>

<template>
  <div class="envs-view">
    <div class="page-header">
      <div class="left">
        <el-button v-if="isAdminUser" type="primary" :icon="Plus" @click="openCreate">新建环境</el-button>
      </div>
      <div class="right">
        <el-select v-model="filterProject" placeholder="按项目筛选" clearable style="width: 180px">
          <el-option v-for="p in projectOptions" :key="p.value" :label="p.label" :value="p.value" />
        </el-select>
        <el-input v-model="searchQuery" placeholder="搜索环境名称..." clearable style="width: 220px; margin-left: 12px">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </div>

    <el-table v-loading="loading" :data="filteredEnvs" stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="环境名称" min-width="120">
        <template #default="{ row }">
          <span style="font-weight: 500">{{ row.name }}</span>
          <el-tag v-if="row.is_default" size="small" type="success" style="margin-left: 8px">默认</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="base_url" label="基础 URL" min-width="200" show-overflow-tooltip />
      <el-table-column v-if="isAdminUser" label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button type="danger" link :icon="Delete" @click="removeEnv(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-if="isAdminUser" v-model="dialogVisible" :title="isEdit ? '编辑环境' : '新建环境'" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="所属项目" required>
          <el-select v-model="form.project" placeholder="请选择项目" style="width: 100%">
            <el-option v-for="p in projectOptions" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境名称" required>
          <el-input v-model="form.name" placeholder="如：测试环境、开发环境" />
        </el-form-item>
        <el-form-item label="基础 URL">
          <el-input v-model="form.base_url" placeholder="http://api.test.com" />
        </el-form-item>
        <el-form-item label="环境变量">
          <el-input v-model="form.variablesJson" type="textarea" :rows="5" placeholder='{"db_host": "127.0.0.1", "token": "xxx"}' />
        </el-form-item>
        <el-form-item label="数据库配置">
          <el-input v-model="form.dbConfigJson" type="textarea" :rows="4" placeholder='{"sqlite_path":"db.sqlite3"}' />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}
.left, .right {
  display: flex;
  align-items: center;
}
</style>
