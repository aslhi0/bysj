# AutoTest Platform

面向毕业设计场景的自动化测试平台，采用 `Django + Vue3` 前后端分离架构，支持 UI/接口/性能测试与角色权限控制。

## 项目定位

- 统一管理测试项目、测试用例、测试套件与执行记录
- 提供可视化执行与结果追踪，降低回归成本
- 支持 OpenAPI 导入和 Locust 压测
- 默认内置 `SauceDemo` 电商场景演示数据，便于论文实验

## 技术栈

- 后端：`Django`、`Django REST Framework`、`SimpleJWT`、`Celery`
- 前端：`Vue 3`、`Vite`、`Vue Router`、`Element Plus`、`ECharts`
- 数据与队列：`SQLite`（默认）、`Redis`（用于 Celery）

## 当前核心功能

- 测试项目管理（含成员授权）
- 测试用例管理（HTTP / UI 步骤编排）
- 测试套件管理（有序编排与批量执行）
- 性能测试（用例转 Locust、CSV 报告解析）
- 审计日志与管理员/普通用户隔离

## 目录结构

```text
.
├─ backend/
│  ├─ api/                 # 业务模型、视图、任务、引擎
│  ├─ core/                # Django 配置
│  └─ manage.py
├─ frontend/
│  └─ src/                 # 页面、路由、API
├─ seed_demo_data.py       # 重建 SauceDemo 演示数据
└─ requirements.txt
```

## 本地运行

### 1) 启动后端

```bash
cd backend
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### 2) 启动前端

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000/api`
- 健康检查：`http://127.0.0.1:8000/api/health/`

## 演示数据重建（SauceDemo）

在项目根目录执行：

```bash
python seed_demo_data.py
```

该脚本会清空旧项目/用例/套件并重建：

- 项目：`Demo-SauceDemo-Ecommerce`
- 环境：`https://www.saucedemo.com`
- UI 用例：登录、锁定用户异常、加购、购物车、结算、退出
- 账号：
  - 管理员：`demo / Demo123456`
  - 普通用户：`viewer / Viewer123456`

## 常用检查命令

```bash
# 后端检查 + 测试
cd backend
python manage.py check
pytest -q

# 前端构建
cd ../frontend
npm run build
```

## 安全说明（简版）

- 默认开启 JWT 鉴权
- 出站请求包含基础 SSRF 防护
- 敏感变量字段加密存储
- 普通用户仅可访问被授权项目数据

## 交付建议

- 开发阶段使用 SQLite 即可
- 多人协作或部署建议切换 PostgreSQL
- 压测与异步任务建议启用 Redis + Celery Worker
# AutoTest Platform

面向毕业设计场景的 Web 自动化测试平台，采用 `Django + Vue3` 前后端分离架构，支持接口/功能/性能测试与基础权限控制。

## 1. 项目目标

- 统一管理测试项目、用例、套件与执行记录
- 提供可视化执行与结果追踪，降低测试门槛
- 支持 OpenAPI 导入与 Locust 压测脚本生成
- 在保证可维护性的前提下，保持实现简洁

## 2. 技术栈

- 后端：`Django`、`Django REST Framework`、`SimpleJWT`、`Celery`、`django-celery-beat`
- 前端：`Vue 3`、`Vite`、`Vue Router`、`Element Plus`、`ECharts`
- 存储与队列：`SQLite`（默认）、`Redis`（Celery）

## 3. 核心功能

- **测试项目管理**：项目增删改查、成员授权
- **测试用例管理**：HTTP/UI 步骤编排、参数渲染、断言校验、OpenAPI 导入
- **测试套件管理**：批量编排与执行历史追踪
- **性能测试**：一键发起压测、状态管理、报告查看
- **权限模型**：管理员负责配置与管理，普通用户按授权项目使用

## 4. 目录结构

```text
.
├─ backend/                # Django 后端
│  ├─ api/                 # 业务模块（模型/序列化/视图/任务）
│  ├─ core/                # 配置与路由
│  └─ manage.py
├─ frontend/               # Vue 前端
│  └─ src/                 # 页面、路由、API 封装
├─ seed_demo_data.py       # 演示数据脚本
└─ requirements.txt
```

## 5. 本地运行

### 5.1 后端

```bash
cd backend
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### 5.2 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问：
- 前端：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000/api`

## 6. 初始化演示数据（可选）

