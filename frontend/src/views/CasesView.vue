<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { ArrowDown, ArrowUp, Delete, Picture, Search } from '@element-plus/icons-vue'
import { apiFetch } from '../api'
import { useCurrentUser } from '../auth'
import PageToolbar from '../components/PageToolbar.vue'

const loading = ref(false)
const runLoading = ref(false)
const logDialogVisible = ref(false)
const logContent = ref('')
const stepResults = ref([])
const screenshotDialogVisible = ref(false)
const screenshotUrl = ref('')
const perfDialogVisible = ref(false)
const perfSubmitting = ref(false)
const perfForm = reactive({
  id: null,
  title: '',
  users: 10,
  spawn_rate: 1,
  duration: '60s'
})
const importDialogVisible = ref(false)
const importSource = ref('body')
const importProject = ref(null)
const importJsonText = ref('')
const importUrl = ref('')
const importYamlText = ref('')
const importLoading = ref(false)
const historyDialogVisible = ref(false)
const historyLoading = ref(false)
const historyTitle = ref('')
const historyRecords = ref([])
const historyCaseId = ref(null)
const versionsDialogVisible = ref(false)
const versionsLoading = ref(false)
const versionsTitle = ref('')
const versionsList = ref([])
const snapshotDialogVisible = ref(false)
const snapshotText = ref('')
const cases = ref([])
const projects = ref([])
const envs = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const searchQuery = ref('')
const filterProject = ref(null)
const selectedEnvId = ref(null)
const { isAdminUser } = useCurrentUser()

const projectEnvs = computed(() => {
  if (!filterProject.value) return envs.value
  return envs.value.filter(e => e.project === filterProject.value)
})

const filteredCases = computed(() => {
  let result = cases.value
  if (filterProject.value) {
    result = result.filter(c => c.project === filterProject.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(c => c.title.toLowerCase().includes(q))
  }
  return result
})

const form = reactive({
  project: null,
  title: '',
  steps: [],
  variablesJson: '{}',
  setup_sql: '',
  teardown_sql: '',
  status: 'draft',
})

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
const ASSERT_SOURCES = [
  { label: '状态码', value: 'status_code' },
  { label: 'JSON 响应', value: 'json' },
  { label: '响应头', value: 'header' },
  { label: '数据库', value: 'database' },
  { label: 'JSON Schema', value: 'schema' },
]
const ASSERT_OPERATORS = [
  { label: '等于', value: 'eq' },
  { label: '包含', value: 'contains' },
  { label: '大于', value: 'gt' },
  { label: '小于', value: 'lt' },
  { label: 'Schema校验', value: 'validate' },
]
const UI_ACTIONS = [
  { label: '打开网页', value: 'open' },
  { label: '点击元素', value: 'click' },
  { label: '输入内容', value: 'input' },
  { label: '等待可见', value: 'wait_visible' },
  { label: '强制等待', value: 'sleep' },
]

function addStep(type) {
  if (type === 'http') {
    form.steps.push({
      type: 'http',
      method: 'GET',
      url: '',
      headers: '{}',
      body: '',
      capture: '{}',
      assertions: [],
    })
  } else {
    form.steps.push({
      type: 'ui',
      action: 'open',
      url: '',
      selector: '',
      text: '',
      by: 'css',
      headless: true,
      seconds: 1,
      timeout: 10,
    })
  }
}

function removeStep(index) {
  form.steps.splice(index, 1)
}

function moveStep(index, direction) {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= form.steps.length) return
  const temp = form.steps[index]
  form.steps[index] = form.steps[newIndex]
  form.steps[newIndex] = temp
}

function addAssertion(step) {
  if (!step.assertions) step.assertions = []
  step.assertions.push({
    source: 'status_code',
    operator: 'eq',
    path: '',
    expected: '200'
  })
}

function removeAssertion(step, index) {
  step.assertions.splice(index, 1)
}

// ... placeholder constants ...
const STEPS_PLACEHOLDER = `混跑示例：HTTP → UI(Selenium) → 再 HTTP
[
  {"type":"http","method":"GET","url":"https://httpbin.org/uuid","capture":{"uid":{"from":"json","path":"uuid"}}},
  {"type":"ui","action":"open","url":"https://example.com","headless":true},
  {"type":"ui","action":"click","by":"css","selector":"a","timeout":10},
  {"type":"ui","action":"click","by":"xpath","selector":"//a","timeout":10},
  {"type":"http","method":"GET","url":"https://httpbin.org/get?tag={{uid}}"}
]
UI 支持: open, click, input, wait_visible, sleep；本地调试可把 headless 改为 false。`

