<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { Monitor, DataLine, Loading, Download } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { apiFetch } from '../api'

const loading = ref(false)
const records = ref([])
const reportVisible = ref(false)
const reportLoading = ref(false)
const reportRow = ref(null)
const report = ref(null)
const chartRef = ref(null)
let myChart = null

async function loadRecords() {
  loading.value = true
  try {
    const res = await apiFetch('/api/perf-records/')
    records.value = await res.json()
  } finally {
    loading.value = false
  }
}

onMounted(loadRecords)

function getStatusTag(status) {
  if (status === 'running') return 'warning'
  if (status === 'finished') return 'success'
  return 'info'
}

function disposeChart() {
  if (myChart) {
    myChart.dispose()
    myChart = null
  }
}

function renderChart(series) {
  if (!chartRef.value) return
  disposeChart()
  myChart = echarts.init(chartRef.value)

  const x = series.map(i => new Date(i.ts * 1000).toLocaleTimeString())
  const rps = series.map(i => i.rps)
  const avgRt = series.map(i => i.avg_rt_ms)

  myChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['RPS', '平均响应(ms)'] },
    grid: { left: 50, right: 50, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: x },
    yAxis: [
      { type: 'value', name: 'RPS' },
      { type: 'value', name: 'ms' },
    ],
    series: [
      { name: 'RPS', type: 'line', smooth: true, data: rps },
      { name: '平均响应(ms)', type: 'line', smooth: true, yAxisIndex: 1, data: avgRt },
    ],
  })
}

async function openReport(row) {
  reportRow.value = row
  reportVisible.value = true
  reportLoading.value = true
  report.value = null
  disposeChart()
  try {
    const res = await apiFetch(`/api/perf-records/${row.id}/report/`)
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      ElMessage.error(data.detail || '加载压测报告失败')
      return
    }
    report.value = data
    await nextTick()
    if (Array.isArray(data.series) && data.series.length) {
      renderChart(data.series)
    }
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    reportLoading.value = false
  }
}

function locustDownloadFilename(row) {
  const raw = String(row.case_title || 'case')
    .replace(/[/\\:*?"<>|\r\n]+/g, '_')
    .trim() || 'case'
  const short = raw.length > 120 ? raw.slice(0, 120) : raw
  return `locust_perf_${row.id}_${short}.py`
}

async function downloadLocust(row) {
  try {
    const res = await apiFetch(`/api/perf-records/${row.id}/locust/`)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      ElMessage.error(data.detail || '下载失败')
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
</script>

<template>
  <div class="perf-view">
    <div class="page-header">
      <el-button type="primary" @click="loadRecords">刷新记录</el-button>
    </div>

    <el-table v-loading="loading" :data="records" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="case_title" label="关联用例" min-width="150" />
      <el-table-column label="压测配置" width="250">
        <template #default="{ row }">
          <el-tag size="small">用户: {{ row.users }}</el-tag>
          <el-tag size="small" type="info" style="margin-left: 4px">速率: {{ row.spawn_rate }}/s</el-tag>
          <el-tag size="small" type="success" style="margin-left: 4px">时长: {{ row.duration }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="getStatusTag(row.status)">
            <el-icon v-if="row.status === 'running'" class="is-loading"><Loading /></el-icon>
            {{ row.status === 'running' ? '压测中' : '已完成' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="开始时间" width="180" />
      <el-table-column label="结果/脚本" width="220" fixed="right">
        <template #default="{ row }">
          <el-button type="success" link :disabled="row.status === 'running'" @click="openReport(row)">
            <el-icon><DataLine /></el-icon> 查看报告 (CSV)
          </el-button>
          <el-button type="primary" link @click="downloadLocust(row)">
            <el-icon><Download /></el-icon> 下载 Locust
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!records.length" description="暂无压测历史，请从「测试用例」发起压测" />

    <el-dialog
      v-model="reportVisible"
      :title="reportRow ? `压测报告 #${reportRow.id}` : '压测报告'"
      width="900px"
      destroy-on-close
      @closed="disposeChart"
    >
      <div v-loading="reportLoading">
        <div v-if="report && report.summary" style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px">
          <el-tag>请求数: {{ report.summary.requests }}</el-tag>
          <el-tag type="danger">失败数: {{ report.summary.failures }}</el-tag>
          <el-tag type="warning">失败率: {{ (report.summary.fail_rate * 100).toFixed(2) }}%</el-tag>
          <el-tag type="success">RPS: {{ report.summary.rps }}</el-tag>
          <el-tag type="info">Avg: {{ report.summary.avg_rt_ms }}ms</el-tag>
          <el-tag type="info">P50: {{ report.summary.median_rt_ms }}ms</el-tag>
          <el-tag type="info">Min: {{ report.summary.min_rt_ms }}ms</el-tag>
          <el-tag type="info">Max: {{ report.summary.max_rt_ms }}ms</el-tag>
        </div>

        <div v-if="report && report.series && report.series.length" ref="chartRef" style="height: 360px; width: 100%" />
        <el-empty v-else-if="!reportLoading" description="暂无曲线数据（可能未生成 stats_history.csv）" />
      </div>
      <template #footer>
        <el-button @click="reportVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
</style>
