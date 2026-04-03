<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'

const loading = ref(false)
const runLoading = ref(false)
const suites = ref([])
const projects = ref([])
const cases = ref([])
const dialogVisible = ref(false)
const runDialogVisible = ref(false)
const runTargetId = ref(null)
const historyDialogVisible = ref(false)
const historySuiteName = ref('')
const historyRuns = ref([])
const historyLoading = ref(false)
const form = reactive({
  project: null,
  name: '',
  description: '',
  variablesJson: '{}',
  caseIdsText: '',
})
const runForm = reactive({
  variablesJson: '{}',
  stop_on_failure: false,
})

const projectOptions = computed(() =>
  projects.value.map((p) => ({ label: p.name, value: p.id })),
)

const caseIdHint = computed(() => {
  if (!form.project) return '请先选择项目'
  const ids = cases.value.filter((c) => c.project === form.project).map((c) => `${c.id}: ${c.title}`)
  return ids.length ? ids.join('\n') : '该项目下暂无用例'
})

async function loadProjects() {
  const res = await fetch('/api/projects/')
  projects.value = await res.json()
}

async function loadCases() {
  const res = await fetch('/api/cases/')
  cases.value = await res.json()
}

async function loadSuites() {
  loading.value = true
  try {
    const res = await fetch('/api/suites/')
    suites.value = await res.json()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  await loadCases()
  loadSuites()
})

function openCreate() {
  form.project = projectOptions.value[0]?.value ?? null
  form.name = ''
  form.description = ''
  form.variablesJson = '{}'
  form.caseIdsText = ''
  dialogVisible.value = true
}

function parseOrderedIds(text) {
  return text
    .split(/\r?\n|,|;/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => parseInt(s, 10))
    .filter((n) => !Number.isNaN(n))
}

async function submitSuite() {
  if (!form.project) {
    ElMessage.warning('请选择项目')
    return
  }
  if (!form.name.trim()) {
    ElMessage.warning('请填写套件名称')
    return
  }
  let variables
  try {
    variables = JSON.parse(form.variablesJson || '{}')
  } catch {
    ElMessage.error('套件变量须为合法 JSON 对象')
    return
  }
  const ordered_case_ids = parseOrderedIds(form.caseIdsText)
  if (!ordered_case_ids.length) {
    ElMessage.warning('请至少填写一个用例 ID（每行一个）')
    return
  }
  const res = await fetch('/api/suites/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project: form.project,
      name: form.name.trim(),
      description: form.description.trim(),
      variables,
      ordered_case_ids,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    ElMessage.error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err) || '创建失败')
    return
  }
  ElMessage.success('套件已创建')
  dialogVisible.value = false
  loadSuites()
}

async function removeSuite(row) {
  await ElMessageBox.confirm(`删除套件「${row.name}」？`, '确认', { type: 'warning' })
  const res = await fetch(`/api/suites/${row.id}/`, { method: 'DELETE' })
  if (res.status === 204 || res.ok) {
    ElMessage.success('已删除')
    loadSuites()
  } else {
    ElMessage.error('删除失败')
  }
}

function openRunDialog(id) {
  runTargetId.value = id
  runForm.variablesJson = '{}'
  runForm.stop_on_failure = false
  runDialogVisible.value = true
}

async function submitRun() {
  let variables
  try {
    variables = JSON.parse(runForm.variablesJson || '{}')
  } catch {
    ElMessage.error('变量须为合法 JSON 对象')
    return
  }
  runLoading.value = true
  try {
    const res = await fetch(`/api/suites/${runTargetId.value}/run/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        variables,
        stop_on_failure: runForm.stop_on_failure,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      ElMessage.error(data.detail || '执行失败')
      return
    }
    const { summary, suite_run_id: srid } = data
    ElNotification({
      title: '套件执行完成',
      message: `记录 #${srid} · 共 ${summary.total} 条 · 通过 ${summary.passed} · 失败 ${summary.failed}`,
      type: summary.failed ? 'warning' : 'success',
      duration: 8000,
    })
    runDialogVisible.value = false
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    runLoading.value = false
  }
}

function suiteCaseCount(row) {
  return row.cases_summary?.length ?? 0
}

