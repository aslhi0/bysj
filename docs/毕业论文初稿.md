# 基于 Flaky 分析与自适应执行策略的自动化测试平台设计与实现

> **修订说明（相对早期初稿与外部生成稿）**  
> 1. **与仓库代码对齐**：Flaky 核心算法已独立为 `backend/api/flaky_analysis.py`，权重与窗口可通过环境变量 `FLAKY_*` 配置；`views_case._compute_flaky_analysis` 仅为调用封装。新增 **`experiment_summary`** 接口与响应字段 **`methodology`**（假设/局限）。  
> 2. **数据诚信**：摘要或第 8 章中出现的百分比、相关系数等，凡未在你本人环境中重复实验得到者，**须在定稿时替换为实测值或改为定性表述**；下文中已用「示例/待实测」标明。  
> 3. **附录行数**：文件行数随迭代变化，以本地 `wc`/IDE 为准，表中为合并时的参考值。

---

> 毕业设计论文（初稿）  
>  
> 作者：\<填写姓名\> &nbsp;&nbsp; 学号：\<填写学号\> &nbsp;&nbsp; 指导教师：\<填写姓名\>  
>  
> 学院 / 专业：\<填写学院专业\> &nbsp;&nbsp; 提交日期：2026 年 4 月

---

## 摘要

随着互联网服务与 Web 前端的快速迭代，软件测试正由「脚本工具堆栈」演化为「工程化测试平台」。然而在实际项目中普遍存在三类问题：（1）手工回归重复成本高、结果不可追溯；（2）接口测试、UI 测试、性能压测等工具链割裂，用例与脚本难以复用；（3）测试结果具有不稳定性（Flaky），失败既可能由被测系统缺陷导致，也可能由环境抖动、网络、并发等偶发因素导致，传统「定次数重试」或「遇败即停」策略缺乏可解释性。

针对上述问题，本文设计并实现了一套面向教学与中小项目的自动化测试平台（工程仓库中可命名为《自动化测试平台》或自填系统名）。平台采用 Django + DRF + Celery + Vue 3 + Element Plus 构成前后端分离架构，在统一的 Web 工作台上整合了接口（HTTP）、UI（Selenium）、数据库（SQL）、性能（Locust）等测试资产的全生命周期管理。论文的主要工作集中在以下几个方面：

1. **三元融合的 Flaky 风险分析模型。** 基于用例的历史执行序列，融合 Wilson 置信区间上界、状态切换率（Transition Rate）与指数加权滑动平均（EWMA）三个互补维度计算 `flaky_score`，并给出建议重试次数与多轮尝试的预测成功率曲线；权重支持环境变量配置，接口返回 **`methodology`** 说明假设与局限。
2. **自适应执行策略。** 设计 `run_smart` 接口，将 Flaky 分析输出的建议重试次数注入 Celery 执行任务，形成「分析 → 决策 → 执行」闭环。
3. **功能用例 → 压测脚本生成。** 基于 Python `ast` 安全生成 Locust 脚本，实现功能与压测共享同一份业务定义；压测任务采用异步状态机管理。
4. **可解释的三维质量评分卡。** 从「设计完整性 / 执行稳定性 / 可运维性」刻画用例质量，配合改进建议。
5. **面向测试平台的安全加固。** SSRF 防护、SQL 与 SQLite 路径约束、敏感字段加密与脱敏、JWT 与限流等。

**实验与数据说明：** 平台提供 `experiment_summary` 便于固定重试与自适应策略的对比制表。摘要中若需列举「成功率提升比例、相关系数」等量化结论，**须与第 8 章实测数据一致**；定稿前请勿使用未重复实验支撑的具体数字。

**关键词：** 自动化测试；Flaky 分析；自适应重试；Wilson 区间；EWMA；Locust；Django；Vue 3

---

## Abstract

With the rapid iteration of web services and front-end applications, software testing has evolved from standalone scripts toward engineered platforms. Common pain points include non-traceable manual regression, fragmented API/UI/performance tooling, and flaky outcomes where failures may stem from defects or transient noise. Fixed-retry and fail-fast strategies often lack explainability.

