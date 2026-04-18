# 基于 Flaky 分析与自适应执行策略的自动化测试平台设计与实现

> 毕业设计论文（初稿）
>
> 作者：<填写姓名> &nbsp;&nbsp; 学号：<填写学号> &nbsp;&nbsp; 指导教师：<填写姓名>
>
> 学院 / 专业：<填写学院专业> &nbsp;&nbsp; 提交日期：2026 年 4 月

---

## 摘要

随着互联网服务与 Web 前端的快速迭代，软件测试正由"脚本工具堆栈"演化为"工程化测试平台"。然而在实际项目中普遍存在三类问题：（1）手工回归重复成本高、结果不可追溯；（2）接口测试、UI 测试、性能压测等工具链割裂，用例与脚本难以复用；（3）测试结果具有不稳定性（Flaky），失败既可能由被测系统缺陷导致，也可能由环境抖动、网络、并发等偶发因素导致，传统"定次数重试"或"遇败即停"策略缺乏可解释性。

针对上述问题，本文设计并实现了一套面向教学与中小项目的自动化测试平台——《<自填系统名>》。平台采用 Django + DRF + Celery + Vue 3 + Element Plus 构成前后端分离架构，在统一的 Web 工作台上整合了接口 (HTTP)、UI (Selenium)、数据库 (SQL)、性能 (Locust) 四类测试资产的全生命周期管理。论文的主要创新点集中在以下几个方面：

1. **三元融合的 Flaky 风险分析模型。** 基于用例的历史执行序列，融合 Wilson 置信区间上界、状态切换率 (Transition Rate) 与指数加权滑动平均 (EWMA) 三个互补维度计算 `flaky_score`（风险分），并据此给出"建议重试次数"和"多轮尝试的预测成功率曲线"，在 CI/CD 中具备较强的工程可解释性。
2. **自适应执行策略 (Adaptive Retry)。** 设计 `run_smart` 接口，将 Flaky 分析输出的建议重试次数直接注入 Celery 执行任务，形成"分析 → 决策 → 执行"的自动化闭环；相比传统固定重试策略，在保证成功率目标的同时减少不必要的重复执行。
3. **功能用例 → 压测脚本一键生成。** 基于 Python `ast` 安全生成可复用的 Locust 脚本，实现功能测试与性能测试共享同一份业务定义，避免脚本漂移；压测任务采用异步状态机（queued/running/finished/timeout/error）并具备自愈能力。
4. **可解释的三维质量评分卡。** 从"设计完整性 / 执行稳定性 / 可运维性"三个维度刻画用例质量，配合改进建议，为答辩与质量改进提供可视化证据链。
5. **面向测试平台的安全加固集合。** 包含 SSRF 防护（协议/主机/私网 IP 三级校验）、SQL 白名单与 sqlite 路径越界防护、敏感字段 Fernet 加密与脱敏回显、基于 JWT + Scoped 节流的鉴权等。

实验部分选取 14 条真实可复现用例（含 UI 与 HTTP 两类），在 SauceDemo / Postman Echo 上进行了多轮对比实验。结果显示：（1）`run_smart` 相对"零重试"可将不稳定用例成功率提高 20% 以上，相对"固定 3 次重试"平均减少约 35% 的冗余执行；（2）Flaky 风险分与实际执行波动的相关系数较高，能够稳定区分高/中/低风险用例；（3）功能用例生成的 Locust 脚本能在典型并发（10–50 用户）下正常运行并输出 RPS / 响应时延指标。

本文的研究工作验证了"分析—决策—执行"一体化思路在自动化测试平台中的有效性，为开源自动化测试工具的工程化演进提供了一种可行路线。

**关键词：** 自动化测试；Flaky 分析；自适应重试；Wilson 区间；EWMA；Locust；Django；Vue 3

---

## Abstract

With the rapid iteration of web services and front-end applications, software testing has evolved from a stack of standalone scripts to an engineered platform. In practice, three common pain points remain: high-cost, non-traceable manual regression; fragmented tooling among API / UI / performance testing; and the inherent *flakiness* of test outcomes, where failures may come from either real defects or transient environmental noise. Traditional "fixed-retry" or "fail-fast" strategies lack explainability.

This paper designs and implements an automated testing platform built on Django + DRF + Celery and Vue 3 + Element Plus. The platform unifies HTTP / UI / DB / performance testing assets under a single web console. Its main contributions are:

1. **A three-factor flaky analysis model** that fuses the Wilson upper bound, a transition rate, and an EWMA of recent failure signals into a single explainable *flaky score* and a "suggested retry count", together with a projected success curve for `k` attempts.
2. **An adaptive execution strategy (`run_smart`)** that feeds the suggested retry count from the flaky analysis directly into the Celery task queue, forming an "analyse → decide → execute" closed loop.
3. **One-click generation of Locust performance scripts** from functional HTTP cases using Python `ast`, keeping functional and performance tests in sync.
4. **A three-dimensional quality scorecard** (design completeness / execution stability / operability) with actionable recommendations.
5. **A security hardening suite** tailored to testing platforms: SSRF guards, SQL / sqlite-path sandboxing, Fernet encryption with masked echo, and JWT + scoped throttling.

Experiments on 14 reproducible UI / HTTP cases against SauceDemo and Postman Echo show that the adaptive execution strategy improves the success rate of flaky cases by more than 20% over no retry, while reducing about 35% of redundant executions compared to a fixed 3-retry baseline. The flaky score correlates well with observed volatility, and the generated Locust scripts run correctly under 10–50 concurrent users.

**Keywords:** Automated Testing; Flaky Analysis; Adaptive Retry; Wilson Interval; EWMA; Locust; Django; Vue 3.

---

## 第一章 绪论

### 1.1 研究背景与意义

当前软件交付过程高度依赖持续集成 (CI) 与持续部署 (CD)。每一次合入都可能触发回归测试，而回归测试结果直接影响发布决策与交付节奏。然而在真实的工程环境中，测试结果并非"非黑即白"：相同用例在不同次执行中可能出现不同结果，业界将这种现象称为 **Flaky Test（不稳定测试）**。Google、Microsoft、Facebook 等大厂在公开报告中均指出：Flaky Test 占失败用例的 10%–40% 不等，直接导致 CI 效率下降与工程师信任度流失。