function locustDownloadFilename(row) {
  const raw = String(row.name || 'suite').replace(/[/\\:*?"<>|\r\n]+/g, '_').trim() || 'suite'
  const short = raw.length > 120 ? raw.slice(0, 120) : raw
  return `locust_${row.id}_${short}.py`
}

async function downloadLocust(row) {
  try {
    const res = await fetch(`/api/suites/${row.id}/export_locust/`)
    if (!res.ok) {
      ElMessage.error('导出失败')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = locustDownloadFilename(row)
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已下载 Locust 脚本')
  } catch (e) {
    ElMessage.error(String(e))
  }
}

async function openHistory(row) {
  historySuiteName.value = row.name
  historyDialogVisible.value = true
  historyLoading.value = true
  historyRuns.value = []
  try {
    const res = await fetch(`/api/suites/${row.id}/runs/?limit=50`)
    if (res.ok) {
      historyRuns.value = await res.json()
    } else {
      ElMessage.error('加载历史失败')
    }
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    historyLoading.value = false
  }
}

function exportHistoryJson() {
  const text = JSON.stringify(historyRuns.value, null, 2)
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `suite-runs-${historySuiteName.value || 'export'}.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div>
    <div style="margin-bottom: 16px">
      <el-button type="primary" @click="openCreate">新建套件</el-button>
      <span v-if="!projectOptions.length" style="margin-left: 12px; color: var(--el-color-warning)">
        请先在「测试项目」中创建项目
      </span>
    </div>
    <el-table v-loading="loading" :data="suites" stripe style="width: 100%; max-width: 960px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="套件名称" min-width="140" />
      <el-table-column prop="project_name" label="项目" width="120" />
      <el-table-column label="用例数" width="90">
        <template #default="{ row }">
          {{ suiteCaseCount(row) }}
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="360" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link :disabled="!suiteCaseCount(row)" @click="openRunDialog(row.id)">
            运行套件
          </el-button>
          <el-button type="success" link @click="downloadLocust(row)">
            导出 Locust
          </el-button>
          <el-button type="info" link @click="openHistory(row)">执行历史</el-button>
          <el-button type="danger" link @click="removeSuite(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建测试套件" width="560px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="项目" required>
          <el-select v-model="form.project" placeholder="选择项目" style="width: 100%">
            <el-option
              v-for="opt in projectOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如：登录回归" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" rows="2" />
        </el-form-item>
        <el-form-item label="套件变量">
          <el-input v-model="form.variablesJson" type="textarea" rows="2" placeholder="{}" />
        </el-form-item>
        <el-form-item label="用例顺序" required>
          <el-input
            v-model="form.caseIdsText"
            type="textarea"
            rows="6"
            placeholder="每行一个用例 ID，自上而下为执行顺序"
          />
          <div class="hint">当前项目用例参考：<pre>{{ caseIdHint }}</pre></div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitSuite">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="historyDialogVisible"
      :title="`执行历史 — ${historySuiteName}`"
      width="720px"
      destroy-on-close
    >
      <div v-loading="historyLoading">
        <div v-if="historyRuns.length" style="margin-bottom: 10px">
          <el-button size="small" @click="exportHistoryJson">导出 JSON</el-button>
        </div>
        <el-table v-if="historyRuns.length" :data="historyRuns" size="small" max-height="420">
          <el-table-column type="expand">
            <template #default="{ row }">
              <el-table :data="row.results || []" size="small" border>
                <el-table-column prop="case_id" label="用例ID" width="80" />
                <el-table-column prop="case_title" label="标题" min-width="120" show-overflow-tooltip />
                <el-table-column prop="record_id" label="执行记录" width="90" />
                <el-table-column prop="status" label="状态" width="90" />
                <el-table-column prop="elapsed_time" label="耗时(s)" width="90" />
              </el-table>
            </template>
          </el-table-column>
          <el-table-column prop="id" label="批次#" width="80" />
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column label="汇总" width="140">
            <template #default="{ row }">
              通过 {{ row.summary?.passed ?? 0 }} / 失败 {{ row.summary?.failed ?? 0 }}
            </template>
          </el-table-column>
          <el-table-column label="遇败即停" width="100">
            <template #default="{ row }">
              {{ row.stop_on_failure ? '是' : '否' }}
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!historyLoading" description="暂无执行记录" />
      </div>
      <template #footer>
        <el-button type="primary" @click="historyDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runDialogVisible" title="运行套件（同步）" width="480px" destroy-on-close>
      <el-form label-width="120px" v-loading="runLoading">
        <el-form-item label="附加变量">
          <el-input v-model="runForm.variablesJson" type="textarea" rows="3" placeholder="{}" />
        </el-form-item>
        <el-form-item label="遇败即停">
          <el-switch v-model="runForm.stop_on_failure" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="runLoading" @click="submitRun">开始执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint pre {
  margin: 6px 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow: auto;
  background: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 4px;
}
</style>