This thesis presents a Django + DRF + Celery + Vue 3 + Element Plus platform that unifies HTTP, UI, database, and performance assets. Contributions include: (1) a three-factor flaky risk model (Wilson upper bound, transition rate, EWMA) with configurable weights and explicit methodology metadata; (2) an adaptive `run_smart` execution path integrated with Celery; (3) AST-based Locust generation from functional HTTP steps; (4) a three-dimensional quality scorecard; (5) security controls including SSRF guards and SQL/path sandboxing. Quantitative claims in the thesis body must be backed by repeated experiments documented in Chapter 8.

**Keywords:** Automated Testing; Flaky Analysis; Adaptive Retry; Wilson Interval; EWMA; Locust; Django; Vue 3.

---

## 第一章 绪论

### 1.1 研究背景与意义

持续集成（CI）与持续部署（CD）已成为软件交付常态。回归测试结果影响发布节奏，但「相同用例多次执行结果不一致」的 Flaky 现象广泛存在，导致 CI 信噪比下降与人力浪费。与此同时，接口、UI、压测工具链割裂，资产难以复用。毕业设计需要在有限周期内形成「问题—方法—系统—验证」的完整叙事，因此构建统一平台并嵌入可解释的 Flaky 治理与自适应执行，兼具工程与教学价值。

### 1.2 国内外研究现状

Flaky 检测与分类、重试策略、测试平台工程化均有大量工作与开源产品。工业界常见「固定 N 次重试」；较少在中小体量可部署平台内，将**历史统计、可解释风险分与任务参数**贯通为默认能力。本文定位：在可演示的工程范围内，实现「分析—决策—执行」闭环，并与 UI/HTTP/压测/审计集成。

### 1.3 本文主要工作与创新点

概括为「一个平台、两个闭环、五个技术点」：统一 Web 平台；执行闭环（设计→执行→记录）与智能闭环（Flaky 分析→建议重试→`run_smart`→新样本）；创新点对应摘要中五条。

### 1.4 论文组织结构

全文分九章：第 2 章技术与文献；第 3 章需求；第 4 章总体架构；第 5 章核心方法（Flaky、自适应、Locust、质量分、闭环）；第 6 章其它功能实现；第 7 章安全；第 8 章实验；第 9 章总结与展望。

---

## 第二章 相关技术与文献综述

### 2.1 自动化测试与执行引擎

平台在执行层以步骤为单元，`step.type ∈ {http, ui}` 分发，共享变量上下文与（可选）数据库配置。HTTP 支持断言、JSON 路径提取等；UI 基于 Selenium。

### 2.2 Web 与任务调度

Django + DRF 提供 REST API；SimpleJWT 鉴权；Celery + Redis 承载异步执行；`task_tracker` 绑定任务与用户，降低越权查询风险。

### 2.3 Selenium 与 Locust

UI 采用 Headless Chrome；Locust 脚本由功能 HTTP 步骤经 `ast` 生成（`locust_codegen.py`），避免手写脚本与功能用例漂移。

### 2.4 Wilson、切换率与 EWMA

Wilson 区间在小样本下较点估计稳健；切换率刻画成败抖动；EWMA 强调近期失败趋势。三者融合见第 5 章。

### 2.5 安全

平台执行用户配置的 URL 与 SQL，需 SSRF 防护、SQL 白名单与路径约束等，第 7 章展开。

---

## 第三章 系统需求分析

### 3.1 功能性需求（摘要）