const VARIABLES_PLACEHOLDER = `{
  "base_url": "https://httpbin.org",
  "tenant": "demo"
}`

const statusLabel = {
  draft: '草稿',
  active: '启用',
  archived: '归档',
}

const statusTag = (s) => ({ draft: 'info', active: 'success', archived: 'warning' }[s] || 'info')

const projectOptions = computed(() =>
  projects.value.map((p) => ({ label: p.name, value: p.id })),
)

function stepCount(row) {
  const s = row.steps
  return Array.isArray(s) ? s.length : 0
}

async function loadProjects() {
  const res = await apiFetch('/api/projects/')
  projects.value = await res.json()
}

async function loadEnvs() {
  const res = await apiFetch('/api/envs/')
  envs.value = await res.json()
}

async function loadCases() {
  if (runLoading.value) return
  loading.value = true
  try {
    const res = await apiFetch('/api/cases/')
    cases.value = await res.json()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  await loadEnvs()
  loadCases()
})

function openCreate() {
  if (!isAdminUser.value) return
  isEdit.value = false
  editId.value = null
  form.project = projectOptions.value[0]?.value ?? null
  form.title = ''
  form.steps = []
  form.variablesJson = '{}'
  form.setup_sql = ''
  form.teardown_sql = ''
  form.status = 'draft'
  dialogVisible.value = true
}

function openEdit(row) {
  if (!isAdminUser.value) return
  isEdit.value = true
  editId.value = row.id
  form.project = row.project
  form.title = row.title
  form.steps = JSON.parse(JSON.stringify(row.steps || [])).map((s) => {
    if (s && s.type === 'ui') {
      if (s.headless === undefined && s.browser && s.browser.headless !== undefined) {
        s.headless = s.browser.headless
      }
      if (!s.by) s.by = 'css'
      if (s.seconds === undefined) s.seconds = 1
    }
    return s
  })
  form.variablesJson = JSON.stringify(row.variables || {}, null, 2)
  form.setup_sql = row.setup_sql || ''
  form.teardown_sql = row.teardown_sql || ''
  form.status = row.status
  dialogVisible.value = true
}

async function submit() {
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可管理用例')
    return
  }
  if (!form.project) {
    ElMessage.warning('请先创建至少一个测试项目')
    return
  }
  if (!form.title.trim()) {
    ElMessage.warning('请填写用例标题')
    return
  }
  
  // Validate variables
  let variables
  try {
    variables = JSON.parse(form.variablesJson || '{}')
  } catch {
    ElMessage.error('变量池须为合法 JSON 对象')
    return
  }
  
  const payload = {
    project: form.project,
    title: form.title.trim(),
    steps: form.steps,
    variables,
    setup_sql: form.setup_sql,
    teardown_sql: form.teardown_sql,
    status: form.status,
  }

  const url = isEdit.value ? `/api/cases/${editId.value}/` : '/api/cases/'
  const method = isEdit.value ? 'PUT' : 'POST'

  const res = await apiFetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    ElMessage.error(err.detail || (isEdit.value ? '修改失败' : '创建失败'))
    return
  }
  ElMessage.success(isEdit.value ? '已更新' : '已创建')
  dialogVisible.value = false
  loadCases()
}

async function removeRow(row) {
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可管理用例')
    return
  }
  await ElMessageBox.confirm(`确定删除用例「${row.title}」？`, '确认', { type: 'warning' })
  const res = await apiFetch(`/api/cases/${row.id}/`, {
    method: 'DELETE',
  })
  if (res.status === 204 || res.ok) {
    ElMessage.success('已删除')
    loadCases()
  } else {
    ElMessage.error('删除失败')
  }
}

function openImportDialog() {
  if (!isAdminUser.value) return
  importSource.value = 'body'
  importProject.value = projectOptions.value[0]?.value ?? null
  importJsonText.value = ''
  importUrl.value = ''
  importYamlText.value = ''
  importDialogVisible.value = true
}