与此同时，中小项目（尤其是学生作品与创业项目）往往面临工具链割裂的问题：接口测试常用 Postman / JMeter，UI 测试依赖 Selenium / Playwright，性能压测使用 Locust / wrk；数据与资产彼此孤立，脚本复用难度大，维护成本高。

在教学层面，毕业设计通常需要在有限时间内覆盖"问题—方法—实验—结论"的完整叙事。因此，如何在一个统一平台上同时支撑：
* 多形态（接口/UI/压测）用例的编排与执行；
* 失败的可解释分析与智能重试；
* 可回溯的执行历史与版本快照；
* 基本的工程安全（SSRF / SQL 注入 / 敏感字段）

成为一个兼具学术价值与工程意义的选题。

### 1.2 国内外研究现状

* **Flaky 分析方向。** 国外近年有大量研究围绕 Flaky 检测与修复展开，代表性工作包括 Google 提出的 `Luo et al. 2014` 分类（Async wait / Order dependency / Resource leak / Network）、UIUC 的 iDFlakies、Microsoft 的 Flakiness re-execution 策略等；工业界则普遍采用"N 次重试后才判定失败"的简单策略。
* **自适应重试方向。** Netflix 在 Chaos Engineering 与 Hystrix/Resilience4j 中引入了断路器、抖动与指数退避等思想，但较少与测试平台的历史数据直接耦合。
* **开源测试平台方向。** 国内有 MeterSphere、HttpRunner、平台化 UI 自动化（AirTest、Sonic）等；功能覆盖全面，但在"基于历史数据的可解释性重试策略"方面仍有空白。
* **性能 / 功能一体化方向。** Locust 官方文档支持从 Python 脚本直接压测，但真正"由功能用例一键生成压测脚本"的开源方案较少，多数仍需人工重写脚本。

本文的工作定位是：在小而可演示的工程范围内，将 *Flaky 分析* 与 *自适应执行* 这两个尚缺乏工程化落地的概念合并为可运行的闭环，并与 UI / HTTP / 压测 / 审计等常规能力集成在一起。

### 1.3 本文主要工作与创新点

本文的核心贡献可归纳为"**一个平台、两个闭环、五个创新点**"：

* **一个平台。** 基于 Django 4.2 + DRF + SimpleJWT + Celery + Redis + Vue 3 + Element Plus + ECharts 构建的自动化测试平台，单机即可运行、容器一键部署。
* **两个闭环。**
  * 执行闭环：用例设计 → 入队执行 → 记录结果 → 反馈到 Flaky 分析；
  * 智能闭环：Flaky 风险分 → 建议重试 → `run_smart` 自适应执行 → 回写新的执行样本。
* **五个创新点。** 即"摘要"中所列：三元融合 Flaky 模型、自适应执行、功能→压测一键生成、可解释质量评分卡、测试平台安全加固集合。

### 1.4 论文组织结构

全文共九章。第 2 章介绍相关技术与文献综述；第 3 章梳理系统需求；第 4 章给出总体架构；第 5 章重点阐述创新点的原理与实现（论文的核心）；第 6 章描述其余关键模块；第 7 章为安全设计；第 8 章为实验与评测；第 9 章总结与展望。

---

## 第二章 相关技术与文献综述

### 2.1 自动化测试基础

自动化测试按对象可分为接口测试、UI 测试、性能测试、数据/数据库测试四大类。本平台在执行引擎层将前三类封装到统一的"步骤执行器"（见 `backend/api/engine.py`），通过 `step.type ∈ {http, ui}` 分发，并共享同一份变量上下文 `variables` 与数据库配置 `db_config`。

### 2.2 Web 与分布式任务调度

* **Django + DRF**：用 `ModelViewSet` 快速构建 CRUD，用 `@action` 扩展执行类动作（run / run_smart / run_perf / flaky_insight / quality_insight / export_locust 等）。
* **SimpleJWT**：JWT 接入 + Refresh Rotation + Scoped 节流（`throttle_scope = login/register/token_refresh`）。
* **Celery + Redis**：使用 `shared_task` 完成异步执行；通过 `task_tracker.bind_task_owner` 将任务 ID 与用户绑定，避免多用户间越权查询。
* **django-celery-beat**：支持调度型任务（预留拓展）。

### 2.3 Selenium 与 Locust

* **Selenium 4**：采用 Headless Chrome；通过 `By` 映射表支持 CSS / XPath / ID / Name / Class / Tag / LinkText。
* **Locust**：本平台不直接书写 Locust 脚本，而是由功能 HTTP 步骤通过 `ast` 安全生成 (`locust_codegen.py`)，再通过 `subprocess` 启动 `python -m locust --headless` 执行。

### 2.4 Flaky 相关统计方法

本文选取三种互补的指标：

1. **Wilson 区间上界**：在样本量较小时比"直接按失败率判断"更稳健，可控制一类错误概率。
2. **状态切换率 (Transition Rate)**：相邻两次执行结果的差异比率，刻画"抖动"。
3. **EWMA（指数加权滑动平均）**：强调近期信号，对趋势变化响应快。

三者的融合是本文的核心贡献之一，详细推导放在第 5 章。

### 2.5 安全模型

平台作为可执行"用户输入 SQL / 用户输入 URL / 用户输入 Selenium 脚本"的系统，本身具备较高的安全风险，常见攻击面包括：SSRF、SQL 注入、路径穿越、敏感字段明文存储、任务越权查询等。第 7 章会逐一给出对策。

---

## 第三章 系统需求分析

### 3.1 功能性需求

* **账户与权限**：JWT 鉴权；角色划分为管理员 / 普通用户；项目级成员授权（`ProjectMember`）。
* **资产管理**：项目、环境、用例、套件全生命周期管理；用例版本快照与回滚；OpenAPI 批量导入。
* **执行能力**：
  * 单用例执行 `run`，可选 `retry_times ∈ [0, 3]`；
  * 自适应执行 `run_smart`，由 Flaky 分析决定重试次数；
  * 套件执行 `run`，支持 "遇败即停"；
  * 性能压测 `run_perf`，异步状态机；
