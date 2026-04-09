# 基于多维统计模型的 Flaky 测试识别与自适应执行策略研究

> **毕业设计全称**：基于多维统计模型的 Flaky 测试识别与自适应执行策略研究与实现
>
> **英文参考**：Research on Flaky Test Identification and Adaptive Execution Strategy Based on Multi-dimensional Statistical Model

## 1. 研究背景与问题

在持续集成（CI）实践中，**Flaky 测试**（间歇性失败测试）是公认的工程难题。Google 2016 年的研究报告指出，其 CI 系统中约 16% 的测试用例表现出 Flaky 特征，导致大量开发者时间被浪费在排查"假失败"上。

现有工具和框架在面对 Flaky 测试时存在三个核心不足：

| 问题 | 现状 | 本研究的切入点 |
|------|------|---------------|
| **识别粗糙** | 多数框架仅通过"失败率 > 阈值"判定 Flaky，小样本下误判率高 | 引入 Wilson 置信区间解决小样本偏差 |
| **缺乏趋势感知** | 历史均值无法区分"持续恶化"与"偶发波动" | EWMA 指数加权追踪近期趋势 |
| **重试策略僵化** | 静态配置"固定重试 N 次"，无法适应不同用例的风险等级 | 基于概率模型动态推导最优重试次数 |

本研究围绕上述问题，提出一套**可解释的 Flaky 风险量化模型**与**自适应执行策略**，并设计实现了一个自动化测试平台作为验证载体。

## 2. 研究内容与创新点

### 2.1 核心研究贡献（3 项）

#### 创新点一：基于 Wilson-EWMA-Transition 的多维 Flaky 风险评估模型

**研究问题**：如何在有限执行样本下准确量化测试用例的 Flaky 风险程度？

**提出方法**：融合三个正交统计指标构建复合风险模型——

| 指标 | 数学基础 | 解决的问题 |
|------|---------|-----------|
| **Wilson 置信区间上界** | `p̂_upper = (p + z²/2n + z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)` (z=1.96, 95% 置信度) | 小样本下失败率的保守估计——跑了 3 次全通过，不等于"稳定"，Wilson 上界会给出合理的风险上限 |
| **EWMA 失败趋势** | `S_t = α·x_t + (1-α)·S_{t-1}` (α=0.35) | 捕捉时序演化——区分"持续恶化"和"历史偶发"，近期失败权重更高 |
| **状态切换率** | `transitions / (n-1)`，其中 transition = 连续两次执行结果不同 | 识别 Flaky 的核心特征——"时好时坏"的交替模式，区别于"稳定失败"（环境问题） |

**融合策略**：加权复合评分 `flaky_score = 100 × (0.50 × wilson_upper + 0.30 × transition_rate + 0.20 × ewma)`

- Wilson 权重最高（50%）：作为风险的置信上界，决定"最坏可能"
- Transition 次之（30%）：Flaky 的定义性特征是"间歇性"
- EWMA 辅助（20%）：修正趋势偏差

评分映射为 low（<45）/ medium（45-69）/ high（≥70）三级风险等级，**每个分值的来源和含义都可向老师解释清楚**。

**与业界对比**：

| 方法 | 是否处理小样本 | 是否感知趋势 | 是否识别交替模式 | 是否可解释 |
|------|:---:|:---:|:---:|:---:|
| 简单失败率阈值 | 否 | 否 | 否 | 是 |
| 滑动窗口失败计数 | 部分 | 部分 | 否 | 部分 |
| 机器学习分类器 | 是 | 是 | 是 | **否（黑盒）** |
| **本研究方法** | **是** | **是** | **是** | **是** |

#### 创新点二：基于几何分布的自适应重试执行策略

**研究问题**：识别出 Flaky 风险后，如何自动确定最优重试次数以平衡成功率和执行开销？

**提出方法**：将重试建模为独立重复伯努利试验，单次失败概率 `p` 取 Wilson 上界（保守估计），则 n 次尝试后仍失败的概率为 `p^n`，对应预期成功率 `P_success(n) = 1 - p^n`。

给定目标成功率 `P_target`（默认 0.95），求解 `n ≥ log(1 - P_target) / log(p)`，取 `min(n, max_attempts)` 作为建议重试次数。

**`run_smart` 动态闭环**：
```
历史执行记录 → Flaky 模型分析 → 推导 suggested_retries → 注入 Celery 任务参数 → 执行 → 结果写回历史库 → 下次分析更新
```

这不是简单的"if 失败率>0.5 then retry=3"的规则引擎，而是一个**有数学依据的、随数据积累持续自校准**的决策系统。答辩时可以展示：同一个用例在积累更多执行数据后，建议重试次数会随风险变化自动调整。

#### 创新点三：多维度可解释质量评分卡模型