在项目根目录执行：

```bash
python seed_demo_data.py
```

该脚本会重建演示项目、用例、套件与账号分配关系，便于快速演示。

## 7. 常见开发命令

```bash
# 后端检查
cd backend
python manage.py check

# 后端测试
pytest

# 前端构建
cd ../frontend
npm run build
```

## 8. 安全与约束（简版）

- 默认开启接口鉴权（JWT）
- 对外部请求做基础 SSRF 防护
- 敏感信息字段使用加密存储
- 普通用户仅能访问被授权项目的数据

## 9. 交付建议

- 开发环境使用 SQLite；若用于多人协作，建议切换 PostgreSQL
- 使用 Redis + Celery Worker/Beat 保障异步任务稳定运行
- 发布前执行一次完整回归（后端测试 + 前端构建 + 关键流程手测）
# AutoTest Platform 毕业设计项目文档

> 项目定位：一个面向接口自动化、业务回归、性能基线验证的测试平台原型。  
> 关键词：`Django`、`DRF`、`Vue3`、`Celery`、`Locust`、`RBAC`、`项目成员授权`。

---

## 1. 项目概述

`AutoTest Platform` 是一个前后端分离的自动化测试平台，面向中小团队的测试资产沉淀与回归提效场景，支持：

- 测试项目、环境、测试用例、测试套件的全生命周期管理
- 接口自动化执行（变量提取、断言、链路编排）
- UI 步骤执行（Selenium，支持基础动作）
- 性能测试（Locust 脚本生成、执行结果读取与可视化）
- 审计日志与管理员/普通用户权限隔离
- 项目成员授权（管理员分配，用户使用）

---

## 2. 课题背景与研究意义

在实际研发协作中，常见问题包括：

- 手工回归重复度高，接口迭代后验证成本激增
- 功能测试、接口测试、性能测试工具链割裂
- 执行结果不可追溯，难以复盘问题
- 权限模型粗放，平台配置与执行边界不清晰

本项目目标是构建一个可演示、可运行、可扩展的工程化平台原型，形成：

`配置 -> 执行 -> 记录 -> 报告 -> 审计` 的测试闭环。

---

## 3. 技术架构

### 3.1 技术栈

- 后端：`Django 4.x` + `Django REST Framework`
- 鉴权：`djangorestframework-simplejwt`
- 异步任务：`Celery`
- 性能压测：`Locust`
- 前端：`Vue 3` + `Vite` + `Element Plus` + `ECharts`
- 数据库：默认 `SQLite`
- 缓存/队列：`Redis`

### 3.2 架构分层

```text
Frontend (Vue3)
  -> REST API (DRF)
    -> Service / ViewSet Layer
      -> Models (Django ORM)
      -> Tasks (Celery)
        -> Engine / Locust / Report Utils
```

### 3.3 项目目录

```text
test/
├─ backend/
│  ├─ api/                     # 业务核心（模型、视图、任务、引擎、序列化）
│  ├─ core/                    # Django settings / urls / celery
│  ├─ media/                   # 执行产物（截图、perf CSV）
│  └─ manage.py
├─ frontend/
│  ├─ src/views/               # 页面层
│  ├─ src/router/              # 路由与权限导航
│  └─ src/api.js               # API 请求封装（含 token refresh）
├─ seed_demo_data.py           # 一键重建答辩演示数据
└─ README.md
```

---

## 4. 核心业务模块说明

### 4.1 测试项目与环境管理

- `Project`：测试资产顶层容器
- `EnvConfig`：环境配置（base_url、变量、数据库配置）
- 支持默认环境，执行时自动解析

### 4.2 用例与套件管理

- `TestCase`：步骤化用例（HTTP / UI）
- `TestSuite`：有序用例集合，可链路串行执行
- `TestCaseVersion`：版本快照，支持回滚演示

### 4.3 执行引擎与任务

- `engine.py`：HTTP/UI 执行、变量渲染、断言、日志
- `tasks.py`：
  - `run_test_case_task`
  - `run_test_suite_task`
  - `run_perf_test_task`
- 记录模型：
  - `TestRecord`（单用例）
  - `SuiteRun`（套件批次）
  - `PerfRecord`（性能任务）

### 4.4 性能测试模块

- 将功能用例转换为 Locust 脚本
- 输出 CSV（stats/stats_history）
- 前端读取并生成摘要指标与曲线图
- 状态机：`queued -> running -> finished/timeout/error`