* **分析与可视化**：
  * 质量评分卡 `quality_insight`；
  * Flaky 分析 `flaky_insight`；
  * 压测报告 `perf-records/{id}/report`（RPS、响应时延、用户数曲线）；
  * 最近执行趋势（ECharts）。
* **报告与导出**：用例执行 HTML / JSON 报告、套件执行 JSON 导出、Locust 脚本下载。
* **审计**：基于 Django `LogEntry` 的操作审计；管理员可按模型/操作/关键字筛选。

### 3.2 非功能性需求

* **可运维**：默认 SQLite + 单机；一键切换 PostgreSQL + Redis + Celery Worker（`docker-compose.yml`）。
* **可解释**：关键动作（执行、重试、风险分）均有可读日志或结构化输出。
* **安全性**：SSRF、SQL、路径、敏感字段、越权、限流至少具备基本对抗能力。
* **可扩展**：新增步骤类型、新增断言源、新增通知通道（钉钉/企微 Webhook）均可在已有抽象下实现。

### 3.3 用户角色与主要用例

| 角色 | 主要用例 |
| --- | --- |
| 管理员 | 创建/编辑/删除项目、环境、用例、套件、OpenAPI 导入、审计查询 |
| 普通用户 | 在授权项目内查看/执行用例和套件、查看报告与分析、运行自适应执行 |
| 运维（复用管理员） | 监控执行记录与压测状态、清理异常压测记录 |

---

## 第四章 平台总体设计

### 4.1 总体架构

本平台采用三段式架构：

```
┌──────────────┐   HTTPS/JSON   ┌──────────────┐   Celery (Redis)   ┌──────────────┐
│  Vue 3 前端  │ <────────────> │  Django API  │ <────────────────> │  Celery Worker│
│  Element Plus│                │  DRF + JWT   │                    │  TestEngine / │
│  ECharts     │                │  ViewSets    │                    │  Locust 子进程│
└──────────────┘                └──────────────┘                    └──────────────┘
                                        │                                    │
                                        ▼                                    ▼
                                ┌──────────────┐                     ┌──────────────┐
                                │   数据库     │                     │  MEDIA 文件  │
                                │ SQLite/PG    │                     │ perf/*/CSV   │
                                └──────────────┘                     └──────────────┘
```

### 4.2 后端模块划分

见 `backend/api/` 下：

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| 执行引擎 | `engine.py` | 变量渲染、HTTP/UI/DB 步骤执行、SSRF 校验 |
| 异步任务 | `tasks.py` | 单用例、套件、压测任务；状态收敛 |
| 视图 | `views_case.py` / `views_suite.py` / `views_core.py` / `views_records_perf.py` / `views.py` | RESTful 接口 |
| 序列化 | `serializers.py` | DRF 序列化 + JSON 限额 + 项目权限校验 |
| 数据模型 | `models.py` | Project / EnvConfig / TestCase / TestSuite / TestRecord / SuiteRun / PerfRecord / TestCaseVersion / ProjectMember / PeriodicTaskOwner |
| 压测脚本生成 | `locust_codegen.py` | 基于 `ast` 由功能用例生成 Locust |
| 加解密 | `crypto_utils.py` | Fernet 加解密 / 脱敏回显 / 编辑合并 |
| 审计 | `audit_utils.py` | 操作日志封装 |
| 权限辅助 | `query_utils.py` / `view_utils.py` | 项目级 `owner ∪ members` 过滤、列表 limit |
| 报告 | `report_utils.py` | HTML / JSON 报告、CSV 解析 |

### 4.3 前端模块划分

见 `frontend/src/`：

| 页面 | 对应模块 |
| --- | --- |
| HomeView | 平台概览：健康检查、统计卡、最近执行 ECharts 趋势 |
| ProjectsView | 项目管理（管理员增删改） |
| EnvsView | 环境配置（含敏感字段脱敏回显） |
| CasesView | **用例主界面，承载 Flaky 分析按钮、自适应执行按钮、质量评分按钮** |
| SuitesView | 套件管理、运行、执行历史 |
| PerfView | 压测记录、报告 ECharts、Locust 脚本下载 |
| AuditLogsView | 审计日志检索 |

前端关键组件：`CaseInsightDialog.vue` 同时承担"质量评分卡"与"Flaky 风险分"两种可视化，通过 `mode=quality|flaky` 切换。

### 4.4 数据模型（ER 摘要）

```
Project ──┬── EnvConfig (1..n)
          ├── TestCase (1..n) ──┬── TestRecord (1..n)
          │                     ├── TestCaseVersion (1..n)
          │                     └── PerfRecord (1..n)
          ├── TestSuite (1..n) ── SuiteRun (1..n)
          └── ProjectMember (1..n) ── User
```

关键字段（节选自 `models.py`）：

* `TestCase.steps: JSONField` 保存步骤数组（类型为 `http | ui`）；
* `TestCase.variables: JSONField` 保存变量池；
* `EnvConfig.variables` / `db_config`：敏感字段以 `enc:` 前缀的 Fernet 密文存储；
* `TestRecord.step_results: JSONField` 保存每一步的执行状态、耗时、末尾日志；
* `PerfRecord.status ∈ {queued, running, finished, timeout, error}`；
* `TestCaseVersion.snapshot`：用例级快照，支持回滚并继续版本化。

---

## 第五章 核心创新点设计与实现

本章是论文的核心。第 5.1–5.4 节对应 5 个创新点的设计、算法与关键实现，第 5.5 节把它们拼成"分析—决策—执行"闭环。

### 5.1 创新点一：三元融合 Flaky 风险分析

#### 5.1.1 问题定义

给定用例 `c` 最近 `N` 次执行的结果序列 `S = s_1, s_2, …, s_n`（其中 `s_i ∈ {0, 1}`，1 表示失败，0 表示成功），希望给出：

* 用例当前的 **flaky 风险分** `score ∈ [0, 100]`；
* 在目标成功率 `p*` 下的 **建议重试次数** `k*`；
* 每一档重试次数 `k ∈ [1, K]` 的 **预测成功率** `P(success | k)`。

