# TestSight — 基于可解释分析的全链路自动化测试平台

> **TestSight**: Test + Insight，意为"测试洞察"——不只执行测试，更能看透质量。

面向毕业设计与课程实践的自动化测试平台，基于 `Django + Vue 3`，统一支持 UI、HTTP、性能测试，并提供可解释分析与智能执行策略。

## 1. 项目定位

本项目不是单一脚本工具，而是完整 Web 测试平台，围绕以下问题构建：

- 手工回归重复成本高，结果不可追溯
- 功能测试与压测脚本割裂，复用率低
- 失败具有波动性（Flaky），但缺少可解释决策机制

系统给出"设计-执行-分析-优化"闭环，支持论文中"问题-方法-实验-结论"的完整叙事。

## 1.1 项目创新点

### 核心创新（重点答辩展示）

**创新点一：基于 Wilson 置信区间与 EWMA 的可解释 Flaky 风险评估模型**

区别于业界简单的"失败率"判定，本平台构建了一套多维度 Flaky 风险量化模型：
- **Wilson 置信区间上界**：解决小样本下失败率估计偏差问题，用统计学方法给出失败率的保守上界，避免"只跑了 2 次就判为稳定"的误判
- **EWMA（指数加权移动平均）趋势追踪**：赋予近期执行结果更高权重（α=0.35），捕捉用例稳定性的变化趋势，而非仅看历史均值
- **状态切换率（Transition Rate）**：统计连续执行结果中"成功↔失败"交替出现的频率，识别"间歇性失败"这一 Flaky 核心特征
- **加权复合评分**：三个指标按 50%/30%/20% 融合为 0-100 分 Flaky 风险分，对应 low/medium/high 三级风险等级
- **重试次数预测**：基于 `1 - p^n` 几何分布模型，给出达到目标成功率（默认 95%）所需的最优重试次数

该模型的关键价值在于**可解释性**——每个维度的含义清晰，分析结果可直接用于论文的实验数据表格。

**创新点二：算法驱动的智能执行策略（`run_smart`）**

传统测试框架的重试策略是静态配置（如固定重试 3 次），本平台实现了**"先分析、后决策、再执行"**的动态闭环：
1. 执行前自动调用 Flaky 分析算法，基于历史数据计算风险
2. 根据 Wilson 上界和目标成功率，通过几何分布模型推导最优重试次数
3. 将算法决策结果作为参数自动注入 Celery 异步任务队列
4. 执行结果反馈至历史库，持续优化后续决策

这形成了一个**数据驱动的自适应执行系统**，而非简单的"if-else 规则引擎"。

**创新点三：功能测试到性能测试的自动代码生成桥梁**

业界功能测试和性能测试通常是完全割裂的两套体系（如 Postman + JMeter），本平台创新性地实现了：
- 从已有 HTTP 功能用例中提取请求规格（方法、路径、头部、请求体）
- 通过 **Python AST（抽象语法树）** 安全地生成合法的 Locust 压测脚本，避免字符串拼接带来的注入风险
- 生成的脚本可直接下载查看，也可一键发起异步压测任务
- 压测状态机管理（queued → running → finished/timeout/error）+ 防重复提交 + 产物自动清理

**一份用例同时覆盖功能验证和性能基线**，大幅提高测试资产复用率。

**创新点四：多维度可解释质量评分卡（Quality Scorecard）**

区别于"通过/失败"的二元判定，本平台从三个正交维度量化用例质量：
- **设计完整性**（45% 权重）：断言覆盖率、变量提取率、UI 显式等待使用率、HTTP+UI 混合测试加分
- **执行稳定性**（40% 权重）：近期成功率、平均耗时惩罚项
- **可运维性**（15% 权重）：标签规范、变量参数化、压测基线覆盖

综合评分映射为 A/B/C/D 等级，并附带**针对性改进建议**（如"HTTP 步骤断言覆盖较低，建议补充 Schema 断言"）。该评分卡为论文中的"用例质量评估实验"提供了完整的量化框架。

### 架构与工程创新

**创新点五：HTTP/UI 混合步骤统一执行引擎**

单个测试用例中可混合编排 HTTP 接口请求和 UI 浏览器操作步骤，共享同一变量上下文：
- HTTP 步骤中通过 `capture` 提取的响应数据（如 token、ID），可直接在后续 UI 步骤中通过 `{{var}}` 引用
- 支持 `{{faker.xxx}}` 动态数据生成（基于 Faker 库，覆盖中文姓名、手机号、身份证等）
- 变量渲染使用**预编译正则**，O(n) 复杂度一次性扫描替换，而非 O(n×m) 的逐变量遍历
- 断言体系支持状态码、JSON 路径、响应头、正则匹配、数值比较、JSON Schema 校验等 7 种模式

