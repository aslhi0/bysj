# TestFusion — 基于统计分析驱动的多模态 Web 自动化测试平台

> **毕业设计正式题目：** 基于 Flaky 检测与质量评分的一体化 Web 自动测试平台的设计与实现

面向 Web 应用质量保障的全栈自动化测试平台，基于 `Django + Vue 3` 技术栈，在统一执行引擎上融合 UI 测试、HTTP 接口测试与性能压测三种测试模态，并创新性地引入 **Wilson-EWMA 复合 Flaky 检测模型** 与 **多维度可解释质量评分卡**，实现从测试设计、异步执行、智能分析到策略优化的完整闭环。

## 1. 项目定位与研究背景

### 1.1 研究背景

在现代 Web 应用的持续集成/持续交付（CI/CD）实践中，自动化测试面临三大核心痛点：

- **测试孤岛问题**：UI 测试、接口测试、性能测试使用不同工具和脚本，资产无法复用，维护成本高
- **Flaky Test 问题**：测试结果存在随机性波动（学术界称为"Flaky Tests"），传统固定重试策略缺乏理论依据，浪费计算资源
- **质量评估主观化**：测试用例的设计质量、执行稳定性缺乏量化评价体系，质量改进缺少数据驱动的决策支撑

### 1.2 解决思路

本平台围绕 **"设计 → 执行 → 分析 → 优化"** 的质量闭环展开，核心贡献包括：

1. 提出统一执行引擎架构，在同一变量上下文中融合多种测试模态
2. 设计基于统计推断的 Flaky 检测复合模型，驱动自适应重试策略
3. 构建多维度加权质量评分卡，输出可解释的评估结果与优化建议
4. 实现功能用例到性能脚本的 AST 级自动桥接，消除跨测试类型的资产隔离

系统支持论文中 **"问题 → 方法 → 实验 → 结论"** 的完整学术叙事。

## 2. 项目创新点

### 创新点一：统一引擎的多模态测试融合架构

**问题**：现有自动化测试工具（如 Selenium、Postman、Locust）各自独立，测试资产无法跨类型复用。

**方案**：设计了统一的 `TestEngine` 执行引擎，在同一步骤管道（Step Pipeline）中支持 HTTP 和 UI 两类步骤的混合编排。核心特性：

- **共享变量上下文**：HTTP 步骤通过 `capture` 提取的响应字段自动注入引擎变量池，后续 UI 步骤可直接通过 `{{var}}` / `[[var]]` 引用，实现跨模态数据传递
- **双语法变量渲染**：支持 `{{var}}`（Mustache 风格）和 `[[var]]`（方括号风格）两种占位符，以及 `{{faker.xxx}}` 动态数据生成，使用预编译正则实现 O(n) 渲染
- **功能到性能的 AST 桥接**：HTTP 用例可通过 Python `ast` 模块自动转换为合法的 Locust 压测脚本（构建完整 AST 模块树后 `unparse`），而非简单字符串拼接，保证生成代码的语法正确性和可执行性

**学术价值**：解决了多模态测试资产复用率低的工程瓶颈，将"功能验证 → 性能评估"的流程从手工割裂缩短为一键自动化。

### 创新点二：基于 Wilson-EWMA 复合模型的 Flaky 检测与自适应重试策略

**问题**：Flaky Test（不稳定测试）是 CI/CD 中的已知难题（Google 2016 年报告其 16% 的测试为 Flaky）。传统做法使用固定重试次数，缺乏理论依据且浪费资源。

**方案**：提出一种融合三种统计指标的复合评分模型：

| 指标 | 权重 | 作用 | 统计含义 |
|------|------|------|----------|
| **Wilson 置信区间上界** | 50% | 衡量失败率在小样本下的不确定性 | 在 95% 置信水平（z=1.96）下，估计失败概率的保守上界 |
| **EWMA 指数加权移动平均** | 20% | 捕捉失败趋势变化，近期数据权重更高 | 平滑系数 α=0.35，对突发波动敏感 |
| **状态切换率** | 30% | 识别成功/失败交替出现的波动模式 | transitions / (n-1)，值越高波动越大 |

**复合 Flaky 分数** = `min(100, max(0, 100 × (0.50×wilson_upper + 0.30×transition_rate + 0.20×ewma)))`

基于该分数实现 **`run_smart` 智能重试策略**：

