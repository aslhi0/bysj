<script setup>
import { onMounted, ref, nextTick } from 'vue'
import { Monitor, Files, List, Collection } from '@element-plus/icons-vue'
import { apiFetch } from '../api'

const apiStatus = ref('加载中…')
const apiOk = ref(false)
const stats = ref({
  projects: 0,
  cases: 0,
  suites: 0,
  pass_rate: '0%',
})
const recentRecords = ref([])

const chartRef = ref(null)
let myChart = null
let echartsLib = null

async function ensureEcharts() {
  if (!echartsLib) {
    echartsLib = await import('echarts')
  }
  return echartsLib
}

const initChart = async (data) => {
  if (!chartRef.value) return
  const echarts = await ensureEcharts()
  if (myChart) myChart.dispose()
  myChart = echarts.init(chartRef.value)
  
  const dates = data.map(i => i.created_at.split(' ')[0]).reverse()
  const successCount = data.map(i => i.status === 'success' ? 1 : 0).reverse()
  
  const option = {
    title: { text: '最近执行趋势', left: 'center', textStyle: { fontSize: 14, fontWeight: 'normal' } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: [...new Set(dates)].slice(-7) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      data: successCount.slice(-7),
      type: 'line',
      smooth: true,
      areaStyle: { color: 'rgba(103, 194, 58, 0.2)' },
      itemStyle: { color: '#67C23A' }
    }]
  }
  myChart.setOption(option)
}

onMounted(async () => {
  try {
    const res = await fetch('/api/health/')
    const data = await res.json()
    if (res.ok && data.status === 'ok') {
      apiOk.value = true
      apiStatus.value = `后端已连通：${data.service}`
    } else {
      apiStatus.value = '后端响应异常'
    }
  } catch {
    apiStatus.value = '无法连接后端（请先启动 Django: python manage.py runserver）'
  }
  
  try {
    const [p, c, s, r] = await Promise.all([
      apiFetch('/api/projects/').then(res => res.json()),
      apiFetch('/api/cases/').then(res => res.json()),
      apiFetch('/api/suites/').then(res => res.json()),
      apiFetch('/api/records/recent/').then(res => res.json()),
    ])
    stats.value.projects = p.length || 0
    stats.value.cases = c.length || 0
    stats.value.suites = s.length || 0
    
    recentRecords.value = r || []
    
    await nextTick()
    await initChart(r)
    
    const passed = r.filter(i => i.status === 'success').length
    stats.value.pass_rate = r.length ? `${Math.round((passed / r.length) * 100)}%` : '0%'
  } catch (e) {
    console.error('Failed to load stats', e)
  }
})
</script>

<template>
  <div class="home">
    <el-alert
      :title="apiStatus"
      :type="apiOk ? 'success' : 'warning'"
      show-icon
      :closable="false"
      style="margin-bottom: 24px"
    />

    <el-row :gutter="20">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>测试项目</span>
              <el-icon color="#409eff"><Files /></el-icon>
            </div>
          </template>
          <div class="stat-value">{{ stats.projects }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>测试用例</span>
              <el-icon color="#67c23a"><List /></el-icon>
            </div>
          </template>
          <div class="stat-value">{{ stats.cases }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>测试套件</span>
              <el-icon color="#e6a23c"><Collection /></el-icon>
            </div>
          </template>
          <div class="stat-value">{{ stats.suites }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>最近成功率</span>
              <el-icon color="#f56c6c"><Monitor /></el-icon>
            </div>
          </template>
          <div class="stat-value">{{ stats.pass_rate }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 24px">
      <el-col :span="16">
        <el-card header="执行统计概览">
          <div ref="chartRef" style="height: 300px; width: 100%;"></div>
        </el-card>

        <el-card header="最近执行记录" style="margin-top: 24px">
          <el-table :data="recentRecords" size="small" stripe>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="case_title" label="用例" min-width="120">
              <template #default="{ row }">
                <router-link :to="{ path: '/cases', query: { id: row.case } }" style="color: var(--el-color-primary); text-decoration: none;">
                  {{ row.case_title || '未知用例' }}
                </router-link>
              </template>
            </el-table-column>
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.status === 'success' ? '通过' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="elapsed_time" label="耗时" width="80" />
            <el-table-column prop="created_at" label="时间" width="160" />
          </el-table>
          <el-empty v-if="!recentRecords.length" description="暂无执行数据" />
        </el-card>

        <el-card header="快速上手指南" style="margin-top: 24px">
          <el-steps :active="1" finish-status="success" direction="vertical">
            <el-step title="创建测试项目" description="在「测试项目」模块中定义你的业务系统或项目边界。" />
            <el-step title="编写测试用例" description="支持 HTTP 接口与 UI 自动化混跑，支持 OpenAPI 导入。" />
            <el-step title="组织测试套件" description="将用例按业务流程编排，支持变量传递与批量执行。" />
            <el-step
              title="Flaky 分析与自适应执行"
              description="用例列表中可查看 Flaky 分析；对不稳定用例使用「自适应执行」，由分析结果自动决定重试次数。"
            />
          </el-steps>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card header="系统信息">
          <div class="info-item">
            <span class="label">当前版本:</span>
            <el-tag size="small">v1.0.0-beta</el-tag>
          </div>
          <div class="info-item">
            <span class="label">后端引擎:</span>
            <span>Django 4.2 + Selenium</span>
          </div>
          <div class="info-item">
            <span class="label">前端框架:</span>
            <span>Vue 3 + Vite + Element Plus</span>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stat-card :deep(.el-card__header) {
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: var(--el-text-color-primary);
  text-align: center;
  padding: 10px 0;
}

.info-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
}

.info-item .label {
  color: var(--el-text-color-secondary);
}
</style>
