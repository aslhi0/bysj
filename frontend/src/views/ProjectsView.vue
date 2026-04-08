<script setup>
import { onMounted, reactive, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { apiFetch } from '../api'
import { useCurrentUser } from '../auth'
import PageToolbar from '../components/PageToolbar.vue'

const loading = ref(false)
const rows = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const searchQuery = ref('')
const form = reactive({ name: '', description: '', webhook_url: '' })
const membersDialogVisible = ref(false)
const memberLoading = ref(false)
const currentProject = ref(null)
const members = ref([])
const userOptions = ref([])
const userQuery = ref('')
const selectedUserId = ref(null)
const { isAdminUser } = useCurrentUser()

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

const userOptionsFiltered = computed(() => {
  const q = userQuery.value.trim().toLowerCase()
  if (!q) return userOptions.value
  return userOptions.value.filter(u => u.username.toLowerCase().includes(q))
})

function openCreate() {
  if (!isAdminUser.value) return
  isEdit.value = false
  editId.value = null
  form.name = ''
  form.description = ''
  form.webhook_url = ''
  dialogVisible.value = true
}

function openEdit(row) {
  if (!isAdminUser.value) return
  isEdit.value = true
  editId.value = row.id
  form.name = row.name
  form.description = row.description
  form.webhook_url = row.webhook_url || ''
  dialogVisible.value = true
}

async function submit() {
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可管理项目')
    return
  }
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
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可管理项目')
    return
  }
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

async function openMembers(row) {
  if (!isAdminUser.value) return
  currentProject.value = row
  membersDialogVisible.value = true
  userQuery.value = ''
  selectedUserId.value = null
  await Promise.all([loadMembers(), loadUsers()])
}

async function loadMembers() {
  if (!currentProject.value) return
  memberLoading.value = true
  try {
    const res = await apiFetch(`/api/projects/${currentProject.value.id}/members/`)
    if (!res.ok) {
      ElMessage.error('加载成员失败')
      return
    }
    members.value = await res.json()
  } finally {
    memberLoading.value = false
  }
}

async function loadUsers() {
  const q = encodeURIComponent(userQuery.value.trim())
  const res = await apiFetch(`/api/auth/users/${q ? `?q=${q}` : ''}`)
  if (!res.ok) {
    ElMessage.error('加载用户列表失败')
    return
  }
  userOptions.value = await res.json()
}

async function addMember() {
  if (!currentProject.value || !selectedUserId.value) {
    ElMessage.warning('请选择用户')
    return
  }
  const res = await apiFetch(`/api/projects/${currentProject.value.id}/add_member/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: selectedUserId.value }),
  })
  if (!res.ok) {
    ElMessage.error('添加成员失败')
    return
  }
  ElMessage.success('成员已添加')
  selectedUserId.value = null
  await loadMembers()
}

async function removeMember(row) {
  if (!currentProject.value) return
  const res = await apiFetch(`/api/projects/${currentProject.value.id}/remove_member/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: row.user }),
  })
  if (!res.ok) {
    ElMessage.error('移除成员失败')
    return
  }
  ElMessage.success('成员已移除')
  await loadMembers()
}
</script>

<template>
  <div>
    <PageToolbar :center-y="true">
      <template #left>
        <el-button v-if="isAdminUser" type="primary" @click="openCreate">新建项目</el-button>
      </template>
      <template #right>
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
      </template>
    </PageToolbar>
    
    <el-table v-loading="loading" :data="filteredRows" stripe class="page-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="160">
        <template #default="{ row }">
          <span style="font-weight: bold; color: var(--el-color-primary)">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column v-if="isAdminUser" label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button type="success" link @click="openMembers(row)">成员</el-button>
          <el-button type="danger" link @click="removeRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-if="isAdminUser" v-model="dialogVisible" :title="isEdit ? '编辑项目' : '新建项目'" width="480px" destroy-on-close>
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

    <el-dialog
      v-if="isAdminUser"
      v-model="membersDialogVisible"
      :title="`项目成员管理 - ${currentProject?.name || ''}`"
      width="640px"
      destroy-on-close
    >
      <div style="display: flex; gap: 8px; margin-bottom: 12px">
        <el-input
          v-model="userQuery"
          placeholder="搜索用户名"
          clearable
          style="width: 220px"
          @change="loadUsers"
        />
        <el-select v-model="selectedUserId" filterable placeholder="选择用户" style="flex: 1">
          <el-option
            v-for="u in userOptionsFiltered"
            :key="u.id"
            :label="`${u.username}${u.is_staff || u.is_superuser ? ' (管理员)' : ''}`"
            :value="u.id"
          />
        </el-select>
        <el-button type="primary" @click="addMember">添加成员</el-button>
      </div>

      <el-table v-loading="memberLoading" :data="members" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="180" />
        <el-table-column prop="created_at" label="加入时间" min-width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link @click="removeMember(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="membersDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>
