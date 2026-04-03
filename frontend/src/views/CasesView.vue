<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'

const loading = ref(false)
const runLoading = ref(false)
const logDialogVisible = ref(false)
const logContent = ref('')
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
const cases = ref([])
const projects = ref([])
const dialogVisible = ref(false)
const form = reactive({
  project: null,
  title: '',
  stepsJson: '[]',
  variablesJson: '{}',
  status: 'draft',
})

const STEPS_PLACEHOLDER = `混跑示例：HTTP → UI(Selenium) → 再 HTTP
[
  {"type":"http","method":"GET","url":"https://httpbin.org/uuid","capture":{"uid":{"from":"json","path":"uuid"}}},
  {"type":"ui","action":"open","url":"https://example.com","browser":{"headless":true}},
  {"type":"ui","action":"click","selector":"a","timeout":10,"by":"css"},
  {"type":"http","method":"GET","url":"https://httpbin.org/get?tag={{uid}}"}
]
UI 支持: open, click, input, wait_visible, sleep；本地调试可把 headless 改为 false。`

const VARIABLES_PLACEHOLDER = `{
  "base": "https://httpbin.org",
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
  const res = await fetch('/api/projects/')
  projects.value = await res.json()
}

async function loadCases() {
  if (runLoading.value) return
  loading.value = true
  try {
    const res = await fetch('/api/cases/')
    cases.value = await res.json()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  loadCases()
})

function openCreate() {
  form.project = projectOptions.value[0]?.value ?? null
  form.title = ''
  form.stepsJson = '[]'
  form.variablesJson = '{}'
  form.status = 'draft'
  dialogVisible.value = true
}

async function submit() {
  if (!form.project) {
    ElMessage.warning('请先创建至少一个测试项目')
    return
  }
  if (!form.title.trim()) {
    ElMessage.warning('请填写用例标题')
    return
  }
  let steps
  try {
    steps = JSON.parse(form.stepsJson || '[]')
  } catch {
    ElMessage.error('步骤须为合法 JSON 数组')
    return
  }
  if (!Array.isArray(steps)) {
    ElMessage.error('步骤须为 JSON 数组')
    return
  }
  let variables
  try {
    variables = JSON.parse(form.variablesJson || '{}')
  } catch {
    ElMessage.error('变量池须为合法 JSON 对象')
    return
  }
  if (typeof variables !== 'object' || variables === null || Array.isArray(variables)) {
    ElMessage.error('变量池须为 JSON 对象')
    return
  }
  const res = await fetch('/api/cases/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project: form.project,
      title: form.title.trim(),
      steps,
      variables,
      status: form.status,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    ElMessage.error(err.detail || '创建失败')
    return
  }
  ElMessage.success('已创建')
  dialogVisible.value = false
  loadCases()
}

async function removeRow(row) {
  await ElMessageBox.confirm(`确定删除用例「${row.title}」？`, '确认', { type: 'warning' })
  const res = await fetch(`/api/cases/${row.id}/`, { method: 'DELETE' })
  if (res.status === 204 || res.ok) {
    ElMessage.success('已删除')
    loadCases()
  } else {
    ElMessage.error('删除失败')
  }
}

function openImportDialog() {
  importSource.value = 'body'
  importProject.value = projectOptions.value[0]?.value ?? null
  importJsonText.value = ''
  importUrl.value = ''
  importYamlText.value = ''
  importDialogVisible.value = true
}

async function submitImport() {
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
    const res = await fetch('/api/cases/import-openapi/', {
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
    const res = await fetch(`/api/cases/${row.id}/records/?limit=50`)
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

function showRecordLog(log) {
  logContent.value = log || '(无日志)'
  logDialogVisible.value = true
}

async function runCase(row) {
  runLoading.value = true
  try {
    const res = await fetch(`/api/cases/${row.id}/run/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variables: {} }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      ElNotification({
        title: '执行请求失败',
        message: data.detail || res.statusText || String(res.status),
        type: 'error',
        duration: 8000,
      })
      return
    }
    const ok = data.status === 'success'
    ElNotification({
      title: ok ? '接口执行成功' : '接口执行失败',
      message: `记录 #${data.record_id} · 耗时 ${data.elapsed_time}s`,
      type: ok ? 'success' : 'error',
      duration: 6000,
    })
    logContent.value = data.result_log || '(无日志)'
    logDialogVisible.value = true
    await loadCases()
    if (historyDialogVisible.value && historyCaseId.value === row.id) {
      openCaseHistory(row)
    }
  } catch (e) {
    ElNotification({
      title: '网络错误',
      message: String(e),
      type: 'error',
      duration: 8000,
    })
  } finally {
    runLoading.value = false
  }
}
</script>

<template>
  <div>
    <div style="margin-bottom: 16px">
      <el-button type="primary" @click="openCreate">新建用例</el-button>
      <el-button type="success" plain :disabled="!projectOptions.length" @click="openImportDialog">
        从 OpenAPI 导入
      </el-button>
      <span v-if="!projectOptions.length" style="margin-left: 12px; color: var(--el-color-warning)">
        请先在「测试项目」中创建项目
      </span>
    </div>
    <el-table v-loading="loading || runLoading" :data="cases" stripe style="width: 100%; max-width: 1100px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
      <el-table-column prop="project_name" label="项目" width="140" />
      <el-table-column label="步骤数" width="80">
        <template #default="{ row }">
          {{ stepCount(row) }}
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
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link :disabled="runLoading" @click="runCase(row)">立即执行</el-button>
          <el-button type="info" link :disabled="runLoading" @click="openCaseHistory(row)">执行历史</el-button>
          <el-button type="danger" link :disabled="runLoading" @click="removeRow(row)">删除</el-button>
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
          <el-table-column label="日志" min-width="100">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showRecordLog(row.result_log)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!historyLoading" description="暂无执行记录" />
      </div>
      <template #footer>
        <el-button type="primary" @click="historyDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="logDialogVisible" title="执行日志" width="640px" destroy-on-close>
      <el-input v-model="logContent" type="textarea" :rows="16" readonly class="log-textarea" />
      <template #footer>
        <el-button type="primary" @click="logDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
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

    <el-dialog v-model="dialogVisible" title="新建用例" width="560px" destroy-on-close>
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
        <el-form-item label="步骤 JSON">
          <el-input v-model="form.stepsJson" type="textarea" :rows="10" :placeholder="STEPS_PLACEHOLDER" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
