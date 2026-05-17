# 自动化测试平台（毕设工程）

**论文题目：** 基于 Flaky 分析与自适应执行策略的自动化测试平台设计与实现。

工程基于 `Django + Vue 3`，在统一 Web 平台中整合 UI / HTTP / 性能测试；创新点集中在 **Flaky 分析**（`flaky_insight`：Wilson、切换率、EWMA）与 **自适应执行策略**（`run_smart`：按分析结果定重试并入队），形成「分析—决策—执行」闭环。

## 1. 项目定位

本项目不是单一脚本工具，而是完整 Web 测试平台，围绕以下问题构建：

- 手工回归重复成本高，结果不可追溯
- 功能测试与压测脚本割裂，复用率低
- 失败具有波动性（Flaky），但缺少可解释决策机制

系统给出“设计-执行-分析-优化”闭环，支持论文中“问题-方法-实验-结论”的完整叙事。

## 2. 核心能力

### 2.1 测试资产管理

- 项目、环境、用例、套件全生命周期管理
- 用例版本快照与回滚
- 项目成员授权（管理员配置，普通用户使用）

### 2.2 执行引擎

- 单用例执行：支持 `http` / `ui` 混合步骤
- 套件执行：按既定顺序编排，多用例批量运行
- 变量渲染与提取：`{{var}}`、`{{faker.xxx}}`、响应提取 `capture`

### 2.3 性能测试

- 由功能用例自动生成 Locust 脚本
- 异步压测状态机：`queued / running / finished / timeout / error`
- CSV 报告解析 + 前端图表展示
- 防重复提交与压测记录删除（同步清理产物）

### 2.4 Flaky 分析与自适应执行（创新点）

- 质量评分卡（设计完整性/执行稳定性/可运维性）
- **Flaky 分析**（`flaky_insight`）：Wilson 上界、状态切换率、EWMA 融合为风险分与重试建议
- **自适应执行策略**（`run_smart`）：按上述分析自动确定重试次数并入队执行

## 3. 技术栈

- 后端：`Django`、`DRF`、`SimpleJWT`、`Celery`
- 前端：`Vue 3`、`Vite`、`Vue Router`、`Element Plus`、`ECharts`
- 存储：`SQLite`（默认，建议生产使用 PostgreSQL）
- 队列：`Redis`（异步任务推荐）

## 4. 目录结构

```text
.
├─ backend/
│  ├─ api/                     # 业务模型、视图、序列化、执行引擎、任务
│  ├─ core/                    # Django settings/urls/celery
│  ├─ manage.py
│  └─ requirements.txt
├─ frontend/
│  ├─ src/                     # 页面、组件、路由、API 封装
│  ├─ package.json
│  └─ vite.config.js
├─ seed_demo_data.py           # 演示数据重建脚本
├─ docker-compose.yml
└─ requirements.txt
```

## 5. 快速运行（Windows）

### 5.1 后端

```powershell
cd /d d:\test\backend
d:\test\venv\Scripts\python.exe manage.py migrate
d:\test\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

### 5.2 前端（新终端）

```powershell
cd /d d:\test\frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 5.3 访问地址

- 前端：`http://localhost:5173`
- 后端 API：`http://127.0.0.1:8000/api`
- 健康检查：`http://127.0.0.1:8000/api/health/`

## 6. 演示数据重建

```powershell
cd /d d:\test
d:\test\venv\Scripts\python.exe seed_demo_data.py
```

默认账号：

- 管理员：`demo / Demo123456`
- 普通用户：`viewer / Viewer123456`

当前预置资产：

- 项目：2 个（UI 电商项目 + HTTP/压测项目）
- 用例：14 条（UI 6 + HTTP 8）
- 套件：8 个（UI 4 + HTTP 4）

## 7. 关键 API（论文/答辩常用）

### 7.1 认证

- `POST /api/auth/token/`
- `POST /api/auth/token/refresh/`
- `GET /api/auth/me/`

### 7.2 用例执行与分析