**研究问题**：如何超越"通过/失败"的二元判定，给出测试用例质量的量化评估？

**提出方法**：从三个正交维度构建评分体系——

| 维度 | 权重 | 评估指标 | 量化公式 |
|------|------|---------|---------|
| **设计完整性** | 45% | 断言覆盖率、变量提取率、UI 显式等待率、HTTP+UI 混合加分 | `40%×assert_ratio + 30%×capture_ratio + 20%×wait_ratio + mixed_bonus` |
| **执行稳定性** | 40% | 近 20 次成功率、平均耗时惩罚 | `100×success_rate - elapsed_penalty` |
| **可运维性** | 15% | 标签规范、变量参数化、压测基线覆盖 | `30%×has_tags + 20%×has_vars + 20%×perf_rate + 30%×has_steps` |

综合评分 `overall = 0.45×design + 0.40×reliability + 0.15×operability`，映射为 A（≥85）/ B（≥70）/ C（≥55）/ D（<55）四级，并生成**针对性改进建议**文本。

该评分卡的价值在于：为论文的"实验与分析"章节提供了一套完整的量化评估框架，每个维度、每个权重都有明确的设计理由。

### 2.2 系统设计创新（3 项）

#### 创新点四：功能用例到压测脚本的 AST 安全代码生成

将功能测试与性能测试的割裂问题转化为一个**代码生成问题**：从 HTTP 用例步骤中提取请求规格，通过 Python AST（抽象语法树）构建合法的 Locust 负载测试脚本。

与字符串模板拼接相比，AST 方法天然避免了代码注入风险（恶意请求体不会破坏脚本结构），且生成的代码可通过 `ast.fix_missing_locations` 确保语法正确性。

**一份用例 → 功能验证 + 性能基线**，测试资产复用率从"两套独立脚本"提升到"同源同模型"。

#### 创新点五：HTTP/UI 混合步骤统一执行引擎

设计了一个支持异构步骤类型的统一执行引擎：
- 单个用例内可混合编排 HTTP 接口请求（基于 requests 库）和 UI 浏览器操作（基于 Selenium），共享同一变量上下文
- 变量渲染采用**预编译正则**两阶段替换（先 Faker 占位符后普通变量），O(n) 复杂度
- 断言体系覆盖 7 种模式：状态码、JSON 路径、响应头、正则匹配、数值比较、不等于、JSON Schema 校验
- 支持 `capture` 跨步骤变量提取，HTTP 响应中提取的 token 可直接用于后续 UI 步骤

#### 创新点六：纵深安全防护机制

在测试执行引擎中嵌入多层安全机制，区别于教学项目常见的"能跑就行"：
- **SSRF 防护**：DNS 解析后校验 IP 段（私有/回环/链路本地/多播/保留地址一律拒绝）
- **SQL 注入防护**：危险关键字拦截 + `os.path.realpath` + `os.path.commonpath` 双重路径遍历防御
- **敏感数据加密**：Fernet 对称加密存储 + API 脱敏返回 + 增量合并防覆盖

### 2.3 工程实现亮点（3 项）

#### 亮点七：OpenAPI 规范自动导入

从 OpenAPI/Swagger 文档批量生成 HTTP 测试用例，支持递归解析 `$ref`/`allOf`/`oneOf` Schema，远程 URL 导入时强制主机白名单校验。

#### 亮点八：异步任务全生命周期管理

Celery + Redis 异步架构，支持任务归属追踪（`task_tracker`）、脏状态自动收敛（`reconcile_stale_perf_records`）、套件级变量链路传递。

#### 亮点九：用例版本控制

自动递增版本快照 + 按版本号/ID 回滚 + Django LogEntry 审计日志，形成完整的变更追溯链。

## 3. 实验验证建议

### 3.1 Flaky 模型有效性实验

| 实验 | 方法 | 预期结论 |
|------|------|---------|
| 小样本鲁棒性 | 构造 3/5/10/20/30 条执行记录，对比简单失败率 vs Wilson 上界 | Wilson 在小样本下给出更合理的风险上限 |
| 趋势感知能力 | 构造"前 10 次全通过 + 后 5 次连续失败"序列，对比 EWMA vs 全局均值 | EWMA 能及时反映恶化趋势 |
| Flaky 特征识别 | 构造"交替成功失败"序列 vs"连续失败"序列，对比两者评分 | 高 transition_rate 导致 Flaky 评分显著升高 |

### 3.2 智能重试策略有效性实验

| 实验 | 方法 | 预期结论 |
|------|------|---------|
| 策略对比 | 同一组 Flaky 用例，分别使用固定重试（0/1/2/3 次）vs `run_smart` | `run_smart` 以更少的总执行次数达到相同或更高的成功率 |
| 自适应性验证 | 随着执行次数增加，观察建议重试次数的变化曲线 | 建议值随数据积累趋于稳定，体现自校准特性 |

