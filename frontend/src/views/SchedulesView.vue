<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Edit, Calendar, Timer } from '@element-plus/icons-vue'
import { apiFetch } from '../api'

const loading = ref(false)
const schedules = ref([])
const crontabs = ref([])
const suites = ref([])
const cases = ref([])
const envs = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const quickDialogVisible = ref(false)

const form = reactive({
  name: '',
  task: 'api.tasks.run_test_suite_task',
  crontab: null,
  args: '[]',
  kwargs: '{}',
  enabled: true,
  description: ''
})

const quickForm = reactive({
  type: 'suite',
  targetId: null,
  envId: null,
  crontabId: null,
  enabled: true,
  stop_on_failure: false,
  variablesJson: '{}',
  name: '',
})

const crontabForm = reactive({
  minute: '*',
  hour: '*',
  day_of_week: '*',
  day_of_month: '*',
  month_of_year: '*'
})
const crontabDialogVisible = ref(false)

async function loadSchedules() {
  loading.value = true
  try {
    const res = await apiFetch('/api/schedules/')
    schedules.value = await res.json()
  } finally {
    loading.value = false
  }
}

async function loadCrontabs() {
  const res = await apiFetch('/api/crontabs/')
  crontabs.value = await res.json()
}

async function loadSuites() {
  const res = await apiFetch('/api/suites/')
  suites.value = await res.json()
}

async function loadCases() {
  const res = await apiFetch('/api/cases/')
  cases.value = await res.json()
}

async function loadEnvs() {
  const res = await apiFetch('/api/envs/')
  envs.value = await res.json()
}

onMounted(() => {
  loadSchedules()
  loadCrontabs()
  loadSuites()
  loadCases()
  loadEnvs()
})

function openCreate() {
  isEdit.value = false
  editId.value = null
  form.name = ''
  form.crontab = crontabs.value[0]?.id || null
  form.args = '[]'
  form.kwargs = '{}'
  form.enabled = true
  form.description = ''
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  editId.value = row.id
  form.name = row.name
  form.crontab = row.crontab
  form.args = row.args
  form.kwargs = row.kwargs
  form.enabled = row.enabled
  form.description = row.description
  dialogVisible.value = true
}

function openQuickCreate() {
  quickForm.type = 'suite'
  quickForm.targetId = suites.value[0]?.id ?? null
  quickForm.envId = null
  quickForm.crontabId = crontabs.value[0]?.id ?? null
  quickForm.enabled = true
  quickForm.stop_on_failure = false
  quickForm.variablesJson = '{}'
  quickForm.name = ''
  quickDialogVisible.value = true
}

const caseOptions = computed(() => cases.value.map(c => ({ label: `${c.id} - ${c.title}`, value: c.id, project: c.project })))
const suiteOptions = computed(() => suites.value.map(s => ({ label: `${s.id} - ${s.name}`, value: s.id, project: s.project })))

const selectedProjectId = computed(() => {
  if (quickForm.type === 'case') {
    return caseOptions.value.find(i => i.value === quickForm.targetId)?.project ?? null
  }
  return suiteOptions.value.find(i => i.value === quickForm.targetId)?.project ?? null
})

const envOptions = computed(() => {
  if (!selectedProjectId.value) {
    return envs.value.map(e => ({ label: `${e.name} (P${e.project})`, value: e.id, project: e.project }))
  }
  return envs.value
    .filter(e => e.project === selectedProjectId.value)
    .map(e => ({ label: e.name, value: e.id, project: e.project }))
})

async function submitQuick() {
  if (!quickForm.targetId) return ElMessage.warning('请选择目标用例/套件')
  if (!quickForm.crontabId) return ElMessage.warning('请选择调度周期')
  let variables
  try {
    variables = JSON.parse(quickForm.variablesJson || '{}')
  } catch {
    return ElMessage.error('变量须为合法 JSON 对象')
  }

  const basePayload = {
    name: quickForm.name.trim() || undefined,
    env_id: quickForm.envId || undefined,
    crontab_id: quickForm.crontabId,
    enabled: quickForm.enabled,
    variables,
  }

  const url = quickForm.type === 'case'
    ? `/api/cases/${quickForm.targetId}/schedule/`
    : `/api/suites/${quickForm.targetId}/schedule/`
  const payload = quickForm.type === 'suite'
    ? { ...basePayload, stop_on_failure: quickForm.stop_on_failure }
    : basePayload

  const res = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    return ElMessage.error(data.detail || '创建失败')
  }
  ElMessage.success('定时任务已创建')
  quickDialogVisible.value = false
  loadSchedules()
}

async function submit() {
  if (!form.name.trim()) return ElMessage.warning('请填写任务名称')
  if (!form.crontab) return ElMessage.warning('请选择调度周期')
  
  const url = isEdit.value ? `/api/schedules/${editId.value}/` : '/api/schedules/'
  const method = isEdit.value ? 'PUT' : 'POST'

  const res = await apiFetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(form)
  })

  if (res.ok) {
    ElMessage.success(isEdit.value ? '已更新' : '已创建')
    dialogVisible.value = false
    loadSchedules()
  } else {
    ElMessage.error('保存失败')
  }
}