账户与项目级权限；项目/环境/用例/套件/版本；单用例与套件执行；`run`/`run_smart`/压测；`quality_insight`/`flaky_insight`/**`experiment_summary`**；报告与审计。

### 3.2 非功能性需求

可部署（SQLite 单机 / PostgreSQL+Redis 生产）；可解释（方法论字段、策略对比表）；安全与限流；可扩展（Flaky 权重可配）。

### 3.3 用户角色

管理员维护资产与审计；普通用户在授权项目内执行与查看分析。

---

## 第四章 平台总体设计

### 4.1 总体架构

浏览器 Vue SPA ↔ Django API ↔ Celery Worker（TestEngine / Locust 子进程）↔ SQLite 或 PostgreSQL；媒体目录存放压测产物等。

```
┌──────────────┐   HTTPS/JSON   ┌──────────────┐   Celery (Redis)   ┌──────────────┐
│  Vue 3 前端  │ <────────────> │  Django API  │ <────────────────> │ Celery Worker│
│  Element Plus│                │  DRF + JWT   │                    │ TestEngine / │
│  ECharts     │                │  ViewSets    │                    │ Locust 子进程│
└──────────────┘                └──────────────┘                    └──────────────┘
                                       │                                    │
                                       ▼                                    ▼
                               ┌──────────────┐                     ┌──────────────┐
                               │   数据库      │                     │  MEDIA 等    │
                               │ SQLite/PG    │                     │ perf/*/CSV   │
                               └──────────────┘                     └──────────────┘