### 3.3 质量评分卡评估实验

对预置的 14 条用例分别计算质量评分，展示不同设计水平的用例在三个维度上的差异，验证评分卡的区分度和改进建议的针对性。

## 4. 核心能力

### 4.1 测试资产管理

- 项目、环境、用例、套件全生命周期管理
- 用例版本快照与回滚
- 项目成员授权（管理员配置，普通用户使用）

### 4.2 执行引擎

- 单用例执行：支持 `http` / `ui` 混合步骤
- 套件执行：按既定顺序编排，多用例批量运行
- 变量渲染与提取：`{{var}}`、`{{faker.xxx}}`、响应提取 `capture`

### 4.3 性能测试

- 由功能用例自动生成 Locust 脚本
- 异步压测状态机：`queued / running / finished / timeout / error`
- CSV 报告解析 + 前端图表展示
- 防重复提交与压测记录删除（同步清理产物）

### 4.4 智能分析与策略执行

- 质量评分卡（设计完整性/执行稳定性/可运维性）
- Flaky 分析（Wilson 置信区间 + EWMA 趋势 + 状态切换率）
- 智能重试执行 `run_smart`：算法先决策，再自动入队执行

## 5. 技术栈

- 后端：`Django`、`DRF`、`SimpleJWT`、`Celery`
- 前端：`Vue 3`、`Vite`、`Vue Router`、`Element Plus`、`ECharts`
- 存储：`SQLite`（默认，建议生产使用 PostgreSQL）
- 队列：`Redis`（异步任务推荐）

## 6. 目录结构

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

## 7. 快速运行（Windows）

### 7.1 后端

```powershell
cd /d d:\test\backend
d:\test\venv\Scripts\python.exe manage.py migrate
d:\test\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

### 7.2 前端（新终端）

```powershell
cd /d d:\test\frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 7.3 访问地址

- 前端：`http://localhost:5173`
- 后端 API：`http://127.0.0.1:8000/api`
- 健康检查：`http://127.0.0.1:8000/api/health/`

## 8. 演示数据重建

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

## 9. 关键 API（论文/答辩常用）

### 9.1 认证

- `POST /api/auth/token/`
- `POST /api/auth/token/refresh/`
- `GET /api/auth/me/`

### 9.2 用例执行与分析

- `POST /api/cases/{id}/run/`（支持 `retry_times`）
- `POST /api/cases/{id}/run_smart/`（智能重试策略执行）
- `GET /api/cases/{id}/quality_insight/`
- `GET /api/cases/{id}/flaky_insight/`

### 9.3 性能测试

- `POST /api/cases/{id}/run_perf/`
- `GET /api/perf-records/{id}/report/`
- `GET /api/perf-records/{id}/locust/`
- `DELETE /api/perf-records/{id}/`

### 9.4 异步任务状态

- `GET /api/task-status/{task_id}/`

## 10. 质量检查

```powershell
cd /d d:\test\backend
d:\test\venv\Scripts\python.exe manage.py check
d:\test\venv\Scripts\python.exe -m pytest -q

cd /d d:\test\frontend
npm run build
```

## 11. 安全设计要点

- JWT 鉴权与角色隔离
- 项目级数据访问控制（owner/member）
- 出站请求 SSRF 防护（协议/主机/IP）
- SQL 执行约束（关键字、模式、路径越界）
- 敏感字段加密存储与脱敏返回

## 12. 论文章节对应关系

| 论文章节 | 对应系统模块 | 对应代码 |
|---------|------------|---------|
| 第三章：Flaky 风险评估模型 | `flaky_insight` API | `views_case.py: _compute_flaky_analysis()` |
| 第三章：自适应重试策略 | `run_smart` API | `views_case.py: run_smart()` + `tasks.py: run_test_case_task()` |
| 第三章：质量评分卡模型 | `quality_insight` API | `views_case.py: quality_insight()` |
| 第四章：执行引擎设计 | TestEngine | `engine.py` |
| 第四章：代码生成 | Locust codegen | `locust_codegen.py` |
| 第四章：安全机制 | SSRF/SQL 防护 | `engine.py: validate_outbound_http_url()`, `run_db_query()` |
| 第五章：实验验证 | 执行记录 + 分析接口 | `models.py: TestRecord`, 各 insight API |

## 13. 已知边界

- UI 动作目前以通用原子动作为主，可继续封装业务动作库
- ECharts 体积仍较大，可进一步迁移到 `echarts/core`
- 生产部署建议 `PostgreSQL + Redis + 独立 Worker`

## 14. 说明

本项目用于教学与毕业设计演示。  
使用第三方公开站点（SauceDemo / Postman Echo）请遵守其使用条款并控制访问频率。