async function submitImport() {
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可导入 OpenAPI')
    return
  }
  if (!importProject.value) {
    ElMessage.warning('请选择目标项目')
    return
  }
  let payload = { project: importProject.value }
  if (importSource.value === 'body') {
    try {
      payload.spec = JSON.parse(importJsonText.value || '{}')
    } catch {
      ElMessage.error('OpenAPI JSON 格式不正确')
      return
    }
  } else if (importSource.value === 'url') {
    const u = importUrl.value.trim()
    if (!u) {
      ElMessage.warning('请填写文档 URL')
      return
    }
    payload.spec_url = u
  } else {
    const y = importYamlText.value.trim()
    if (!y) {
      ElMessage.warning('请粘贴 YAML 内容')
      return
    }
    payload.spec_yaml = importYamlText.value
  }
  importLoading.value = true
  try {
    const res = await apiFetch('/api/cases/import-openapi/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      ElMessage.error(
        typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data) || '导入失败',
      )
      return
    }
    ElMessage.success(`已生成 ${data.count} 条用例骨架`)
    importDialogVisible.value = false
    loadCases()
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    importLoading.value = false
  }
}

async function openCaseHistory(row) {
  historyCaseId.value = row.id
  historyTitle.value = row.title
  historyDialogVisible.value = true
  historyLoading.value = true
  historyRecords.value = []
  try {
    const res = await apiFetch(`/api/cases/${row.id}/records/?limit=50`)
    if (res.ok) {
      historyRecords.value = await res.json()
    } else {
      ElMessage.error('加载执行历史失败')
    }
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    historyLoading.value = false
  }
}

async function openCaseVersions(row) {
  versionsTitle.value = row.title
  versionsDialogVisible.value = true
  versionsLoading.value = true
  versionsList.value = []
  try {
    const res = await apiFetch(`/api/cases/${row.id}/versions/`)
    if (res.ok) {
      versionsList.value = await res.json()
    } else {
      ElMessage.error('加载版本历史失败')
    }
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    versionsLoading.value = false
  }
}

function showSnapshot(row) {
  snapshotText.value = JSON.stringify(row.snapshot || {}, null, 2)
  snapshotDialogVisible.value = true
}

async function restoreVersion(caseId, v) {
  if (!isAdminUser.value) {
    ElMessage.warning('仅管理员可回滚版本')
    return
  }
  await ElMessageBox.confirm(`回滚到版本 v${v.version}？将生成一个新版本保存当前状态。`, '确认', { type: 'warning' })
  const res = await apiFetch(`/api/cases/${caseId}/restore_version/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version_id: v.id }),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    ElMessage.error(data.detail || '回滚失败')
    return
  }
  ElMessage.success('已回滚')
  versionsDialogVisible.value = false
  await loadCases()
}

function showRecordLog(row) {
  logContent.value = row.result_log || '(无日志)'
  stepResults.value = row.step_results || []
  logDialogVisible.value = true
}

async function openRecordReport(row) {
  try {
    const res = await apiFetch(`/api/records/${row.id}/report/`)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      ElMessage.error(err.detail || '无法加载报告')
      return
    }
    const html = await res.text()
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const w = window.open(url, '_blank')
    if (!w) {
      URL.revokeObjectURL(url)
      ElMessage.warning('浏览器拦截了弹出窗口，请使用「下载 HTML」')
      return
    }
    setTimeout(() => URL.revokeObjectURL(url), 120000)
  } catch (e) {
    ElMessage.error(String(e))
  }
}

async function downloadRecordReportHtml(row) {
  try {
    const res = await apiFetch(`/api/records/${row.id}/report/?download=1`)
    if (!res.ok) {
      ElMessage.error('下载失败')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `record_${row.id}.html`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已下载 HTML 报告')
  } catch (e) {
    ElMessage.error(String(e))
  }
}

async function downloadRecordReportJson(row) {
  try {
    const res = await apiFetch(`/api/records/${row.id}/report/?format=json&download=1`)
    if (!res.ok) {
      ElMessage.error('导出失败')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `record_${row.id}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出 JSON')
  } catch (e) {
    ElMessage.error(String(e))
  }
}

function showScreenshot(url) {
  screenshotUrl.value = url
  screenshotDialogVisible.value = true
}

function openPerfDialog(row) {
  perfForm.id = row.id
  perfForm.title = row.title
  perfSubmitting.value = false
  perfDialogVisible.value = true
}