```

### 4.2 后端模块（与 `backend/api/` 对应）

| 模块 | 文件 | 职责 |
|------|------|------|
| Flaky 分析 | **`flaky_analysis.py`** | Wilson/切换率/EWMA 融合、策略对比行构造 |
| 执行引擎 | `engine.py` | HTTP/UI/SQL、SSRF |
| 任务 | `tasks.py` | 用例/套件/压测 |
| 视图 | `views_case.py` 等 | REST、`run_smart`、`experiment_summary` |
| 序列化 | `serializers.py` | 校验与限额 |
| 模型 | `models.py` | 领域实体 |
| Locust 生成 | `locust_codegen.py` | AST 安全生成 |
| 加解密 | `crypto_utils.py` | Fernet、脱敏 |

### 4.3 前端模块（摘要）

`CasesView` 承载运行、自适应执行、质量与 Flaky 分析；`CaseInsightDialog` 展示质量分或 Flaky（数据来自 **`experiment_summary`** 时可含策略对比表与方法论文本）。

### 4.4 数据模型（ER 摘要）

Project → EnvConfig / TestCase / TestSuite / ProjectMember；TestCase → TestRecord / TestCaseVersion / PerfRecord；TestSuite → SuiteRun。

---

## 第五章 核心创新点设计与实现

### 5.1 三元融合 Flaky 风险分析

#### 问题定义

给定最近若干次执行构成的成败序列，估计风险分、建议重试次数，并在独立尝试假设下给出「至少一次成功」的近似投影。

#### 三个指标与融合

1. **Wilson 失败率上界** \(w\)：控制小样本乐观偏差（置信度由 `FLAKY_WILSON_Z` 等参数决定）。  
2. **切换率** \(t\)：相邻结果不一致比例。  
3. **EWMA** \(e\)：平滑系数默认 `FLAKY_EWMA_ALPHA`，可配置。

融合形式为：

\[
\text{flaky\_score} = \left\lfloor 100 \cdot (w_1 w + w_2 t + w_3 e) + 0.5 \right\rfloor
\]

其中 \(w_1,w_2,w_3\) 由环境变量 **`FLAKY_WEIGHT_WILSON` / `FLAKY_WEIGHT_TRANSITION` / `FLAKY_WEIGHT_EWMA`** 读取并在服务端**归一化**（默认等价于 0.5/0.3/0.2）。风险等级阈值仍可按实现划分高/中/低。

**建议重试：** 在 Wilson 上界 \(w\) 下用 \(1-w^k\) 作为「至少一次成功」的保守投影，在 `target_success` 与 `max_attempts` 约束下选取最小 \(k\)，映射为 `retry_times = k-1`（并受平台 0～3 重试上限约束）。

**样本量提示：** 对 \(n<5\)、\(5\le n<10\) 等给出 `warning` 与 `confidence_level`，响应中一并返回。

#### 工程实现位置（与代码一致）

- **核心计算**：`backend/api/flaky_analysis.py` 中 `compute_flaky_analysis_from_statuses`、`compute_flaky_analysis_for_case`。  
- **窗口大小**：`FLAKY_RECENT_WINDOW`（默认 30，合法范围实现中限制为 5～200）。  
- **视图封装**：`views_case.py` 中 `_compute_flaky_analysis` 调用上述函数；**`flaky_insight`**、**`run_smart`**、**`experiment_summary`** 共用同一分析逻辑。  
- **方法论输出**：分析结果含 **`methodology`**（假设、局限、有效权重等），便于论文表述可解释性。

#### 与朴素方法的对比

相比「仅看失败率」或「固定重试」，本文方法同时刻画保守上界、抖动与短期趋势，并暴露假设与局限。

### 5.2 自适应执行 `run_smart`

`POST /api/cases/{id}/run_smart/` 读取（可选）`target_success`、`max_attempts`，调用 Flaky 分析得到 `suggested_retries`，裁剪到平台允许范围后 **`run_test_case_task.delay(..., retry_times)`**，并 `bind_task_owner`。响应中的 `strategy` 携带完整分析字段（含 `methodology`）。

### 5.3 功能用例 → Locust（AST）

`locust_codegen.py` 使用 `ast` 将字面量编译为源码，降低字符串拼接导致的注入风险；压测异步任务与 `PerfRecord` 状态机详见实现与第 6 章。

### 5.4 三维质量评分卡

`quality_insight` 从设计/稳定性/可运维性综合评分并输出可操作建议（见 `views_case.py` 实现）。

### 5.5 「分析—决策—执行」闭环与实验接口

- **闭环**：历史 `TestRecord` → Flaky 分析 → `run_smart` → 新记录反哺分析。  
- **实验制表**：**`GET /api/cases/{id}/experiment_summary/`** 返回执行统计、完整 `flaky_analysis` 与 **固定 retry_times（0～3）与自适应行** 的对比，便于论文第 8 章制表。

---

## 第六章 关键功能模块实现（节选）

### 6.1 统一执行引擎 `TestEngine`

变量渲染（`{{var}}`/`[[var]]`、Faker）、HTTP 断言与 capture、UI 步骤、SQL 沙箱与 SSRF，见 `engine.py`。

### 6.2 用例版本与 OpenAPI 导入

版本快照与回滚；OpenAPI 导入在 `views_case` 中实现（需注意 URL 拉取时的 SSRF 与规格大小限制）。

### 6.3 套件共享变量

套件任务可在用例间传递变量（见 `tasks.py` 中套件执行逻辑）。

### 6.4 报告与压测前端

HTML/JSON 报告、Locust CSV 解析与 ECharts 展示。

---

## 第七章 安全性设计与实现

### 7.1 SSRF

`engine.validate_outbound_http_url`：限制 `http/https`；禁止 URL 内嵌用户名密码；禁止 `localhost`；若未指定 `allowed_hosts` 则对解析得到的 IP 判定私网/回环/链路本地等并拒绝；OpenAPI 等场景可对 `spec_url` 绑定环境 `base_url` 的 Host 白名单。

### 7.2 SQL 与 SQLite 路径

`run_db_query`：禁止多语句；危险关键字黑名单；查询/执行模式分离；SQLite 文件路径必须在项目 `BASE_DIR` 下经 `realpath` 校验，禁止 `..` 与绝对路径越界。

### 7.3 敏感字段

`crypto_utils`：敏感键 Fernet 加密、`enc:` 前缀；序列化脱敏；更新时合并掩码避免误覆盖密文。

### 7.4 鉴权、限流与越权

SimpleJWT；DRF 默认节流与 Scoped 登录/注册等；`task_status` 结合 `task_tracker` 校验任务归属；`apply_project_access_filter` 实现 owner ∪ 活跃成员的项目级隔离。

### 7.5 输入限额

对 `steps`、`variables` 等大 JSON 字段限制深度、键数量与字符串长度，降低 DoS 面。

---

## 第八章 实验与结果分析

> **重要：** 下列表格与百分比为**撰稿模板/示例**。定稿时须替换为你本人重复实验（固定环境、固定轮次）得到的统计；若尚未完成实验，请保留表头并标注「待测」。

### 8.1 实验环境

【填写：OS、Python、Django、Node、Chrome、被测站点等。】

### 8.2 数据集

`seed_demo_data.py` 可提供演示项目/用例规模作为基线描述。

### 8.3 功能正确性（示例 checklist）

注册登录、用例执行、套件执行、压测、`experiment_summary` 返回结构等，可结合 `pytest` 与手工验收表列出。

### 8.4 自适应 vs 固定重试（示例表，数据待填）

| 策略 | 成功率（示例） | 平均尝试次数（示例） | 备注 |
|------|----------------|----------------------|------|
| `run(retry_times=0)` | 【待测】 | 【待测】 | 基线 |
| `run(retry_times=3)` | 【待测】 | 【待测】 | 固定高重试 |
| `run_smart` | 【待测】 | 【待测】 | 本文策略 |

### 8.5 Flaky 分与波动（示例，数据待填）

可报告 Spearman/Pearson 等，**须附样本量与显著性说明**；不得虚构。

### 8.6 安全性抽检

列举 SSRF/SQL/越权/限流用例与预期拒绝结果（可与 README 安全章节一致）。

---

## 第九章 总结与展望

总结五条工作与闭环价值；展望步骤级根因、分布式压测、按需 ECharts、与外部 CI 对接等。

---

## 参考文献（请按学校格式核对页码与文献类型）

1. Luo Q, et al. An empirical analysis of flaky tests. FSE, 2014.  
2. Wilson E B. Probable inference, the law of succession, and statistical inference. JASA, 1927.  
3. Django / DRF / Celery / Vue / Locust / Selenium 官方文档。  
4. OWASP SSRF Prevention Cheat Sheet.  
【继续补充学院要求的篇数】

---

## 致谢

感谢指导教师与同学在选题、实现与论文撰写中的帮助。

---

## 附录 A 主要 API（与当前实现一致）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/cases/{id}/run/` | POST | 普通执行，`retry_times` |
| `/api/cases/{id}/run_smart/` | POST | 自适应执行 |
| `/api/cases/{id}/flaky_insight/` | GET | Flaky 分析 |
| `/api/cases/{id}/experiment_summary/` | GET | **实验对比摘要（制表）** |
| `/api/cases/{id}/quality_insight/` | GET | 质量评分 |
| `/api/cases/{id}/run_perf/` | POST | 压测 |
| `/api/task-status/{task_id}/` | GET | 任务状态 |