- `POST /api/cases/{id}/run/`（支持 `retry_times`）
- `POST /api/cases/{id}/run_smart/`（自适应执行策略，依赖 Flaky 分析结果）
- `GET /api/cases/{id}/quality_insight/`
- `GET /api/cases/{id}/flaky_insight/`
- `GET /api/cases/{id}/experiment_summary/`（执行统计 + Flaky 分析 + 固定重试 vs `run_smart` 对比行，便于论文制表；查询参数与 `flaky_insight` 一致：`target_success`、`max_attempts`）

### 7.3 性能测试

- `POST /api/cases/{id}/run_perf/`
- `GET /api/perf-records/{id}/report/`
- `GET /api/perf-records/{id}/locust/`
- `DELETE /api/perf-records/{id}/`

### 7.4 异步任务状态

- `GET /api/task-status/{task_id}/`

### 7.5 论文策略对照实验脚本

在平台已启动、已具备测试用户与三类用例 ID 的前提下，可用根目录脚本批量执行并导出 CSV，供第 6 章制表与作图：

- `scripts/thesis_experiment.py`：`summary` / `summary-json`（写入 JSON 归档）拉取 `experiment_summary`；`run-series` 对 `run` / `run_smart` 重复触发并轮询 `task_status`，支持 `--label` 写入 CSV 的 `case_label` 列。
- `scripts/thesis_runs_stats.py`：对 `run-series` 产出的 CSV 按用例/策略汇总观测成功率、标准误、耗时的均值与标准差，便于填论文表 6-3（需 `pandas`）。
- `scripts/enrich_thesis_csv_flaky_score.py`：根据 `experiment_summary_case*.json` 为每行 `case_id` 写入 `flaky_score`，便于图 6-3 与重跑作图（需 `pandas`）。
- `docs/images/gen_thesis_diagrams.py`：统一生成论文图 3-1、图 4-1～4-3、图 5-1～5-2、图 6-1～6-3，输出到 `docs/images/thesis_diagrams/`（需 `matplotlib pandas`，并复用 `scripts/figure_fonts.py` 支持中文）。
- `scripts/plot_thesis_ch6_figures.py`：保留为第 6 章旧版实验图脚本；当前论文正文插图以 `docs/images/gen_thesis_diagrams.py` 的统一输出为准。
- `docs/artifacts/`：一次跑通的归档（`thesis_runs_20260424.csv`、`thesis_runs_20260424_enriched.csv`、`experiment_summary_case*.json` 等）与第 6 章表/图可对照；根目录 `data/thesis_runs.csv` 默认在 `.gitignore` 中。
- `docs/md_to_thesis_docx.py`：定稿时由 `毕业论文初稿.md` 生成 `毕业论文初稿.docx`（`pip install python-docx`；在 `docs/` 下运行）。
- `docs/artifacts/README.md`：第 6 章本地大文件归档目录说明；该目录下除 README 外大文件默认不提交 Git。
- `seed_demo_data.py` 重建数据时会多建 3 条以 `[论文]` 开头的策略实验用例（稳定 HTTP / 波动 UI / 高风险 HTTP），见脚本内 `build_thesis_experiment_cases()`。

环境变量：`THESIS_API_BASE`、`THESIS_USERNAME`、`THESIS_PASSWORD`。论文脚本还可在独立虚拟环境安装 `pip install -r scripts/requirements-thesis.txt`（`pandas` / `matplotlib` / `python-docx`）。详见各脚本内 docstring。

## 8. 质量检查

推荐使用提交前检查脚本一次性复核：

```powershell
cd /d d:\test
powershell -ExecutionPolicy Bypass -File scripts/check_submission.ps1
```

该脚本只执行检查，不修改数据库结构、不生成迁移、不改源码。也可按以下命令分步运行：

```powershell
cd /d d:\test\backend
d:\test\venv\Scripts\python.exe manage.py check
d:\test\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
d:\test\venv\Scripts\python.exe -m pytest -q

cd /d d:\test\frontend
npm test
npm run lint
npm run build
```