async function submitPerf() {
  if (perfSubmitting.value) return
  perfSubmitting.value = true
  try {
    const res = await apiFetch(`/api/cases/${perfForm.id}/run_perf/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        users: perfForm.users,
        spawn_rate: perfForm.spawn_rate,
        duration: perfForm.duration,
        env_id: selectedEnvId.value
      })
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      if (data && data.deduplicated) {
        ElMessage.warning('检测到重复提交，已复用最近一次压测任务')
      } else {
        ElMessage.success('性能测试已在后台启动，请稍后查看生成的 CSV 结果')
      }
      perfDialogVisible.value = false
    } else {
      ElMessage.error(data.detail || '启动压测失败')
    }
  } finally {
    perfSubmitting.value = false
  }
}

async function runCase(row) {
  runLoading.value = true
  try {
    const res = await apiFetch(`/api/cases/${row.id}/run/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        env_id: selectedEnvId.value
      })
    })
    const taskData = await res.json()
    if (taskData.status === 'pending') {
      ElMessage.info('任务已提交，后台执行中...')
      pollTaskStatus(taskData.task_id, row.title)
    }
  } catch (e) {
    ElMessage.error(`任务提交异常: ${e.message}`)
    runLoading.value = false
  }
}

async function pollTaskStatus(taskId, title) {
  const timer = setInterval(async () => {
    try {
      const res = await apiFetch(`/api/task-status/${taskId}/`)
      const data = await res.json()
      if (data.ready) {
        clearInterval(timer)
        runLoading.value = false
        const result = data.result
        if (result.status === 'success') {
          ElMessage.success(`执行成功: ${title}`)
        } else {
          ElMessage.error(`执行失败: ${title}`)
        }
        await loadCases()
      }
    } catch (e) {
      clearInterval(timer)
      runLoading.value = false
    }
  }, 2000)
}
</script>