---

## 附录 B 关键算法伪代码（与实现一致）

```text
Algorithm FlakyAnalysis(case)
    cfg ← 读取 FLAKY_* 配置并归一化权重 w1,w2,w3
    statuses ← 最近 FLAKY_RECENT_WINDOW 条记录按时间正序映射为失败指示
    计算 w（Wilson 上界）、t（切换率）、e（EWMA）
    score ← round(100 * (w1*w + w2*t + w3*e))
    依 target_success、max_attempts 与投影 1-w^k 建议重试
    返回 { score, projections, suggested_retries, methodology, ... }
```

---

## 附录 C 代码规模参考（合并稿撰写时统计，以本地为准）

| 文件 | 参考行数 |
|------|----------|
| `backend/api/tests.py` | 约 1288 |
| `frontend/src/views/CasesView.vue` | 约 1117 |
| `backend/api/views_case.py` | 约 704 |
| `backend/api/engine.py` | 约 537 |
| `backend/api/serializers.py` | 约 352 |
| `backend/api/tasks.py` | 约 315 |
| `backend/api/flaky_analysis.py` | 约 254 |
| `frontend/src/views/SuitesView.vue` | 约 558 |
| `backend/api/locust_codegen.py` | 约 188 |

---

**全文完（合并修订稿）**