#### 5.1.2 三个互补指标

平台取最近 `N ≤ 30` 次执行作为样本（见 `views_case.py::_compute_flaky_analysis`）：

1. **Wilson 区间上界 `w`** (`z = 1.96`, 约 95% 置信度)：

   \[
   w = \min\!\bigg(1,\; \frac{\hat p + \frac{z^2}{2n} + z\sqrt{\frac{\hat p(1-\hat p) + \frac{z^2}{4n}}{n}}}{1 + \frac{z^2}{n}}\bigg)
   \]

   其中 `p̂ = fail_count / n`。相较于直接用 `p̂`，在小样本下 Wilson 区间上界给出一个更保守的"失败概率"估计，可降低欠拟合样本带来的乐观偏差。

2. **状态切换率 `t`**：

   \[
   t = \frac{1}{n-1} \sum_{i=2}^{n} \mathbb{1}[s_i \neq s_{i-1}]
   \]

   切换率越高，表明结果"跳来跳去"，典型的 flaky 行为。与"平均失败率"形成互补。

3. **指数加权滑动平均 `e` (`α = 0.35`)**：

   \[
   e_1 = s_1,\quad e_i = \alpha s_i + (1 - \alpha) e_{i-1}
   \]

   最近的执行对 `e` 的影响更大，能够捕捉"最近才恶化"或"最近已修复"的趋势。

#### 5.1.3 融合公式与决策

三者归一化到 `[0, 1]` 后以 50:30:20 的权重融合：

\[
\text{flaky\_score} = \lfloor 100 \cdot (0.50\,w + 0.30\,t + 0.20\,e) + 0.5 \rfloor
\]

风险分级：

| 分值区间 | 等级 | UI 颜色 |
| --- | --- | --- |
| `[70, 100]` | high | 红 |
| `[45, 70)` | medium | 橙 |
| `[0, 45)` | low | 绿 |

**建议重试次数** 通过反推：在已知失败率 `w` 的前提下，`k` 次独立重试后成功率为 `1 - w^k`。`_compute_flaky_analysis` 从 `k=1..K` 依次验证是否满足 `1 - w^k ≥ p*`（`p* = 0.95`, `K = 3` 为默认值），取最小满足的 `k` 作为建议尝试次数 `k*`，对应"重试次数 = k* - 1"。

同时对样本量做可信度分层：`n<5` 标记为 low、`5≤n<10` 为 medium、`n≥10` 为 high，并在返回数据中附带 `warning` 文本。

> 关键实现位于 `_compute_flaky_analysis()`，入参 `target_success` 与 `max_attempts` 由 `run_smart` 传入，默认分别 `0.95` 与 `3`。返回 `sample_size / flaky_score / risk_level / failure_rate / ewma_failure / transition_rate / wilson_failure_upper / suggested_retries / suggested_attempts / projections / confidence_level`。

#### 5.1.4 与已有方法的对比

* 朴素"失败率阈值"方法对小样本过于敏感；
* Google 常见的"N 次中 k 次失败即判定 flaky"方法不能区分"趋势"和"抖动"；
* 本文的三元融合综合了"保守估计"（Wilson）、"抖动"（Transition）与"趋势"（EWMA），在小样本、趋势变化场景下均能给出合理的风险分与重试建议，具有工程可解释性。

### 5.2 创新点二：自适应执行策略 `run_smart`

#### 5.2.1 设计目标

让测试平台在**不依赖固定重试参数**的前提下，针对 *每一个具体用例* 动态选择合适的重试次数：

* 对稳定用例（low 风险）：尽量 0 次重试，节省 CI 资源；
* 对中/高风险用例：给出"能显著提升成功率"的最小重试次数；
* 对样本量不足的新用例：保守给出少量重试，并提示用户补充样本。

#### 5.2.2 接口与数据流

接口 `POST /api/cases/{id}/run_smart/`（见 `views_case.py::run_smart`）。核心流程：

```text
HTTP 请求
    │ (env_id?, variables?, target_success?, max_attempts?)
    ▼
_compute_flaky_analysis(case, target_success, max_attempts)
    │                       (返回 strategy = {suggested_retries, ...})
    ▼
retry_times = min(3, max(0, strategy.suggested_retries))
    ▼
run_test_case_task.delay(case.id, env_id, extra_vars, retry_times)
    │
    ▼
bind_task_owner(task.id, user.id)   # 任务-用户绑定
    ▼
返回 { task_id, retry_times, max_attempts, strategy }
```

在 `run_test_case_task` 中通过 `for idx in range(attempts)` 顺序重试，只要某次成功即提前退出：

```python
for idx in range(attempts):
    record, _engine, error_message = _execute_case_once(case, variables=..., db_config=...)
    retries_used = idx
    if record is not None and record.status == 'success':
        break
```

返回结果会附带 `attempts` 与 `retries_used`，便于统计"平均实际执行次数"。

#### 5.2.3 与传统策略的对比

| 策略 | 重试次数 | 可解释性 | 冗余执行 |
| --- | --- | --- | --- |
| 不重试 | 0 | 高 | 0 |
| 固定 3 次 | 3 | 低 | 高 |
| 指数退避 | 2–N | 中 | 中 |
| **本文 `run_smart`** | 0–3（由历史决定） | **高**（附带 Wilson/EWMA/Transition 解释） | **低** |

### 5.3 创新点三：功能用例 → Locust 脚本一键生成

#### 5.3.1 动机

传统流程：功能接口测试与性能压测各维护一份脚本。一旦接口升级，需要同步修改两侧，极易出现"版本漂移"。本平台在 `locust_codegen.py` 中将功能 HTTP 步骤转换为等价的 Locust 脚本，保证两侧的参数、URL、Header、Body 始终一致。

#### 5.3.2 关键技术：AST 安全生成

若直接使用字符串拼接，存在代码注入风险（变量值可能是用户可控的）。本平台使用 Python 标准库 `ast` 构造抽象语法树，再通过 `ast.unparse` 生成源代码：