### 4.5 审计与权限

- 审计日志：关键配置操作可追踪

---

## 5. 权限模型与安全策略

### 5.1 角色定义

- 管理员（`is_staff` 或 `is_superuser`）：
  - 管理项目/环境/用例/套件
  - 管理项目成员
  - 管理审计
- 普通用户：
  - 在授权项目中执行与查看结果
  - 不可进行配置类操作

### 5.2 授权模型

- 项目拥有者：`Project.owner`
- 项目成员：`ProjectMember(project, user, is_active)`
- 访问规则：`owner OR member`

### 5.3 安全加固点

- SSRF 防护（URL 校验、内网地址拦截）
- JWT 刷新 + 黑名单
- 任务结果字段白名单返回（避免敏感信息泄露）
- SQL 执行场景限制（危险关键字与多语句拦截）

---

## 6. 答辩演示数据（已内置）

项目提供一键重建脚本：

- 文件：`seed_demo_data.py`
- 目标：清空旧 demo 数据，重建开源电商链路演示集

### 6.1 演示账号

- 用户名：`demo`
- 密码：`Demo123456`

### 6.2 演示项目

- 项目：`Demo-OpenSource-Ecommerce`
- 环境：`DummyJSON 公网演示环境`（`https://dummyjson.com`）

### 6.3 当前演示规模

- 用例：11 条（接口/功能/性能均已标注）
- 套件：4 个（功能回归、接口回归、功能场景、性能基线）

---

## 7. 快速启动与运行

### 7.1 后端

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### 7.2 前端

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 7.3 重建演示数据

```bash
cd ..
python seed_demo_data.py
```

### 7.4 访问地址

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- 健康检查：`http://localhost:8000/api/health/`

---

## 8. 配置说明（环境变量）

关键配置位于 `backend/core/settings.py`：

- `DJANGO_DEBUG`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_DB_ENGINE` / `POSTGRES_*`
- `CELERY_ALWAYS_EAGER`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

说明：

- 开发环境默认可 `eager` 同步执行 Celery 任务（便于快速演示）
- 生产环境建议 Redis + 独立 worker

---

## 9. API 概览（核心）

### 9.1 认证

- `POST /api/auth/register/`
- `POST /api/auth/token/`
- `POST /api/auth/token/refresh/`
- `GET /api/auth/me/`
- `GET /api/auth/users/`（管理员）

### 9.2 业务资源

- `/api/projects/`
- `/api/envs/`
- `/api/cases/`
- `/api/suites/`
- `/api/records/`
- `/api/suite-runs/`
- `/api/perf-records/`
- `/api/audit-logs/`

### 9.3 任务状态

- `GET /api/task-status/{task_id}/`

---

## 10. 测试与质量现状

### 10.1 检查命令

```bash
python manage.py check
python -m pytest backend/api/tests.py -q
cd frontend && npm run build
```

### 10.2 当前质量基线

- 后端接口与权限链路已具备回归测试
- 关键功能（执行、权限、导入、状态）均覆盖
- 前端可正常构建并支持角色化展示

---

## 11. 答辩演示建议（10 分钟版）

1. 登录管理员账号（展示角色标签）  
2. 进入项目页，查看成员管理  
3. 展示 11 条用例分类（接口/功能/性能）  
4. 运行“电商交易链-功能回归套件”  
5. 展示执行结果（通过率、日志、历史）  
6. 对 `P1/P2` 发起压测，展示性能报告  
7. 切换普通用户，展示“可使用不可配置”权限效果

---

## 12. 已知问题与改进方向

### 12.1 已知限制

- UI 自动化仍以基础动作编排为主，复杂页面适配待增强
- 公网依赖存在不稳定风险，建议后续增加本地 mock 服务
- 性能模块尚未支持分布式 worker 扩展策略

### 12.2 下阶段计划

- 增强断言与模板能力（负例断言、复杂 JSON 校验）
- 增加批量成员管理与更细粒度权限
- 补充 Docker 一键部署与监控指标
- 补充论文中的架构图、时序图与性能对比数据

---

## 13. 里程碑完成度评估（中期）

- 架构完成度：高
- 功能完成度：高（核心链路可跑通）
- 工程完成度：中上（权限、调度、审计、测试齐备）
- 答辩可演示性：高
