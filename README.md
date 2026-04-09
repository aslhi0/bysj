# AutoTest Platform

面向毕业设计与课程实践的自动化测试平台，基于 `Django + Vue 3`，统一支持 UI、HTTP、性能测试，并提供可解释分析与智能执行策略。

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