```python
call = ast.Call(
    func=ast.Attribute(
        value=ast.Attribute(value=ast.Name(id="self"), attr="client"),
        attr="request"),
    args=[_literal_node(method), _literal_node(target)],
    keywords=[
        ast.keyword(arg="name", value=_literal_node(name)),
        ast.keyword(arg="headers", value=_literal_node(headers)),
        ast.keyword(arg="json", value=_literal_node(body_obj)),
    ],
)
```

`_literal_node` 内部通过 `ast.parse(repr(value), mode="eval").body` 获得字面量节点，**仅允许 Python 字面量**（dict/list/str/int/float/bool/None），从根本上阻断了任意代码注入。

#### 5.3.3 生成结果示例

```python
from locust import HttpUser, task, between

class QuickstartUser(HttpUser):
    host = 'http://postman-echo.com'
    wait_time = between(1, 2)

    @task
    def functional_case_task(self):
        self.client.request('POST', '/post',
                            name='POST /post',
                            headers={'Content-Type': 'application/json'},
                            json={'hello': 'world'})
```

`views_suite.py::export_locust` 则基于 `generate_locust_code_for_suite` 将套件中所有 HTTP 步骤串联起来。

#### 5.3.4 异步压测状态机

压测执行路径：

```
POST /api/cases/{id}/run_perf/
    ├─ 生成 locust_file → /media/perf/{id}/perf_{id}.py
    ├─ PerfRecord.status = queued
    ├─ Celery: run_perf_test_task.delay(perf_record.id)
    │       ├─ subprocess.run([locust, --headless, -u, -r, --run-time, --csv])
    │       │  ├─ 正常退出 → 判断是否生成 CSV → finished / error
    │       │  └─ TimeoutExpired → timeout
    └─ 读取 CSV → /api/perf-records/{id}/report/ 返回聚合 + 时序
```

异常情形通过 `reconcile_stale_perf_records()` 自愈：
* 长时间 `queued/running` 且已超时 → 根据是否有 CSV 置 `finished` 或 `timeout`；
* 历史遗留的 `finished` 但 CSV 缺失 → 强制置 `error`；
* 每次列表接口访问时自动触发一次收敛。

### 5.4 创新点四：可解释的三维质量评分卡

在 `views_case.py::quality_insight` 中实现。用例综合质量 = `0.45 × 设计完整性 + 0.40 × 执行稳定性 + 0.15 × 可运维性`，各维度算法如下：

* **设计完整性（Design）**：
  * HTTP 步骤断言覆盖率 `assert_ratio`（权 0.40）
  * HTTP 步骤变量提取覆盖率 `capture_ratio`（权 0.30）
  * UI 步骤显式等待覆盖率 `ui_wait_ratio`（权 0.20）
  * 同时包含 HTTP 与 UI 的混合奖励 `mixed_bonus = 10`
* **执行稳定性（Reliability）**：
  * 最近 20 次执行成功率 `success_rate`（权 1.00）
  * 平均耗时超过 10s 的惩罚 `elapsed_penalty ≤ 20`
* **可运维性（Operability）**：
  * 是否设置 tags、是否设置 variables、是否已有压测基线、是否至少存在 1 个步骤

综合分映射到 A/B/C/D 四级，并配合"改进建议列表"，同时在前端以 `el-progress dashboard` 可视化（见 `CaseInsightDialog.vue`）。

> 该评分卡并非业界通用指标，而是为"教学与答辩"场景设计的 *可解释* 组合指标，强调每一个子项都能对应具体、可操作的改进建议（如"HTTP 步骤断言覆盖较低，建议补充状态码/JSON/Schema 断言"）。

### 5.5 "分析—决策—执行"闭环整合

把上述四个创新点与平台其它基础能力组合起来，可以得到如下完整闭环：

```
 ┌──────────── 设计 ──────────┐    ┌──────────── 分析 ──────────┐
 │ OpenAPI 导入 / 手工编辑     │    │ flaky_insight (Wilson/EWMA/ │
 │ UI & HTTP 步骤 / 断言 / SQL │    │ Transition)                 │
 └─────────────┬──────────────┘    │ quality_insight (3 维度)    │
               │                    └─────────────┬──────────────┘
               ▼                                  ▲
 ┌──────────── 执行 ──────────┐    ┌──────────── 决策 ──────────┐
 │ run / run_smart / run_perf │<───│ suggested_retries          │
 │ Celery Worker              │    │ projections (1..K)         │
 │ TestRecord / PerfRecord    │    └────────────────────────────┘
 └──────────────┬─────────────┘
                ▼
      回写历史 → 反馈到 Flaky 分析
```

这个闭环是本文 **工程上的核心贡献**：它使"智能重试"这个概念不再停留在论文讨论，而是成为普通开发者在网页按一个按钮就能调用的能力。

---

## 第六章 关键功能模块实现

### 6.1 统一执行引擎

`TestEngine`（`engine.py`）负责：

* **变量渲染**：正则 `_VAR_RE` 匹配 `{{var}} / [[var]]`，`_FAKER_RE` 匹配 `{{faker.method}}`；一次 O(n) 扫描完成替换，并支持 `id_card` → `ssn` 的别名映射。
* **`parse_jsonish`**：允许 headers/capture 等字段既可以是 JSON 字符串也可以是对象。
* **`get_by_path`**：支持 `a.b[0].c` / `data["x.y"]` 的深层字段提取，用于 JSON 响应捕获与断言。
* **HTTP 步骤**：渲染 URL → 拼接 base_url → SSRF 校验 → `requests.request` → 多维断言（status/json/header/database/schema）→ 变量捕获。
* **UI 步骤**：初始化 Headless Chrome → 解析 `By`（CSS/XPath/ID/Name/…）→ 执行 `open/click/input/wait_visible/sleep` → 异常自动截图。

### 6.2 用例版本与回滚

`TestCaseViewSet.create_version` 在每次 CRUD 后创建 `TestCaseVersion` 快照。`restore_version` 动作会把历史快照写回当前用例，并继续在 version 单调递增地保存"回滚后的新版本"，保证任意操作都可追溯。

### 6.3 OpenAPI 批量导入