1. 根据历史记录计算 Flaky 分数和风险等级（low/medium/high）
2. 利用 Wilson 上界进行几何概率推算：`projected_success = 1 - wilson_upper^attempts`
3. 找到满足用户目标成功率（默认 95%）的最小重试次数
4. 自动入队执行，前端可查看完整分析报告和预测曲线

**学术价值**：将统计推断方法（Wilson Score Interval、EWMA）应用于自动化测试决策，提供了比固定重试更高效且有理论支撑的策略。

### 创新点三：多维度可解释质量评分卡模型

**问题**：测试用例的"好坏"缺乏客观量化标准，团队对用例质量的评估依赖主观经验。

**方案**：构建三维度加权评分卡：

| 维度 | 权重 | 评估指标 |
|------|------|----------|
| **设计完整性** | 45% | HTTP 断言覆盖率、变量提取率、UI 显式等待率、是否混合编排 |
| **执行稳定性** | 40% | 近期成功率、平均耗时（超时惩罚项） |
| **可运维性** | 15% | 标签完整度、变量参数化率、是否有压测基线 |

综合评分输出 **A/B/C/D 四级评级**（优秀/良好/可改进/高风险），并根据各维度短板自动生成 **针对性优化建议**（如"HTTP 步骤断言覆盖较低，建议补充 JSON Schema 断言"）。

**学术价值**：提出了一种面向测试用例的多维质量评估框架，将主观评价转化为可量化、可解释、可追踪的工程指标。

### 创新点四：纵深安全防护体系

**问题**：测试平台允许用户提交 URL 和 SQL 执行，天然面临 SSRF、注入等安全风险。

**方案**：实现多层安全防护：

- **SSRF 防护**：协议白名单（仅 http/https）→ 禁止 URL 携带凭据 → DNS 解析后 IP 分类检查（私有地址 `is_private`、回环 `is_loopback`、链路本地 `is_link_local`、多播 `is_multicast`、保留段 `is_reserved`）→ 可选主机白名单
- **SQL 注入防护**：禁止多语句执行（`;` 检测）→ 危险关键字拦截（ATTACH/PRAGMA/LOAD_EXTENSION 等）→ 读写模式分离（查询仅 SELECT / 执行仅 INSERT/UPDATE/DELETE）→ 长度限制
- **路径遍历防护**：禁止绝对路径 → `..` 检测 → `os.path.realpath` + `os.path.commonpath` 双重校验
- **敏感数据安全**：Fernet 对称加密存储（基于 SECRET_KEY 派生密钥）→ API 返回时自动脱敏（`******`）→ 前端编辑时掩码值自动保留原密文

**学术价值**：展示了安全纵深防御（Defense in Depth）的工程实践，涵盖 OWASP Top 10 中的多项风险缓解。

### 创新点五：异步任务架构与状态自愈机制

**问题**：测试执行耗时长，同步阻塞会导致 HTTP 超时；分布式环境下任务状态可能因异常而停滞。

**方案**：

- **Celery 异步任务引擎**：测试执行、套件运行、性能压测均通过 Celery 异步入队，前端通过轮询 `task_status` 接口获取进度，支持 Redis 和 eager 两种模式（开发环境无需 Redis 即可运行）
- **性能测试五态状态机**：`queued → running → finished / timeout / error`，覆盖正常完成、超时中断、异常终止三种终态
- **状态自愈（Reconciliation）**：`reconcile_stale_perf_records` 函数在每次列表查询时自动检测并修复历史遗留的卡死状态（超时未更新的 running/queued 记录），防止前端永久转圈
- **任务归属隔离**：每个异步任务绑定提交用户 ID（`task_tracker`），查询结果时进行数据白名单过滤（`_sanitize_task_result`），其他用户无法查看或操控

**学术价值**：展示了生产级异步系统的设计模式，包括状态机、幂等性和最终一致性的工程实践。

### 创新点六：OpenAPI 规范驱动的用例自动生成

**问题**：手工编写接口测试用例效率低，且接口变更后容易遗漏。

**方案**：

- 支持 JSON / YAML / URL 三种 OpenAPI 规范输入方式
- 递归解析 `$ref` 引用和 `allOf/oneOf/anyOf` 组合类型，自动构建请求体骨架
- 根据 Schema 类型和格式（date-time、email、uuid 等）生成合理的默认值
- 支持 `skip`（跳过已存在）和 `overwrite`（覆盖已存在）两种冲突策略
- 远端 spec_url 拉取时复用 SSRF 防护机制，限制最大 paths 数（500）和最大用例数（1000），防止恶意规范耗尽资源