**创新点六：纵深安全防护体系**

不同于教学项目常见的"能跑就行"，本平台在执行引擎中嵌入了多层安全机制：
- **SSRF 防护**：出站 HTTP 请求强制校验协议（仅 http/https）、禁止 URL 携带凭据、DNS 解析后检查 IP 段（拒绝私有/回环/链路本地/多播/保留地址）
- **SQL 注入防护**：禁止多语句执行、危险关键字（ATTACH/PRAGMA/LOAD_EXTENSION 等）拦截、路径遍历攻击防御（`os.path.realpath` + `os.path.commonpath` 双重校验）
- **敏感数据保护**：环境配置中的密码/Token 等字段使用 Fernet 对称加密存储，API 返回时自动脱敏（`******`）；前端编辑时支持增量合并，未修改的脱敏字段不会覆盖原始密文
- **JWT 鉴权与项目级 RBAC**：管理员/普通用户角色分离，数据查询自动注入项目归属过滤

**创新点七：OpenAPI 规范一键导入与用例自动生成**

支持从 OpenAPI/Swagger 规范文档批量生成测试用例：
- 支持 JSON 直传、YAML 字符串、远程 URL 三种导入方式
- 远程 URL 导入时强制校验目标主机必须匹配项目环境 `base_url`，防止恶意 URL 拉取
- 自动解析请求体 Schema（递归处理 `$ref`、`allOf`、`oneOf`），生成结构化请求模板
- 支持冲突策略（跳过/覆盖），单次最多导入 1000 条用例

### 系统工程创新

**创新点八：完整的异步任务生命周期管理**

- Celery 异步任务队列 + Redis Broker，支持用例执行、套件批量运行、性能测试三类长耗时任务
- **任务归属追踪**（`task_tracker`）：通过 Redis 缓存绑定任务 ID 与用户 ID，确保用户只能查询自己提交的任务状态
- **脏状态自动收敛**（`reconcile_stale_perf_records`）：定时扫描超时未完成的压测记录，根据产物文件存在性自动修正状态
- **套件执行变量传递**：前序用例提取的变量自动注入后续用例的执行上下文，实现业务链路级编排

**创新点九：用例版本控制与快照回滚**

- 每次用例创建/修改自动生成递增版本快照（包含步骤、变量、标签、SQL 等完整字段）
- 支持按版本号或版本 ID 回滚，回滚后自动创建新版本形成完整审计链
- 配合 Django `LogEntry` 审计日志，实现操作可追溯

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

### 2.4 智能分析与策略执行

- 质量评分卡（设计完整性/执行稳定性/可运维性）
- Flaky 分析（Wilson 置信区间 + EWMA 趋势 + 状态切换率）
- 智能重试执行 `run_smart`：算法先决策，再自动入队执行

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
- `POST /api/cases/{id}/run_smart/`（智能重试策略执行）
- `GET /api/cases/{id}/quality_insight/`
- `GET /api/cases/{id}/flaky_insight/`

### 7.3 性能测试

- `POST /api/cases/{id}/run_perf/`
- `GET /api/perf-records/{id}/report/`
- `GET /api/perf-records/{id}/locust/`
- `DELETE /api/perf-records/{id}/`

### 7.4 异步任务状态

- `GET /api/task-status/{task_id}/`

## 8. 质量检查

```powershell
cd /d d:\test\backend
d:\test\venv\Scripts\python.exe manage.py check
d:\test\venv\Scripts\python.exe -m pytest -q

cd /d d:\test\frontend
npm run build
```

## 9. 安全设计要点

- JWT 鉴权与角色隔离
- 项目级数据访问控制（owner/member）
- 出站请求 SSRF 防护（协议/主机/IP）
- SQL 执行约束（关键字、模式、路径越界）
- 敏感字段加密存储与脱敏返回

## 10. 论文与复审建议

建议围绕三个证据链展开：

1. **功能正确性**：UI/HTTP/套件/压测主流程可复现
2. **策略有效性**：普通执行 vs 智能重试执行对比（成功率/耗时）
3. **稳定性与安全性**：Flaky 风险评估与安全防护验证

推荐实验指标：

- 执行成功率、平均耗时、失败率
- 重试策略前后成功率提升
- RPS、失败率、响应时间（性能维度）

## 11. 已知边界

- UI 动作目前以通用原子动作为主，可继续封装业务动作库
- ECharts 体积仍较大，可进一步迁移到 `echarts/core`
- 生产部署建议 `PostgreSQL + Redis + 独立 Worker`

## 12. 说明

本项目用于教学与毕业设计演示。  
使用第三方公开站点（SauceDemo / Postman Echo）请遵守其使用条款并控制访问频率。
