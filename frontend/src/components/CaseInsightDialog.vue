<script setup>
import { computed } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: '',
  },
  mode: {
    type: String,
    default: 'quality', // quality | flaky
  },
  data: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:visible'])

function closeDialog() {
  emit('update:visible', false)
}

function qualityLevelTag(level) {
  if (level === 'A') return 'success'
  if (level === 'B') return ''
  if (level === 'C') return 'warning'
  return 'danger'
}

function flakyRiskTag(level) {
  if (level === 'low') return 'success'
  if (level === 'medium') return 'warning'
  if (level === 'high') return 'danger'
  return 'info'
}

function flakyRiskText(level) {
  if (level === 'low') return '低风险'
  if (level === 'medium') return '中风险'
  if (level === 'high') return '高风险'
  return '样本不足'
}

/** experiment_summary 嵌套 flaky_analysis，兼容旧版扁平结构 */
const flaky = computed(() => props.data?.flaky_analysis ?? props.data)
const strategyRows = computed(() =>
  Array.isArray(props.data?.strategy_comparison) ? props.data.strategy_comparison : [],
)
const methodology = computed(() => flaky.value?.methodology)
</script>

<template>
  <el-dialog
    :model-value="props.visible"
    :title="props.title"
    width="760px"
    destroy-on-close
    @update:model-value="(v) => emit('update:visible', v)"
  >
    <div v-loading="props.loading">
      <template v-if="props.mode === 'quality' && props.data">
        <div class="insight-score-head">
          <el-progress
            type="dashboard"
            :percentage="props.data.overall_score"
            :stroke-width="12"
            :color="props.data.overall_score >= 85 ? '#67c23a' : props.data.overall_score >= 70 ? '#409eff' : props.data.overall_score >= 55 ? '#e6a23c' : '#f56c6c'"
          />
          <div class="insight-score-meta">
            <div class="insight-score-title">综合质量分：{{ props.data.overall_score }}</div>
            <el-tag :type="qualityLevelTag(props.data.level)" size="large">
              等级 {{ props.data.level }} · {{ props.data.level_label }}
            </el-tag>
            <div class="insight-score-sub">评分由设计完整性、执行稳定性、可运维性三维度构成</div>
          </div>
        </div>

        <el-divider content-position="left">维度明细</el-divider>
        <div class="insight-dims">
          <el-card shadow="never">
            <template #header>设计完整性</template>
            <el-progress :percentage="props.data.dimensions.design_score" />
          </el-card>
          <el-card shadow="never">
            <template #header>执行稳定性</template>
            <el-progress :percentage="props.data.dimensions.reliability_score" status="success" />
          </el-card>
          <el-card shadow="never">
            <template #header>可运维性</template>
            <el-progress :percentage="props.data.dimensions.operability_score" status="warning" />
          </el-card>
        </div>

        <el-divider content-position="left">关键指标</el-divider>
        <div class="insight-metrics">
          <el-tag>步骤总数: {{ props.data.metrics.steps_total }}</el-tag>
          <el-tag type="success">HTTP: {{ props.data.metrics.http_steps }}</el-tag>
          <el-tag type="info">UI: {{ props.data.metrics.ui_steps }}</el-tag>
          <el-tag>断言覆盖: {{ (props.data.metrics.assertion_coverage * 100).toFixed(0) }}%</el-tag>
          <el-tag>提取覆盖: {{ (props.data.metrics.capture_coverage * 100).toFixed(0) }}%</el-tag>
          <el-tag>成功率: {{ (props.data.metrics.recent_success_rate * 100).toFixed(0) }}%</el-tag>
        </div>

        <el-divider content-position="left">改进建议</el-divider>
        <el-alert
          v-for="(s, idx) in props.data.suggestions"
          :key="idx"
          type="info"
          :closable="false"
          style="margin-bottom: 8px"
        >
          {{ s }}
        </el-alert>
      </template>

      <template v-else-if="props.mode === 'flaky' && props.data && flaky">
        <div class="insight-score-head">
          <el-progress
            type="dashboard"
            :percentage="flaky.flaky_score"
            :stroke-width="12"
            :color="flaky.flaky_score >= 70 ? '#f56c6c' : flaky.flaky_score >= 45 ? '#e6a23c' : '#67c23a'"
          />
          <div class="insight-score-meta">
            <div class="insight-score-title">Flaky 风险分：{{ flaky.flaky_score }}</div>
            <el-tag :type="flakyRiskTag(flaky.risk_level)" size="large">
              {{ flakyRiskText(flaky.risk_level) }}
            </el-tag>
            <div class="insight-score-sub">{{ flaky.message }}</div>
          </div>
        </div>

        <el-divider content-position="left">Flaky 分析指标</el-divider>
        <div class="insight-metrics">
          <el-tag>样本数: {{ flaky.sample_size }}</el-tag>
          <el-tag type="danger">失败率: {{ (flaky.failure_rate * 100).toFixed(1) }}%</el-tag>
          <el-tag type="warning">EWMA失败趋势: {{ (flaky.ewma_failure * 100).toFixed(1) }}%</el-tag>
          <el-tag type="info">状态切换率: {{ (flaky.transition_rate * 100).toFixed(1) }}%</el-tag>
          <el-tag>Wilson上界: {{ (flaky.wilson_failure_upper * 100).toFixed(1) }}%</el-tag>
          <el-tag type="success">建议重试次数: {{ flaky.suggested_retries }}</el-tag>
          <el-tag type="success">建议总尝试次数: {{ flaky.suggested_attempts }}</el-tag>
        </div>

        <el-divider content-position="left">重试成功率预测</el-divider>
        <div class="insight-metrics" v-if="Array.isArray(flaky.projections) && flaky.projections.length">
          <el-tag
            v-for="item in flaky.projections"
            :key="item.attempts"
            type="info"
          >
            {{ item.attempts }} 次尝试 ≈ {{ (item.projected_success * 100).toFixed(1) }}% 成功率
          </el-tag>
        </div>

        <template v-if="strategyRows.length">
          <el-divider content-position="left">策略对比（论文制表）</el-divider>
          <el-table :data="strategyRows" stripe size="small" class="strategy-table">
            <el-table-column prop="label" label="策略" min-width="220" show-overflow-tooltip />
            <el-table-column prop="retry_times" label="retry_times" width="100" align="center" />
            <el-table-column prop="max_attempts" label="总尝试" width="88" align="center" />
            <el-table-column label="投影成功率(≥一次)" width="160" align="center">
              <template #default="{ row }">
                {{
                  row.projected_at_least_one_success == null
                    ? '—'
                    : (row.projected_at_least_one_success * 100).toFixed(1) + '%'
                }}
              </template>
            </el-table-column>
          </el-table>
        </template>

        <el-collapse v-if="methodology" class="methodology-collapse">
          <el-collapse-item title="模型假设与局限（方法论）" name="meta">
            <p class="methodology-p"><strong>有效权重</strong>：Wilson {{ methodology.weights?.wilson_failure_upper }} · 切换率 {{ methodology.weights?.transition_rate }} · EWMA {{ methodology.weights?.ewma_failure }}（EWMA α={{ methodology.ewma_alpha }}）</p>
            <p class="methodology-h">假设</p>
            <ul class="methodology-ul">
              <li v-for="(a, i) in methodology.assumptions" :key="'a'+i">{{ a }}</li>
            </ul>
            <p class="methodology-h">局限</p>
            <ul class="methodology-ul">
              <li v-for="(b, i) in methodology.limitations" :key="'b'+i">{{ b }}</li>
            </ul>
          </el-collapse-item>
        </el-collapse>

        <el-alert type="success" :closable="false" style="margin-top: 14px">
          Flaky 分析融合 Wilson 上界、状态切换率与 EWMA；建议重试与「自适应执行」按钮共用同一套决策结果。
        </el-alert>
      </template>

      <el-empty v-else-if="!props.loading" :description="props.mode === 'quality' ? '暂无评分数据' : '暂无 Flaky 分析数据'" />
    </div>
    <template #footer>
      <el-button type="primary" @click="closeDialog">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.insight-score-head {
  display: flex;
  align-items: center;
  gap: 24px;
}

.insight-score-meta {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.insight-score-title {
  font-size: 22px;
  font-weight: 700;
}

.insight-score-sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.insight-dims {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.insight-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.strategy-table {
  width: 100%;
}

.methodology-collapse {
  margin-top: 12px;
}

.methodology-p {
  font-size: 13px;
  line-height: 1.5;
  margin: 0 0 10px;
  color: var(--el-text-color-regular);
}

.methodology-h {
  font-size: 13px;
  font-weight: 600;
  margin: 8px 0 4px;
}

.methodology-ul {
  margin: 0 0 8px 16px;
  padding: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-secondary);
}

@media (max-width: 900px) {
  .insight-score-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .insight-dims {
    grid-template-columns: 1fr;
  }
}
</style>