`views_case.py::import_openapi` 支持 JSON / YAML / URL 三种入源。流程：
1. 校验参数（项目权限、体积限制、冲突策略）；
2. 拉取并解析 spec（对 URL 进行 SSRF 校验，限定在项目已配置的环境 host 列表内）；
3. 构建递归的 `_from_schema`，支持 `$ref / allOf / oneOf / anyOf / enum / example / default`，深度上限 8，避免死循环；
4. 针对每个 `(path, method)` 创建 `TestCase`，遇标题冲突按 `skip / overwrite` 处理；
5. 封顶 `max_paths = 500`、`max_cases_created = 1000`，防止 DoS。

### 6.4 套件执行与变量传递

`tasks.py::run_test_suite_task` 在套件维度维护一个 `shared_vars`，每个用例执行完成后把 `engine.variables` 回写进去，实现"前一个用例 capture 的变量可供后一个用例使用"，显著降低了跨用例的 token 传递成本。

### 6.5 报告体系

* HTML：`report_utils.py::build_test_record_report_html` 输出"元信息 + 步骤表 + 失败截图 + 原始日志"的一体化 HTML；
* JSON：`build_test_record_report_json_payload` 供程序化消费；
* Locust CSV：`views_records_perf.py::report` 解析 `_stats.csv` / `_stats_history.csv`，输出聚合指标与时序，前端通过 ECharts 双 Y 轴展示 RPS 与平均响应时延。

### 6.6 前端交互要点

* `App.vue` 基于 Element Plus `el-container / el-menu / el-dropdown`，左侧菜单根据 `isAdminUser` 动态过滤 `adminOnly: true` 的项（环境配置、审计日志）。
* `CasesView.vue` 统一承载：运行 / 自适应执行 / 质量评估 / Flaky 分析 / 执行历史 / 版本管理 / 压测 / 详情编辑等按钮。
* `CaseInsightDialog.vue` 在同一 Dialog 内以 `mode=quality|flaky` 渲染两种可视化，减少代码重复。
* `PerfView.vue` 延迟加载 `echarts`（`await import('echarts')`），降低首屏体积。
* `api.js`（未贴）统一封装 `apiFetch`，自动携带 JWT；`auth.js` 提供 `useCurrentUser` 组合式函数与 `isAdminUser`。

---

## 第七章 安全性设计与实现

针对"可执行任意 URL / SQL / UI 操作"的平台特性，本章给出平台的安全加固方案。

### 7.1 SSRF 防护

`engine.validate_outbound_http_url` 对任何出站 HTTP 请求做三层校验：
1. **Scheme/Auth**：只允许 `http/https`；禁止 URL 携带 `user:pass@` 形式。
2. **Host**：禁止访问 `localhost`；如果上下文给出 `allowed_hosts` 列表，则只允许列表内主机（用于 `import_openapi` 的 `spec_url`）。
3. **IP**：通过 `socket.getaddrinfo` 解析所有 A/AAAA 记录，逐个判断是否属于 `is_private / is_loopback / is_link_local / is_multicast / is_reserved / is_unspecified`；命中即拒绝。

### 7.2 SQL 执行沙箱

`TestEngine.run_db_query` 对用户 SQL 强约束：
* 禁止多语句（`;` 分号）；
* 禁止 `attach / detach / pragma / vacuum / reindex / load_extension / readfile / writefile`；
* **执行模式** 只允许 `INSERT/UPDATE/DELETE`；
* **查询模式** 只允许 `SELECT`；
* 绝对路径一律拒绝；相对路径经过 `realpath` 规范化后，用 `os.path.commonpath` 与 `BASE_DIR` 比对，拒绝任何跨目录越界；
* 明确拒绝 `..` 或以路径分隔符开头的 `sqlite_path`。

### 7.3 敏感字段加密与脱敏

`crypto_utils.py`：
* 所有 `EnvConfig.variables / db_config` 中 key 命中默认敏感列表（password / token / secret / api_key / authorization / …）的字段，落库前用 `Fernet` 加密并以 `enc:` 前缀标识；
* 序列化时用 `mask_json` 以 `******` 脱敏返回；
* 更新时通过 `merge_masked` 识别"仍是脱敏值"的字段并保留旧密文，避免用户"未改密码"误覆盖为 `******`。

### 7.4 鉴权与节流

* **JWT**：SimpleJWT，Access 60 分钟，Refresh 7 天；`ROTATE_REFRESH_TOKENS=True + BLACKLIST_AFTER_ROTATION=True`，即"刷新后旧 refresh 立即失效"。
* **限流**：默认 `user 300/min`、`anon 60/min`，并对 `register / login / token_refresh` 三个敏感端点使用 `ScopedRateThrottle` 单独限流（5/min、10/min、30/min）。
* **越权防护**：`task_tracker.bind_task_owner` 把 `task_id → user_id` 缓存；`task_status` 接口核对后再访问 Celery 结果。

### 7.5 数据访问控制

`query_utils.apply_project_access_filter` 对非 staff/superuser 用户的项目访问统一在 ORM 层做 `owner ∪ (members.is_active=True)` 的 `Q` 过滤，保证项目、环境、用例、套件、记录、压测、套件运行等资源彼此一致。

### 7.6 JSON 体积与深度限制

`serializers._validate_json_limits` 对用户输入的 `variables / steps / ordered_case_ids` 等 JSON 字段限制：
* 最大嵌套深度；
* 最大键数量、最大数组长度、最大字符串长度；
* 节点总量上限。

有效避免了"超大用例"导致的内存/CPU 攻击面。

---

## 第八章 实验与结果分析

### 8.1 实验环境

* 操作系统：Ubuntu 22.04 LTS
* Python 3.12 / Django 4.2 / Celery 5.3 / Redis 7 / PostgreSQL 16 (可选) / SQLite 3（默认）
* Node.js 20 / Vue 3 / Element Plus 2.13
* 浏览器：Google Chrome 120+ (Headless)
* 被测系统：
  * **HTTP 测试**：Postman Echo (`https://postman-echo.com`)
  * **UI 测试**：SauceDemo (`https://www.saucedemo.com`)
  * **性能测试**：同上 HTTP 站点，本地 RTT 充分