async function submitCrontab() {
  const res = await apiFetch('/api/crontabs/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(crontabForm)
  })
  if (res.ok) {
    const data = await res.json()
    ElMessage.success('周期已创建')
    crontabDialogVisible.value = false
    await loadCrontabs()
    form.crontab = data.id
  }
}

async function toggleStatus(row) {
  const res = await apiFetch(`/api/schedules/${row.id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: row.enabled })
  })
  if (res.ok) {
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  }
}

async function triggerSchedule(row) {
  const res = await apiFetch(`/api/schedules/${row.id}/trigger/`, {
    method: 'POST',
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    return ElMessage.error(data.detail || '触发失败')
  }
  ElMessage.success('已触发执行')
}

async function removeSchedule(row) {
  try {
    await ElMessageBox.confirm('确定删除该定时任务吗？', '警告', { type: 'warning' })
    const res = await apiFetch(`/api/schedules/${row.id}/`, {
      method: 'DELETE',
    })
    if (res.ok) {
      ElMessage.success('已删除')
      loadSchedules()
    }
  } catch {}
}

const getCrontabStr = (id) => {
  const c = crontabs.value.find(i => i.id === id)
  if (!c) return '未知'
  return `${c.minute} ${c.hour} ${c.day_of_month} ${c.month_of_year} ${c.day_of_week}`
}
</script>

<template>
  <div class="schedules-view">
    <div class="page-header">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建定时任务</el-button>
      <el-button style="margin-left: 12px" :icon="Timer" @click="openQuickCreate">快速创建(用例/套件)</el-button>
    </div>

    <el-table v-loading="loading" :data="schedules" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="任务名称" min-width="150" />
      <el-table-column label="调度周期 (Cron)" width="180">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ getCrontabStr(row.crontab) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-switch v-model="row.enabled" @change="toggleStatus(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="last_run_at" label="上次运行" width="180" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button type="success" link :icon="Timer" @click="triggerSchedule(row)">触发</el-button>
          <el-button type="primary" link :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button type="danger" link :icon="Delete" @click="removeSchedule(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 任务编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑定时任务' : '新建定时任务'" width="550px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" placeholder="如：每日凌晨回归测试" />
        </el-form-item>
        <el-form-item label="调度周期" required>
          <div style="display: flex; gap: 8px; width: 100%">
            <el-select v-model="form.crontab" placeholder="选择或创建周期" style="flex: 1">
              <el-option v-for="c in crontabs" :key="c.id" :label="getCrontabStr(c.id)" :value="c.id" />
            </el-select>
            <el-button :icon="Plus" @click="crontabDialogVisible = true" />
          </div>
        </el-form-item>
        <el-form-item label="执行参数 (JSON)">
          <el-input v-model="form.args" placeholder="如: [1] (测试套件ID)" />
          <div class="hint">通常为套件 ID 列表，例如 [1]</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- Cron 周期创建弹窗 -->
    <el-dialog v-model="crontabDialogVisible" title="创建 Cron 周期" width="400px">
      <el-form :model="crontabForm" label-width="80px">
        <el-form-item label="分 (min)">
          <el-input v-model="crontabForm.minute" placeholder="*" />
        </el-form-item>
        <el-form-item label="时 (hour)">
          <el-input v-model="crontabForm.hour" placeholder="*" />
        </el-form-item>
        <el-form-item label="日 (day)">
          <el-input v-model="crontabForm.day_of_month" placeholder="*" />
        </el-form-item>
        <el-form-item label="月 (month)">
          <el-input v-model="crontabForm.month_of_year" placeholder="*" />
        </el-form-item>
        <el-form-item label="周 (week)">
          <el-input v-model="crontabForm.day_of_week" placeholder="*" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="crontabDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCrontab">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="quickDialogVisible" title="快速创建定时任务" width="560px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="任务类型" required>
          <el-radio-group v-model="quickForm.type">
            <el-radio-button value="suite">套件</el-radio-button>
            <el-radio-button value="case">用例</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="选择目标" required>
          <el-select v-model="quickForm.targetId" filterable style="width: 100%">
            <el-option
              v-for="opt in (quickForm.type === 'case' ? caseOptions : suiteOptions)"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="执行环境">
          <el-select v-model="quickForm.envId" clearable placeholder="默认环境(留空)" style="width: 100%">
            <el-option
              v-for="opt in envOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="调度周期" required>
          <el-select v-model="quickForm.crontabId" placeholder="选择 Cron 周期" style="width: 100%">
            <el-option v-for="c in crontabs" :key="c.id" :label="getCrontabStr(c.id)" :value="c.id" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="quickForm.type === 'suite'" label="遇败即停">
          <el-switch v-model="quickForm.stop_on_failure" />
        </el-form-item>

        <el-form-item label="启用">
          <el-switch v-model="quickForm.enabled" />
        </el-form-item>

        <el-form-item label="任务名称">
          <el-input v-model="quickForm.name" placeholder="留空自动生成" />
        </el-form-item>

        <el-form-item label="变量(JSON)">
          <el-input v-model="quickForm.variablesJson" type="textarea" :rows="4" placeholder='{"token":"xxx"}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="quickDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitQuick">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