**学术价值**：实现了基于接口规范的测试自动生成，减少了接口测试的人工成本，并展示了对 OpenAPI 3.x 规范的深度解析能力。

## 3. 核心能力总览

### 3.1 测试资产管理

- 项目、环境、用例、套件全生命周期管理
- 用例版本快照与回滚
- 项目成员授权（管理员配置，普通用户使用）

### 3.2 执行引擎

- 单用例执行：支持 `http` / `ui` 混合步骤
- 套件执行：按既定顺序编排，多用例批量运行，变量跨用例传递
- 变量渲染与提取：`{{var}}`、`{{faker.xxx}}`、响应提取 `capture`
- 多维断言：状态码 / JSON Path / Header / JSON Schema / 数据库 / 正则

### 3.3 性能测试

- 由功能用例自动生成 Locust 脚本（AST 级代码生成）
- 异步压测状态机：`queued / running / finished / timeout / error`
- CSV 报告解析 + ECharts 前端图表展示（RPS、响应时间趋势）
- 防重复提交与压测记录删除（同步清理产物）

### 3.4 智能分析与策略执行

- 质量评分卡（设计完整性 / 执行稳定性 / 可运维性三维评估）
- Flaky 分析（Wilson 置信区间 + EWMA 趋势 + 状态切换率）
- 智能重试执行 `run_smart`：算法先决策，再自动入队执行
- 预测曲线：不同重试次数下的预计成功率推算

## 4. 技术栈

| 层次 | 技术选型 |
|------|----------|
| 后端框架 | `Django 4.x`、`Django REST Framework`、`SimpleJWT` |
| 异步引擎 | `Celery`、`Redis`、`django-celery-beat` |
| 测试执行 | `Selenium`（UI）、`requests`（HTTP）、`Locust`（性能） |
| 数据生成 | `Faker`（中文区域化）、`jsonschema`（Schema 校验） |
| 安全加密 | `cryptography`（Fernet 对称加密） |
| 前端框架 | `Vue 3`、`Vite`、`Vue Router` |
| UI 组件库 | `Element Plus`（自动导入） |
| 数据可视化 | `ECharts`（异步加载） |
| 数据库 | `SQLite`（默认）/ `PostgreSQL`（Docker / 生产） |
| 容器化 | `Docker`、`Docker Compose`（Postgres + Redis + Backend + Worker + Frontend） |
| CI/CD | `GitHub Actions`（pytest + coverage + npm build） |

## 5. 目录结构

```text
.
├─ backend/
│  ├─ api/
│  │  ├─ models.py              # 数据模型（项目/用例/记录/性能/版本/成员）
│  │  ├─ engine.py              # 统一测试执行引擎（HTTP + UI + 变量渲染）
│  │  ├─ views_case.py          # 用例 CRUD、执行、智能分析、OpenAPI 导入
│  │  ├─ views_core.py          # 项目/环境/审计日志管理
│  │  ├─ views_suite.py         # 套件管理与执行
│  │  ├─ views_records_perf.py  # 记录查询、压测报告、Locust 脚本下载
│  │  ├─ locust_codegen.py      # AST 级 Locust 脚本生成器
│  │  ├─ tasks.py               # Celery 异步任务（执行/压测/自愈）
│  │  ├─ crypto_utils.py        # Fernet 加密/解密/脱敏工具
│  │  ├─ audit_utils.py         # 审计日志工具
│  │  ├─ query_utils.py         # 项目级数据访问控制
│  │  ├─ task_tracker.py        # 异步任务归属追踪
│  │  └─ tests.py               # 后端单元测试
│  ├─ core/                     # Django settings / urls / celery 配置
│  ├─ tests/                    # pytest 扩展测试
│  └─ manage.py
├─ frontend/
│  ├─ src/
│  │  ├─ views/                 # 页面组件（用例/套件/压测/审计等）
│  │  ├─ components/            # 共享组件（质量洞察对话框等）
│  │  ├─ router/                # 路由配置（含角色守卫）
│  │  └─ api.js                 # JWT 认证 + 401 自动刷新
│  ├─ package.json
│  └─ vite.config.js
├─ seed_demo_data.py            # 演示数据重建脚本
├─ docker-compose.yml           # 一键容器编排
├─ .github/workflows/ci.yml    # CI 流水线
└─ requirements.txt
```