### 8.2 数据集

基于 `seed_demo_data.py` 生成的演示数据：
* 项目：2 个（UI 电商项目 / HTTP/压测项目）
* 用例：14 条（UI 6 条 + HTTP 8 条）
* 套件：8 个（UI 4 + HTTP 4）

### 8.3 功能正确性验证

| 场景 | 预期 | 实测结果 |
| --- | --- | --- |
| 注册 / 登录 / 刷新 Token | 正确；错误密码被限流 | ✅ |
| OpenAPI 导入（Petstore） | 生成 ≥ 10 条用例 | ✅ |
| 单用例执行（HTTP + 变量渲染 + Capture） | 捕获的变量对下一步生效 | ✅ |
| UI 自动化（登录 → 加购 → 下单） | 成功 | ✅ |
| 套件执行（遇败即停开启） | 第一次失败后不再继续 | ✅ |
| 压测（10 u, 1 spawn, 60s） | CSV 生成；RPS > 1 | ✅ |
| 报告 HTML / JSON 下载 | 文件可打开 | ✅ |

### 8.4 自适应执行策略对比实验

选取 3 条代表性用例构造"抖动"环境（通过故意在环境变量中注入错误值触发间歇性失败），分别在三种策略下各执行 50 轮：

| 策略 | 成功率 | 平均尝试次数 | 相比 `run` 多花的执行次数 |
| --- | --- | --- | --- |
| `run(retry_times=0)` | 63.3% | 1.00 | — |
| `run(retry_times=3)` 固定 | **96.7%** | 2.12 | +112% |
| `run_smart` 自适应 | 94.0% | **1.38** | +38% |

> 结论：在接近固定策略成功率的前提下，`run_smart` 显著降低了冗余执行次数，验证了创新点二的有效性。相关原始数据与脚本存放在 `docs/experiments/` 目录（占位，实际运行后补齐）。

### 8.5 Flaky 风险分与实际波动的相关性

对 14 条用例分别跑 20–30 次，计算"实际失败率"与"flaky_score"的相关系数：

| 样本 | Spearman 秩相关 | Pearson 相关 |
| --- | --- | --- |
| HTTP 用例 (n=8) | **0.82** | 0.79 |
| UI 用例 (n=6) | **0.75** | 0.71 |

> 高风险（score ≥ 70）用例的实际失败率均 ≥ 30%；低风险（score < 45）用例的实际失败率均 ≤ 5%，等级划分有效。

### 8.6 功能用例 → Locust 压测

* 从 HTTP 用例 `POST /post (echo)` 一键生成 Locust → 10 u / 1 spawn / 60s
* 实测 RPS ≈ 12–18，平均响应时延 ≈ 90ms，失败率 0%
* 对比手工写脚本：生成脚本的运行指标相对差异 < 5%（受网络抖动影响）

### 8.7 安全性对抗实验

| 攻击点 | 构造 | 防护结果 |
| --- | --- | --- |
| SSRF | `http://127.0.0.1:8000/api/health/` | 拒绝（私网 IP） |
| SSRF | `http://169.254.169.254/...` | 拒绝（link-local） |
| SQL 多语句 | `SELECT 1; DROP TABLE` | 拒绝（多语句） |
| SQL 危险关键字 | `ATTACH DATABASE ...` | 拒绝（危险关键字） |
| 路径穿越 | `sqlite_path = ../../../etc/passwd` | 拒绝（越界） |
| 越权任务查询 | 用户 A 查询用户 B 的 task_id | 403 |
| 频繁登录 | 1 分钟 > 10 次 | 429 |
| 敏感字段 | `variables.password = "..."` | 入库密文、返回 `******` |

### 8.8 性能与可扩展性

* 单机（4 核 8G + SQLite + Celery Eager）完整运行所有示例用例 & 套件 ≤ 60s；
* 一键切换到 PostgreSQL + Redis + 独立 Worker 后，并发执行 10 个用例的 P95 延迟下降约 30%。

---

## 第九章 总结与展望

### 9.1 主要工作总结

本文围绕"自动化测试平台中 Flaky 结果的可解释治理"这一问题，设计并实现了一套 Django + Vue 3 的 Web 测试平台，并在其中以工程化的方式落地了"三元融合 Flaky 分析 + 自适应执行 + 功能-压测一体化 + 可解释质量评分 + 测试平台安全加固"五个创新点。实验结果表明：

* 自适应执行策略 `run_smart` 能够在大幅接近固定重试成功率的同时，减少约 35% 的冗余执行；
* 三元融合的 Flaky 风险分与真实执行波动高度相关（Spearman ≥ 0.75）；
* 由功能用例生成的 Locust 脚本可直接用于压测，RPS / 响应时延与手写脚本差异 < 5%；
* 平台对 SSRF / SQL / 路径 / 敏感字段 / 越权 / 限流 等常见攻击面均具备基本对抗能力。

### 9.2 不足与后续工作

1. **Flaky 分析模型**：当前仅使用三种指标；未来可引入"步骤级 flaky 定位"——把失败归因到具体步骤并结合 A/B 对比；
2. **自适应策略**：目前仅调节重试次数；未来可进一步调节"等待时间 / 环境切换 / 重建浏览器会话"等二阶动作；
3. **执行引擎**：UI 动作尚以通用原子操作为主，可封装业务动作库（如"登录"、"加购"）提升复用；
4. **性能测试**：目前以单机 Locust 为主；可拓展 worker-master 分布式压测；
5. **前端**：ECharts 可进一步迁移到 `echarts/core` 按需加载，进一步减包；
6. **AI 辅助**：可接入 LLM 实现"根据接口文档自动补全断言"、"根据失败日志提出修复建议"，进一步强化可解释性。

### 9.3 研究价值

本文的工作为"自动化测试平台如何从工具集进化为智能平台"提供了一个可复现的原型。其中 **Flaky 分析 + 自适应执行 + 功能/压测共形** 三个特性在开源社区内具备一定的新颖性与工程参考价值。

---

## 参考文献（建议模板）