当前复查基线：

- 后端：`pytest` 94 个用例通过，覆盖率约 77%
- 前端：Vitest 4 个测试文件、11 个用例通过
- 前端质量门禁：`npm run lint` 与 `npm run build` 通过

## 9. 答辩演示路线

详细清单见 `docs/答辩演示清单.md`。
建议答辩前固定使用以下 5～10 分钟路线，避免临场临时找功能入口：

1. 运行 `seed_demo_data.py` 重建演示数据，使用 `demo / Demo123456` 登录。
2. 在“项目/环境”页说明系统支持项目级测试资产管理和环境变量隔离。
3. 在“用例”页打开一条 `[论文]` 或 SauceDemo UI 用例，展示 HTTP / UI 步骤、变量、断言和截图能力。
4. 点击“立即执行”或“自适应执行”，观察任务状态、步骤结果、错误日志和报告入口。
5. 在“套件”页运行一个预置套件，说明多用例顺序编排和套件级运行记录。
6. 在“性能”页展示 Locust 脚本导出、压测记录和响应时间图表。
7. 打开“质量评分 / Flaky 分析”，说明 Wilson、状态切换率、EWMA 如何形成风险分与重试建议。

演示前建议设置：

```powershell
$env:TEST_BROWSER = "edge"
```

如果现场浏览器驱动异常，可直接展示已归档的运行报告和 `docs/artifacts/` 中的论文实验数据。

## 10. Flaky 分析可调参数（环境变量）

可在部署时覆盖以下变量（`core/settings.py` 中自动归一化权重）：

| 变量 | 含义 | 默认 |
|------|------|------|
| `FLAKY_WEIGHT_WILSON` | Wilson 失败率上界权重 | 0.5 |
| `FLAKY_WEIGHT_TRANSITION` | 成败切换率权重 | 0.3 |
| `FLAKY_WEIGHT_EWMA` | EWMA 失败趋势权重 | 0.2 |
| `FLAKY_EWMA_ALPHA` | EWMA 平滑系数 | 0.35 |
| `FLAKY_WILSON_Z` | Wilson 区间 z 值（如 1.96≈95%） | 1.96 |
| `FLAKY_RECENT_WINDOW` | 参与分析的最近执行条数 | 30（5～200） |

API 响应中的 `methodology` 字段说明了模型假设与局限；`flaky_insight` 与 `experiment_summary` 均包含该说明。

## 11. 安全设计要点

- JWT 鉴权与角色隔离
- 项目级数据访问控制（owner/member）
- 出站请求 SSRF 防护（协议/主机/IP）
- SQL 执行约束（关键字、模式、路径越界）
- 敏感字段加密存储与脱敏返回

## 12. 论文与复审建议

建议围绕三个证据链展开：

1. **功能正确性**：UI/HTTP/套件/压测主流程可复现
2. **策略机制可用性**：普通执行 vs 自适应执行（`run_smart`）对比（成功率/耗时/重试次数），重点证明“分析—决策—执行”闭环可复现，不夸大为统计显著提升
3. **稳定性与安全性**：Flaky 风险评估与安全防护验证

推荐实验指标：

- 执行成功率、平均耗时、失败率
- 重试策略前后成功率、耗时与尝试次数变化
- RPS、失败率、响应时间（性能维度）

## 13. 已知边界

- UI 动作目前以通用原子动作为主，可继续封装业务动作库
- ECharts 体积仍较大，可进一步迁移到 `echarts/core`
- 生产部署建议 `PostgreSQL + Redis + 独立 Worker`
- 前端单元测试已覆盖认证与基础组件，但复杂页面交互仍可继续补充
- 执行引擎与部分页面文件体积偏大，后续可拆分为更细的服务层和组件层

## 14. 说明

本项目用于教学与毕业设计演示。  
使用第三方公开站点（SauceDemo / Postman Echo）请遵守其使用条款并控制访问频率。