## 6. 快速运行（Windows）

### 6.1 后端

```powershell
cd /d d:\test\backend
d:\test\venv\Scripts\python.exe manage.py migrate
d:\test\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

### 6.2 前端（新终端）

```powershell
cd /d d:\test\frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 6.3 访问地址

- 前端：`http://localhost:5173`
- 后端 API：`http://127.0.0.1:8000/api`
- 健康检查：`http://127.0.0.1:8000/api/health/`

## 7. 演示数据重建

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

## 8. 关键 API（论文/答辩常用）

### 8.1 认证

- `POST /api/auth/token/`
- `POST /api/auth/token/refresh/`
- `GET /api/auth/me/`

### 8.2 用例执行与分析

- `POST /api/cases/{id}/run/`（支持 `retry_times`）
- `POST /api/cases/{id}/run_smart/`（智能重试策略执行）
- `GET /api/cases/{id}/quality_insight/`（质量评分卡）
- `GET /api/cases/{id}/flaky_insight/`（Flaky 风险分析）

### 8.3 性能测试

- `POST /api/cases/{id}/run_perf/`
- `GET /api/perf-records/{id}/report/`
- `GET /api/perf-records/{id}/locust/`
- `DELETE /api/perf-records/{id}/`

### 8.4 OpenAPI 导入

- `POST /api/cases/import-openapi/`

### 8.5 异步任务状态

- `GET /api/task-status/{task_id}/`

## 9. 质量检查

```powershell
cd /d d:\test\backend
d:\test\venv\Scripts\python.exe manage.py check
d:\test\venv\Scripts\python.exe -m pytest -q

cd /d d:\test\frontend
npm run build
```

## 10. 安全设计要点

- JWT 鉴权与角色隔离（管理员/普通用户）
- 项目级数据访问控制（owner/member）
- 出站请求 SSRF 防护（协议/主机/IP 多层校验）
- SQL 执行约束（关键字拦截、模式分离、路径越界防护）
- 敏感字段 Fernet 加密存储与 API 自动脱敏
- 登录/注册/刷新接口频率限制（ScopedRateThrottle）
- 异步任务结果白名单过滤（防止内部信息泄露）

## 11. 论文与复审建议

建议围绕三个证据链展开：

1. **功能正确性**：UI/HTTP/套件/压测主流程可复现
2. **策略有效性**：普通执行 vs 智能重试执行对比（成功率/耗时）
3. **稳定性与安全性**：Flaky 风险评估与安全防护验证

推荐实验指标：

- 执行成功率、平均耗时、失败率
- 重试策略前后成功率提升（不同 Flaky 分数区间对比）
- RPS、失败率、响应时间（性能维度）
- 质量评分卡改进前后分值变化

## 12. 工作量说明

| 模块 | 关键文件数 | 核心代码行数（约） | 主要工作内容 |
|------|-----------|-------------------|-------------|
| 后端模型与序列化 | 3 | ~400 | 9 个数据模型、序列化器、约束设计 |
| 统一执行引擎 | 1 | ~580 | HTTP/UI 双模态引擎、变量渲染、断言体系、SSRF/SQL 防护 |
| 业务视图层 | 5 | ~1200 | 用例/套件/记录/压测/审计 CRUD、智能分析、OpenAPI 导入 |
| Celery 异步任务 | 1 | ~360 | 用例执行/套件运行/压测任务/状态自愈 |
| Locust 代码生成 | 1 | ~220 | AST 级压测脚本生成（用例+套件） |
| 安全与工具 | 4 | ~250 | 加密/脱敏/审计/访问控制/任务追踪 |
| 前端页面 | 8 | ~1500 | Vue 3 SPA、ECharts 图表、JWT 认证、路由守卫 |
| 测试代码 | 2 | ~600 | pytest 单元测试（覆盖率 ≥ 70%） |
| DevOps | 3 | ~120 | Docker Compose、CI 流水线、演示数据脚本 |
| **合计** | **~30** | **~5200** | |

## 13. 已知边界

- UI 动作目前以通用原子动作为主，可继续封装业务动作库
- ECharts 体积仍较大，可进一步迁移到 `echarts/core`
- 生产部署建议 `PostgreSQL + Redis + 独立 Worker`

## 14. 说明

本项目用于教学与毕业设计演示。
使用第三方公开站点（SauceDemo / Postman Echo）请遵守其使用条款并控制访问频率。