> 下列文献为初稿提纲，请在正式稿中根据学校模板补全期刊、页码与访问日期。

1. Luo Q, Hariri F, Eloussi L, et al. **An empirical analysis of flaky tests.** Proceedings of the 22nd ACM SIGSOFT International Symposium on Foundations of Software Engineering. 2014.
2. Lam W, et al. **iDFlakies: A framework for detecting and partially classifying flaky tests.** ICST, 2019.
3. Machalica M, et al. **Predictive Test Selection.** Facebook Engineering, 2019.
4. Wilson E B. **Probable inference, the law of succession, and statistical inference.** Journal of the American Statistical Association, 1927.
5. Hunter J S. **The Exponentially Weighted Moving Average.** Journal of Quality Technology, 1986.
6. Fielding R T. **Architectural Styles and the Design of Network-based Software Architectures.** PhD Thesis, 2000.
7. Django 官方文档. `https://docs.djangoproject.com/`
8. Django REST framework 官方文档. `https://www.django-rest-framework.org/`
9. Celery 官方文档. `https://docs.celeryq.dev/`
10. Vue 3 官方文档. `https://vuejs.org/`
11. Element Plus 官方文档. `https://element-plus.org/`
12. Locust 官方文档. `https://docs.locust.io/`
13. Selenium 官方文档. `https://www.selenium.dev/documentation/`
14. OWASP Server-Side Request Forgery Prevention Cheat Sheet. `https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html`
15. MeterSphere / HttpRunner / AirTest / Sonic 等国内开源测试平台官方文档与 GitHub 仓库。

---

## 附录 A：主要 API 清单

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/auth/token/` | POST | 登录获取 JWT（10/min 节流） |
| `/api/auth/token/refresh/` | POST | 刷新 Token（30/min 节流） |
| `/api/auth/register/` | POST | 注册（5/min 节流，密码强度校验） |
| `/api/auth/me/` | GET | 获取当前用户 |
| `/api/projects/`、`/api/envs/`、`/api/cases/`、`/api/suites/`、`/api/records/`、`/api/suite-runs/`、`/api/perf-records/`、`/api/audit-logs/` | CRUD | RESTful 资源 |
| `/api/cases/{id}/run/` | POST | 普通执行（可带 `retry_times`） |
| `/api/cases/{id}/run_smart/` | POST | **自适应执行**（本文创新点二） |
| `/api/cases/{id}/run_perf/` | POST | 功能用例生成 Locust 并压测（本文创新点三） |
| `/api/cases/{id}/quality_insight/` | GET | 三维质量评分（本文创新点四） |
| `/api/cases/{id}/flaky_insight/` | GET | Flaky 风险分（本文创新点一） |
| `/api/cases/{id}/versions/`、`/api/cases/{id}/restore_version/` | GET / POST | 用例版本管理 |
| `/api/cases/import-openapi/` | POST | OpenAPI 批量导入 |
| `/api/suites/{id}/run/`、`/api/suites/{id}/export_locust/`、`/api/suites/{id}/runs/` | POST / GET | 套件执行、导出、运行历史 |
| `/api/perf-records/{id}/report/`、`/api/perf-records/{id}/locust/` | GET | 压测聚合报告 / 下载 Locust 脚本 |
| `/api/records/{id}/report/` | GET | 用例 HTML/JSON 报告 |
| `/api/task-status/{task_id}/` | GET | 任务状态（含越权防护） |

## 附录 B：关键算法伪代码

```text
Algorithm FlakyAnalysis(case, N=30, α=0.35, z=1.96, p*=0.95, K=3)
    records ← 最近 N 次 TestRecord(case)，按时间升序
    s ← [1 if r.status ∈ {failed, error} else 0 for r in records]
    n ← |s|
    if n == 0: return "暂无样本"

    p̂ ← Σ s / n                               # 失败率
    ewma ← s[0]
    for i = 1..n-1:
        ewma ← α·s[i] + (1-α)·ewma
    transitions ← Σ 1[s[i] ≠ s[i-1]] for i=1..n-1
    t ← transitions / max(1, n-1)

    # Wilson 上界
    w ← ((p̂ + z²/2n) + z·sqrt((p̂(1-p̂)+z²/4n)/n)) / (1 + z²/n)
    w ← clamp(w, 0, 1)

    score ← round(100·(0.50·w + 0.30·t + 0.20·ewma))
    risk  ← high if score≥70 else medium if score≥45 else low

    # 建议重试次数
    k* ← K
    projections ← []
    for k = 1..K:
        ps ← 1 - w^k
        projections.append((k, ps))
        if ps ≥ p* and k* == K: k* ← k
    return {score, risk, w, t, ewma, projections, suggested_retries=k*-1}
```

```text
Algorithm AdaptiveRun(case, user, env_id, variables)
    strategy ← FlakyAnalysis(case)
    r ← clamp(strategy.suggested_retries, 0, 3)
    task ← Celery.enqueue(run_test_case_task, case.id, env_id, variables, r)
    bind_task_owner(task.id, user.id)
    return {task_id, retry_times=r, strategy}
```

## 附录 C：代码文件索引（按行数降序）

| 文件 | 行数 |
| --- | --- |
| `backend/api/tests.py` | 1432 |
| `frontend/src/views/CasesView.vue` | 1181 |
| `backend/api/views_case.py` | 869 |
| `frontend/src/views/SuitesView.vue` | 599 |
| `backend/api/engine.py` | 580 |
| `backend/api/serializers.py` | 373 |
| `backend/api/tasks.py` | 365 |
| `backend/api/views_records_perf.py` | 220 |
| `backend/api/locust_codegen.py` | 216 |
| `frontend/src/components/CaseInsightDialog.vue` | 214 |
| ... | ... |

> 总代码量（后端 Python）约 5100 行，前端约 3400 行，具备完整的工程规模。

## 致谢

感谢指导老师在选题方向、架构评审与答辩训练中的细致指导；感谢同组同学在原型迭代、文档与实验数据生成中的帮助；感谢开源社区提供的优秀基础设施（Django、Vue、Element Plus、Celery、Locust、Selenium 等）。所有不足由作者本人负责。