<template>
  <div>
    <PageToolbar>
      <template #left>
        <el-button v-if="isAdminUser" type="primary" @click="openCreate">新建用例</el-button>
        <el-button v-if="isAdminUser" type="success" plain :disabled="!projectOptions.length" @click="openImportDialog">
          从 OpenAPI 导入
        </el-button>
        <span v-if="!projectOptions.length" style="margin-left: 12px; color: var(--el-color-warning)">
          请先在「测试项目」中创建项目
        </span>
      </template>
      <template #right>
        <el-select v-model="selectedEnvId" placeholder="执行环境" clearable style="width: 150px">
          <el-option v-for="e in projectEnvs" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
        <el-select v-model="filterProject" placeholder="按项目筛选" clearable style="width: 180px">
          <el-option
            v-for="opt in projectOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-input
          v-model="searchQuery"
          placeholder="搜索用例标题..."
          clearable
          style="width: 240px"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </template>
    </PageToolbar>
    
    <el-table v-loading="loading || runLoading" :data="filteredCases" stripe class="page-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span style="font-weight: 500">{{ row.title }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="project_name" label="项目" width="140" />
      <el-table-column label="步骤数" width="80">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ stepCount(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">
            {{ statusLabel[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="180" />
          <el-table-column :width="isAdminUser ? 350 : 220" label="操作" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link :disabled="runLoading" @click="runCase(row)">立即执行</el-button>
              <el-button type="success" link :disabled="runLoading" @click="openPerfDialog(row)">压测</el-button>
              <el-button v-if="isAdminUser" type="primary" link :disabled="runLoading" @click="openEdit(row)">编辑</el-button>
              <el-button type="info" link :disabled="runLoading" @click="openCaseHistory(row)">执行历史</el-button>
              <el-button type="warning" link :disabled="runLoading" @click="openCaseVersions(row)">版本</el-button>
              <el-button v-if="isAdminUser" type="danger" link :disabled="runLoading" @click="removeRow(row)">删除</el-button>
            </template>
          </el-table-column>
    </el-table>

    <el-dialog
      v-model="historyDialogVisible"
      :title="`执行历史 — ${historyTitle}`"
      width="720px"
      destroy-on-close
    >
      <div v-loading="historyLoading">
        <el-table v-if="historyRecords.length" :data="historyRecords" size="small" max-height="400" stripe>
          <el-table-column prop="id" label="记录#" width="80" />
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column label="结果" width="100">
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'success' ? 'success' : row.status === 'running' ? 'info' : 'danger'"
                size="small"
              >
                {{
                  row.status === 'success' ? '成功' : row.status === 'running' ? '执行中' : '失败'
                }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="elapsed_time" label="耗时(s)" width="90" />
          <el-table-column label="详情" min-width="260">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showRecordLog(row)">日志</el-button>
              <el-button type="success" link size="small" @click="openRecordReport(row)">报告</el-button>
              <el-button type="info" link size="small" @click="downloadRecordReportHtml(row)">HTML</el-button>
              <el-button type="warning" link size="small" @click="downloadRecordReportJson(row)">JSON</el-button>
              <el-button v-if="row.screenshot" type="success" link size="small" @click="showScreenshot(row.screenshot)">截图</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!historyLoading" description="暂无执行记录" />
      </div>
      <template #footer>
        <el-button type="primary" @click="historyDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="versionsDialogVisible"
      :title="`版本历史 — ${versionsTitle}`"
      width="780px"
      destroy-on-close
    >
      <div v-loading="versionsLoading">
        <el-table v-if="versionsList.length" :data="versionsList" size="small" max-height="420" stripe>
          <el-table-column prop="version" label="版本" width="90">
            <template #default="{ row }">v{{ row.version }}</template>
          </el-table-column>
          <el-table-column prop="created_by_username" label="创建人" width="120" />
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showSnapshot(row)">快照</el-button>
              <el-button v-if="isAdminUser" type="warning" link size="small" @click="restoreVersion(row.case, row)">回滚</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!versionsLoading" description="暂无版本记录" />
      </div>
      <template #footer>
        <el-button type="primary" @click="versionsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="snapshotDialogVisible" title="版本快照" width="760px" destroy-on-close>
      <el-input v-model="snapshotText" type="textarea" :rows="18" readonly />
      <template #footer>
        <el-button type="primary" @click="snapshotDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="logDialogVisible" title="执行详情与日志" width="800px" destroy-on-close>
      <el-tabs type="border-card">
        <el-tab-pane label="步骤明细">
          <el-table :data="stepResults" stripe size="small">
            <el-table-column prop="name" label="步骤" width="120" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.status === 'success' ? '通过' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="elapsed" label="耗时(s)" width="80" />
            <el-table-column label="简要日志">
              <template #default="{ row }">
                <div v-for="(l, i) in row.log" :key="i" style="font-size: 11px; color: #666">{{ l }}</div>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!stepResults.length" description="暂无结构化步骤数据" />
        </el-tab-pane>
        <el-tab-pane label="原始日志">
          <el-input v-model="logContent" type="textarea" :rows="16" readonly class="log-textarea" />
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button type="primary" @click="logDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="screenshotDialogVisible" title="失败截图" width="800px" destroy-on-close>
      <div style="text-align: center">
        <el-image :src="screenshotUrl" fit="contain" style="max-width: 100%; border: 1px solid var(--el-border-color)">
          <template #error>
            <div class="image-slot">
              <el-icon><Picture /></el-icon> 无法加载图片 ({{ screenshotUrl }})
            </div>
          </template>
        </el-image>
      </div>
    </el-dialog>

    <!-- 性能测试配置弹窗 -->
    <el-dialog v-model="perfDialogVisible" :title="'性能压测: ' + perfForm.title" width="450px">
      <el-form :model="perfForm" label-width="100px" :disabled="perfSubmitting">
        <el-form-item label="并发用户数">
          <el-input-number v-model="perfForm.users" :min="1" :max="5000" />
        </el-form-item>
        <el-form-item label="每秒启动数">
          <el-input-number v-model="perfForm.spawn_rate" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="压测持续时长">
          <el-select v-model="perfForm.duration" style="width: 100%">
            <el-option label="30秒" value="30s" />
            <el-option label="1分钟" value="60s" />
            <el-option label="5分钟" value="300s" />
            <el-option label="10分钟" value="600s" />
          </el-select>
        </el-form-item>
        <el-alert title="性能测试将基于接口功能用例自动转换为 Locust 场景并在后台 Headless 模式运行。" type="info" :closable="false" />
      </el-form>
      <template #footer>
        <el-button :disabled="perfSubmitting" @click="perfDialogVisible = false">取消</el-button>
        <el-button type="success" :loading="perfSubmitting" :disabled="perfSubmitting" @click="submitPerf">启动压测</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-if="isAdminUser"
      v-model="importDialogVisible"
      title="从 OpenAPI / Swagger 导入"
      width="620px"
      destroy-on-close
    >
      <el-form label-width="100px" v-loading="importLoading">
        <el-form-item label="目标项目" required>
          <el-select v-model="importProject" placeholder="选择项目" style="width: 100%">
            <el-option
              v-for="opt in projectOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="文档来源">
          <el-radio-group v-model="importSource">
            <el-radio-button value="body">粘贴 JSON</el-radio-button>
            <el-radio-button value="url">文档 URL</el-radio-button>
            <el-radio-button value="yaml">粘贴 YAML</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="importSource === 'body'" label="OpenAPI JSON">
          <el-input v-model="importJsonText" type="textarea" :rows="12" placeholder="{ &quot;openapi&quot;: &quot;3.0.0&quot;, ... }" />
        </el-form-item>
        <el-form-item v-else-if="importSource === 'url'" label="URL">
          <el-input v-model="importUrl" placeholder="https://example.com/openapi.json" />
        </el-form-item>
        <el-form-item v-else label="YAML">
          <el-input v-model="importYamlText" type="textarea" :rows="12" placeholder="swagger: &quot;2.0&quot; ..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importLoading" @click="submitImport">导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-if="isAdminUser" v-model="dialogVisible" :title="isEdit ? '编辑用例' : '新建用例'" width="560px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="所属项目" required>
          <el-select v-model="form.project" placeholder="选择项目" style="width: 100%">
            <el-option
              v-for="opt in projectOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="用例名称" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio-button value="draft">草稿</el-radio-button>
            <el-radio-button value="active">启用</el-radio-button>
            <el-radio-button value="archived">归档</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="变量池 JSON">
          <el-input
            v-model="form.variablesJson"
            type="textarea"
            :rows="3"
            :placeholder="VARIABLES_PLACEHOLDER"
          />
        </el-form-item>

        <el-collapse style="margin-bottom: 20px">
          <el-collapse-item title="测试数据管理 (Setup/Teardown SQL)" name="data-hooks">
            <el-form-item label="前置 SQL">
              <el-input v-model="form.setup_sql" type="textarea" :rows="3" placeholder="例如: INSERT INTO users (name) VALUES ('test');" />
            </el-form-item>
            <el-form-item label="后置 SQL">
              <el-input v-model="form.teardown_sql" type="textarea" :rows="3" placeholder="例如: DELETE FROM users WHERE name='test';" />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
        
        <el-divider content-position="left">测试步骤 ({{ form.steps.length }})</el-divider>
        
        <div class="steps-container">
          <div v-for="(step, index) in form.steps" :key="index" class="step-card">
            <div class="step-header">
              <div style="display: flex; align-items: center; gap: 8px">
                <el-tag :type="step.type === 'http' ? '' : 'success'" size="small">
                  {{ step.type === 'http' ? 'HTTP' : 'UI' }}
                </el-tag>
                <span style="font-size: 13px; color: var(--el-text-color-secondary)">步骤 {{ index + 1 }}</span>
              </div>
              <div class="step-actions">
                <el-button link :disabled="index === 0" @click="moveStep(index, -1)">
                  <el-icon><ArrowUp /></el-icon>
                </el-button>
                <el-button link :disabled="index === form.steps.length - 1" @click="moveStep(index, 1)">
                  <el-icon><ArrowDown /></el-icon>
                </el-button>
                <el-button link type="danger" @click="removeStep(index)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>
            
            <div class="step-body">
              <template v-if="step.type === 'http'">
                <div style="display: flex; gap: 8px; margin-bottom: 8px">
                  <el-select v-model="step.method" style="width: 100px">
                    <el-option v-for="m in HTTP_METHODS" :key="m" :label="m" :value="m" />
                  </el-select>
                  <el-input v-model="step.url" placeholder="请求地址 (支持 {{变量}})" style="flex: 1" />
                </div>
                <el-collapse>
                  <el-collapse-item title="高级参数 (Headers/Body/Capture)" name="1">
                    <el-form-item label="Headers" label-width="70px">
                      <el-input v-model="step.headers" type="textarea" :rows="2" placeholder="{}" />
                    </el-form-item>
                    <el-form-item label="Body" label-width="70px">
                      <el-input v-model="step.body" type="textarea" :rows="2" placeholder="{}" />
                    </el-form-item>
                    <el-form-item label="提取变量" label-width="70px">
                      <el-input v-model="step.capture" type="textarea" :rows="2" placeholder="{}" />
                    </el-form-item>
                    <el-divider content-position="left"><span style="font-size: 12px">断言规则</span></el-divider>
                    <div v-for="(ass, aIdx) in step.assertions" :key="aIdx" style="display: flex; gap: 4px; margin-bottom: 8px; align-items: center">
                      <el-select v-model="ass.source" style="width: 100px" size="small">
                        <el-option v-for="s in ASSERT_SOURCES" :key="s.value" :label="s.label" :value="s.value" />
                      </el-select>
                      <el-input v-if="ass.source !== 'status_code'" 
                                v-model="ass.path" 
                                :placeholder="ass.source === 'database' ? 'SQL语句' : 'JSONPath/Header'" 
                                style="width: 120px" 
                                size="small" />
                      <el-select v-model="ass.operator" style="width: 80px" size="small">
                        <el-option v-for="o in ASSERT_OPERATORS" :key="o.value" :label="o.label" :value="o.value" />
                      </el-select>
                      <el-input v-model="ass.expected" 
                                :placeholder="ass.source === 'schema' ? 'JSON Schema' : '预期值'" 
                                style="flex: 1" 
                                size="small" />
                      <el-button link type="danger" @click="removeAssertion(step, aIdx)"><el-icon><Delete /></el-icon></el-button>
                    </div>
                    <el-button link type="primary" size="small" @click="addAssertion(step)">+ 添加断言</el-button>
                  </el-collapse-item>
                </el-collapse>
              </template>
              
              <template v-else>
                <div style="display: flex; gap: 8px; margin-bottom: 8px">
                  <el-select v-model="step.action" style="width: 130px">
                    <el-option v-for="a in UI_ACTIONS" :key="a.value" :label="a.label" :value="a.value" />
                  </el-select>
                  <el-input
                    v-if="step.action === 'open'"
                    v-model="step.url"
                    placeholder="地址"
                    style="flex: 1"
                  />
                  <el-input-number
                    v-else-if="step.action === 'sleep'"
                    v-model="step.seconds"
                    :min="0"
                    :max="3600"
                    controls-position="right"
                    style="flex: 1"
                  />
                  <template v-else>
                    <el-select v-model="step.by" style="width: 110px">
                      <el-option label="CSS" value="css" />
                      <el-option label="XPath" value="xpath" />
                      <el-option label="ID" value="id" />
                      <el-option label="Name" value="name" />
                    </el-select>
                    <el-input v-model="step.selector" placeholder="选择器" style="flex: 1" />
                  </template>
                </div>
                <div v-if="step.action === 'input'" style="margin-top: 8px">
                  <el-input v-model="step.text" placeholder="输入内容" />
                </div>
                <div style="display: flex; gap: 12px; align-items: center; margin-top: 10px">
                  <el-switch v-model="step.headless" />
                  <span style="font-size: 12px; color: var(--el-text-color-secondary)">Headless</span>
                  <el-input-number v-model="step.timeout" :min="1" :max="120" controls-position="right" />
                  <span style="font-size: 12px; color: var(--el-text-color-secondary)">超时(s)</span>
                </div>
              </template>
            </div>
          </div>
          
          <div style="margin-top: 16px; text-align: center">
            <el-button-group>
              <el-button type="primary" plain @click="addStep('http')">+ 添加 HTTP 步骤</el-button>
              <el-button type="success" plain @click="addStep('ui')">+ 添加 UI 步骤</el-button>
            </el-button-group>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.log-textarea :deep(.el-textarea__inner) {
  font-family: 'Courier New', Courier, monospace;
  background: #1e1e1e;
  color: #d4d4d4;
  line-height: 1.4;
}

.steps-container {
  max-height: 500px;
  overflow-y: auto;
  padding: 4px;
}

.step-card {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  margin-bottom: 12px;
  background: var(--el-bg-color);
  transition: all 0.3s;
}

.step-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.step-header {
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--el-border-color);
}

.step-body {
  padding: 12px;
}

.step-actions .el-icon {
  font-size: 16px;
}
</style>
