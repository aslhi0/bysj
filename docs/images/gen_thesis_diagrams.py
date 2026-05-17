# -*- coding: utf-8 -*-
"""Generate thesis diagrams from project structure and archived experiment data.

Outputs are written to docs/images/thesis_diagrams/ so the thesis references a
single, reproducible figure directory.
"""
from __future__ import annotations

from pathlib import Path
import math
import sys
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path as MplPath
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, PathPatch
from matplotlib import font_manager
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "thesis_diagrams"
CSV_PATH = ROOT / "docs" / "artifacts" / "thesis_runs_20260424_enriched.csv"
sys.path.insert(0, str(ROOT / "scripts"))
from figure_fonts import configure_matplotlib_chinese  # noqa: E402


configure_matplotlib_chinese(plt, font_manager)
plt.rcParams["figure.facecolor"] = "white"

PALETTE = {
    "blue": "#2F6B9A",
    "blue_light": "#DDEDF8",
    "green": "#2D7A5F",
    "green_light": "#DFF2EA",
    "orange": "#B8651B",
    "orange_light": "#FDE9D4",
    "purple": "#6C5A9A",
    "purple_light": "#ECE7F6",
    "red": "#A33C3C",
    "red_light": "#F6DDDD",
    "gray": "#4A5568",
    "gray_light": "#F4F6F8",
    "line": "#334155",
}


def _wrap(text: str, width: int = 12) -> str:
    parts: list[str] = []
    for line in str(text).split("\n"):
        if not line:
            parts.append("")
        else:
            parts.extend(textwrap.wrap(line, width=width, break_long_words=False, replace_whitespace=False))
    return "\n".join(parts)


def _setup_ax(ax, xlim=(0, 10), ylim=(0, 7)):
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")


def _box(ax, x, y, w, h, text, *, fc, ec, fs=9, lw=1.2, radius=0.08, weight="normal", z=2):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        zorder=z,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, _wrap(text, 18), ha="center", va="center", fontsize=fs, fontweight=weight, color="#1F2937", zorder=z + 1)
    return box


def _table_box(ax, x, y, w, h, title, rows, *, fc, ec, title_fc=None, fs=7.2):
    _box(ax, x, y, w, h, "", fc=fc, ec=ec, fs=fs, radius=0.04)
    header_h = 0.33
    ax.add_patch(patches.Rectangle((x, y + h - header_h), w, header_h, facecolor=title_fc or ec, edgecolor=ec, linewidth=1.0, zorder=3))
    ax.text(x + w / 2, y + h - header_h / 2, title, ha="center", va="center", fontsize=fs + 0.4, color="white", fontweight="bold", zorder=4)
    row_text = "\n".join(rows)
    ax.text(x + 0.12, y + h - header_h - 0.13, row_text, ha="left", va="top", fontsize=fs, color="#1F2937", linespacing=1.18, zorder=4)


def _arrow(ax, start, end, text="", *, color=None, lw=1.1, style="->", connectionstyle="arc3,rad=0.0", fs=7, ls="solid"):
    a = FancyArrowPatch(
        start,
        end,
        arrowstyle=style,
        mutation_scale=10,
        linewidth=lw,
        color=color or PALETTE["line"],
        linestyle=ls,
        connectionstyle=connectionstyle,
        zorder=1,
    )
    ax.add_patch(a)
    if text:
        mx = (start[0] + end[0]) / 2
        my = (start[1] + end[1]) / 2
        ax.text(mx, my + 0.12, text, ha="center", va="bottom", fontsize=fs, color=color or PALETTE["line"])


def _actor(ax, x, y, label):
    ax.add_patch(patches.Circle((x, y + 0.55), 0.16, fill=False, ec=PALETTE["line"], lw=1.2))
    ax.plot([x, x], [y + 0.39, y - 0.05], color=PALETTE["line"], lw=1.2)
    ax.plot([x - 0.28, x + 0.28], [y + 0.22, y + 0.22], color=PALETTE["line"], lw=1.2)
    ax.plot([x, x - 0.24], [y - 0.05, y - 0.42], color=PALETTE["line"], lw=1.2)
    ax.plot([x, x + 0.24], [y - 0.05, y - 0.42], color=PALETTE["line"], lw=1.2)
    ax.text(x, y - 0.66, label, ha="center", va="top", fontsize=8.5, color="#111827")


def _ellipse(ax, x, y, w, h, text, *, fc="#FFFFFF", ec=None, fs=8):
    e = patches.Ellipse((x, y), w, h, facecolor=fc, edgecolor=ec or PALETTE["blue"], linewidth=1.1, zorder=2)
    ax.add_patch(e)
    ax.text(x, y, _wrap(text, 12), ha="center", va="center", fontsize=fs, color="#111827", zorder=3)
    return e


def draw_use_case():
    fig, ax = plt.subplots(figsize=(10.5, 7.2), dpi=220)
    _setup_ax(ax, (0, 12), (0, 8))
    ax.set_title("图3-1 系统 UML 用例图", loc="left", fontsize=13, fontweight="bold")
    _actor(ax, 0.9, 5.6, "管理员")
    _actor(ax, 0.9, 2.0, "测试人员")
    _actor(ax, 11.1, 4.0, "外部被测系统")

    boundary = FancyBboxPatch((2.0, 0.7), 8.0, 6.6, boxstyle="round,pad=0.03,rounding_size=0.08", fc="#FBFCFD", ec="#94A3B8", lw=1.2)
    ax.add_patch(boundary)
    ax.text(6.0, 7.08, "自动化测试平台", ha="center", va="center", fontsize=11, fontweight="bold", color="#334155")

    cases = [
        (3.2, 6.25, "登录/刷新令牌"),
        (5.1, 6.25, "项目与成员管理"),
        (7.2, 6.25, "环境变量配置"),
        (3.2, 4.95, "用例创建/编辑"),
        (5.1, 4.95, "版本快照/回滚"),
        (7.2, 4.95, "OpenAPI 导入"),
        (3.2, 3.65, "套件编排/运行"),
        (5.1, 3.65, "run_smart 自适应执行"),
        (7.2, 3.65, "HTTP/UI/SQL 执行"),
        (3.2, 2.35, "报告与历史查询"),
        (5.1, 2.35, "Flaky 分析与策略对比"),
        (7.2, 2.35, "性能测试与 CSV 报告"),
    ]
    for i, (x, y, t) in enumerate(cases):
        _ellipse(ax, x, y, 1.55, 0.65, t, fc=PALETTE["blue_light"] if i % 3 == 0 else "#FFFFFF", fs=7.7)

    admin_targets = [(5.1, 6.25), (7.2, 6.25), (7.2, 4.95)]
    tester_targets = [(3.2, 4.95), (3.2, 3.65), (5.1, 3.65), (3.2, 2.35), (5.1, 2.35), (7.2, 2.35)]
    for target in admin_targets:
        _arrow(ax, (1.25, 6.05), (target[0] - 0.85, target[1]), lw=0.8, style="-", color="#64748B")
    for target in tester_targets:
        _arrow(ax, (1.25, 2.45), (target[0] - 0.85, target[1]), lw=0.8, style="-", color="#64748B")
    for target in [(7.2, 3.65), (7.2, 2.35)]:
        _arrow(ax, (target[0] + 0.85, target[1]), (10.75, 4.0), lw=0.8, style="-", color="#64748B")

    _arrow(ax, (5.8, 3.65), (6.35, 3.65), "<<include>>", color="#7C3AED", fs=6.5, lw=0.9, ls="dashed")
    _arrow(ax, (5.1, 3.3), (5.1, 2.7), "<<include>>", color="#7C3AED", fs=6.5, lw=0.9, ls="dashed")
    _arrow(ax, (3.85, 4.95), (4.35, 4.95), "<<extend>>", color="#B45309", fs=6.5, lw=0.9, ls="dashed")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig3-1_use_case.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_architecture():
    fig, ax = plt.subplots(figsize=(11.2, 7.4), dpi=220)
    _setup_ax(ax, (0, 12), (0, 8))
    ax.set_title("图4-1 系统总体架构图", loc="left", fontsize=13, fontweight="bold")

    layers = [
        (0.5, 6.55, 11.0, 0.95, "表现层", "#E8F2FF"),
        (0.5, 4.85, 11.0, 1.25, "服务层", "#EAF7EF"),
        (0.5, 3.05, 11.0, 1.25, "执行层", "#FFF3E4"),
        (0.5, 1.0, 11.0, 1.35, "数据与产物层", "#F5F6F8"),
    ]
    for x, y, w, h, name, fc in layers:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.05", fc=fc, ec="#CBD5E1", lw=1.0, zorder=0))
        ax.text(x + 0.25, y + h - 0.18, name, ha="left", va="top", fontsize=9.5, fontweight="bold", color="#334155")

    _box(ax, 1.0, 6.78, 2.2, 0.45, "Vue 3 工作台\n用例/套件/报告/性能", fc="#FFFFFF", ec=PALETTE["blue"], fs=7.8)
    _box(ax, 3.65, 6.78, 2.1, 0.45, "Element Plus\n表单与表格组件", fc="#FFFFFF", ec=PALETTE["blue"], fs=7.8)
    _box(ax, 6.2, 6.78, 2.1, 0.45, "api.js\nJWT 注入与刷新", fc="#FFFFFF", ec=PALETTE["blue"], fs=7.8)
    _box(ax, 8.75, 6.78, 2.2, 0.45, "ECharts\n报告可视化", fc="#FFFFFF", ec=PALETTE["blue"], fs=7.8)

    _box(ax, 0.95, 5.25, 1.8, 0.55, "Django/DRF\nViewSet + Serializer", fc="#FFFFFF", ec=PALETTE["green"], fs=7.6)
    _box(ax, 3.05, 5.25, 1.8, 0.55, "认证与权限\nSimpleJWT + 项目域过滤", fc="#FFFFFF", ec=PALETTE["green"], fs=7.4)
    _box(ax, 5.15, 5.25, 1.8, 0.55, "Flaky 分析\nWilson/EWMA/切换率", fc="#FFFFFF", ec=PALETTE["green"], fs=7.4)
    _box(ax, 7.25, 5.25, 1.8, 0.55, "接口编排\nrun/run_smart/suite/perf", fc="#FFFFFF", ec=PALETTE["green"], fs=7.4)
    _box(ax, 9.35, 5.25, 1.65, 0.55, "限流/SSRF/SQL\n安全边界", fc="#FFFFFF", ec=PALETTE["green"], fs=7.0)

    _box(ax, 1.0, 3.55, 2.0, 0.58, "Celery Worker\n异步用例/套件/压测", fc="#FFFFFF", ec=PALETTE["orange"], fs=7.4)
    _box(ax, 3.35, 3.55, 2.0, 0.58, "TestEngine\nHTTP + UI + SQL", fc="#FFFFFF", ec=PALETTE["orange"], fs=7.4)
    _box(ax, 5.7, 3.55, 2.0, 0.58, "Selenium\nChrome/Edge 自动选择", fc="#FFFFFF", ec=PALETTE["orange"], fs=7.2)
    _box(ax, 8.05, 3.55, 2.0, 0.58, "Locust 脚本\nAST 生成与执行", fc="#FFFFFF", ec=PALETTE["orange"], fs=7.2)

    _box(ax, 1.0, 1.55, 2.0, 0.55, "关系数据库\nProject/Case/Record", fc="#FFFFFF", ec=PALETTE["gray"], fs=7.4)
    _box(ax, 3.45, 1.55, 2.0, 0.55, "Media\n失败截图/附件", fc="#FFFFFF", ec=PALETTE["gray"], fs=7.4)
    _box(ax, 5.9, 1.55, 2.0, 0.55, "CSV/报告\n性能与套件结果", fc="#FFFFFF", ec=PALETTE["gray"], fs=7.4)
    _box(ax, 8.35, 1.55, 2.0, 0.55, "缓存/队列\nRedis/本地 eager", fc="#FFFFFF", ec=PALETTE["gray"], fs=7.4)

    _arrow(ax, (6.2, 6.55), (6.2, 6.1), "REST/JSON", color=PALETTE["blue"])
    _arrow(ax, (6.2, 4.85), (6.2, 4.3), "task_id + 轮询", color=PALETTE["green"])
    _arrow(ax, (4.4, 3.55), (4.4, 2.35), "执行结果", color=PALETTE["orange"])
    _arrow(ax, (8.9, 3.55), (6.9, 2.1), "stats.csv", color=PALETTE["orange"])
    _arrow(ax, (6.7, 3.55), (10.9, 3.0), "真实浏览器", color=PALETTE["orange"])
    _box(ax, 10.25, 2.55, 1.2, 0.75, "外部 Web\n被测系统", fc="#FFFFFF", ec=PALETTE["red"], fs=7.2)
    ax.text(0.7, 0.45, "代码落点：frontend/src/views、backend/api/views_*.py、backend/api/engine.py、backend/api/tasks.py、backend/api/flaky_analysis.py", fontsize=8, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4-1_system_architecture.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_domain_er():
    fig, ax = plt.subplots(figsize=(10.5, 7.2), dpi=220)
    _setup_ax(ax, (0, 12), (0, 8))
    ax.set_title("图4-2 核心领域实体关系示意图", loc="left", fontsize=13, fontweight="bold")
    nodes = {
        "User": (0.9, 6.2, 1.5, 0.65, "用户\nUser"),
        "ProjectMember": (0.9, 4.4, 1.7, 0.65, "项目成员\nProjectMember"),
        "Project": (3.4, 5.2, 1.8, 0.8, "项目\nProject"),
        "EnvConfig": (6.2, 6.4, 1.8, 0.65, "环境配置\nEnvConfig"),
        "TestCase": (6.2, 5.15, 1.8, 0.65, "测试用例\nTestCase"),
        "TestSuite": (6.2, 3.9, 1.8, 0.65, "测试套件\nTestSuite"),
        "TestCaseVersion": (9.3, 6.0, 2.0, 0.65, "用例版本\nTestCaseVersion"),
        "TestRecord": (9.3, 4.9, 2.0, 0.65, "执行记录\nTestRecord"),
        "PerfRecord": (9.3, 3.8, 2.0, 0.65, "性能记录\nPerfRecord"),
        "SuiteRun": (9.3, 2.7, 2.0, 0.65, "套件运行\nSuiteRun"),
        "PeriodicTaskOwner": (3.4, 2.4, 2.0, 0.65, "定时任务归属\nPeriodicTaskOwner"),
    }
    for i, (key, (x, y, w, h, label)) in enumerate(nodes.items()):
        fc = [PALETTE["blue_light"], PALETTE["green_light"], PALETTE["orange_light"], PALETTE["purple_light"]][i % 4]
        _box(ax, x, y, w, h, label, fc=fc, ec=PALETTE["line"], fs=7.6, radius=0.05)
    rels = [
        ("User", "Project", "owner 1:N"),
        ("User", "ProjectMember", "1:N"),
        ("Project", "ProjectMember", "1:N"),
        ("Project", "EnvConfig", "1:N"),
        ("Project", "TestCase", "1:N"),
        ("Project", "TestSuite", "1:N"),
        ("TestCase", "TestCaseVersion", "1:N"),
        ("TestCase", "TestRecord", "1:N"),
        ("TestCase", "PerfRecord", "1:N"),
        ("TestSuite", "SuiteRun", "1:N"),
        ("TestSuite", "TestCase", "ordered_case_ids\nJSON 引用", "dashed"),
        ("User", "PeriodicTaskOwner", "1:N"),
    ]
    centers = {k: (v[0] + v[2] / 2, v[1] + v[3] / 2) for k, v in nodes.items()}
    for rel in rels:
        src, dst, label = rel[:3]
        ls = rel[3] if len(rel) > 3 else "solid"
        _arrow(ax, centers[src], centers[dst], label, lw=0.9, fs=6.5, color="#475569", ls=ls, connectionstyle="arc3,rad=0.08")
    ax.text(0.7, 0.65, "说明：该图强调项目域隔离与核心业务聚合关系；字段级数据库结构见图4-3。", fontsize=8.2, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4-2_domain_er_overview.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_database_er():
    fig, ax = plt.subplots(figsize=(12.5, 8.5), dpi=220)
    _setup_ax(ax, (0, 14), (0, 9))
    ax.set_title("图4-3 系统核心数据库 E-R 图", loc="left", fontsize=13, fontweight="bold")
    tables = {
        "auth_user": (0.55, 7.0, 2.0, 1.05, ["id PK", "username", "is_staff"]),
        "api_project": (3.45, 7.0, 2.35, 1.25, ["id PK", "owner_id FK", "name", "webhook_url", "created_at"]),
        "api_projectmember": (0.55, 5.05, 2.45, 1.25, ["id PK", "project_id FK", "user_id FK", "is_active", "uniq(project,user)"]),
        "api_envconfig": (6.8, 7.0, 2.35, 1.25, ["id PK", "project_id FK", "name", "base_url", "db_config JSON", "variables JSON"]),
        "api_testcase": (3.45, 4.05, 2.65, 1.85, ["id PK", "project_id FK", "title", "steps JSON", "variables JSON", "setup/teardown_sql", "status"]),
        "api_testsuite": (6.8, 4.15, 2.55, 1.5, ["id PK", "project_id FK", "name", "variables JSON", "ordered_case_ids JSON"]),
        "api_testcaseversion": (0.55, 2.0, 2.55, 1.35, ["id PK", "case_id FK", "version", "snapshot JSON", "created_by_id FK"]),
        "api_testrecord": (3.45, 1.65, 2.65, 1.75, ["id PK", "case_id FK", "status", "step_results JSON", "attempts", "attempt_logs JSON", "screenshot"]),
        "api_perfrecord": (6.8, 1.85, 2.55, 1.35, ["id PK", "case_id FK", "users", "spawn_rate", "duration", "status", "csv_prefix"]),
        "api_suiterun": (10.2, 4.25, 2.45, 1.25, ["id PK", "suite_id FK", "summary JSON", "stop_on_failure", "results JSON"]),
    }
    for i, (name, spec) in enumerate(tables.items()):
        x, y, w, h, rows = spec
        title_color = [PALETTE["blue"], PALETTE["green"], PALETTE["orange"], PALETTE["purple"], PALETTE["gray"]][i % 5]
        _table_box(ax, x, y, w, h, name, rows, fc="#FFFFFF", ec=title_color, title_fc=title_color, fs=6.5)

    def center(name):
        x, y, w, h, _ = tables[name]
        return (x + w / 2, y + h / 2)

    relationships = [
        ("auth_user", "api_project", "owner_id", "solid"),
        ("auth_user", "api_projectmember", "user_id", "solid"),
        ("api_project", "api_projectmember", "project_id", "solid"),
        ("api_project", "api_envconfig", "project_id", "solid"),
        ("api_project", "api_testcase", "project_id", "solid"),
        ("api_project", "api_testsuite", "project_id", "solid"),
        ("api_testcase", "api_testcaseversion", "case_id", "solid"),
        ("api_testcase", "api_testrecord", "case_id", "solid"),
        ("api_testcase", "api_perfrecord", "case_id", "solid"),
        ("api_testsuite", "api_suiterun", "suite_id", "solid"),
        ("api_testsuite", "api_testcase", "", "dashed"),
    ]
    for src, dst, label, ls in relationships:
        _arrow(ax, center(src), center(dst), label, lw=0.75, fs=5.8, color="#475569", ls=ls, connectionstyle="arc3,rad=0.08")
    ax.text(0.55, 0.35, "实线表示 Django 外键关系；虚线表示 TestSuite.ordered_case_ids 中的有序 ID 引用。图中保留论文相关核心表与字段，定时任务归属等辅助表在文字中说明。", fontsize=8, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4-3_database_er.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_flaky_flow():
    fig, ax = plt.subplots(figsize=(8.5, 9.5), dpi=220)
    _setup_ax(ax, (0, 10), (0, 12))
    ax.set_title("图5-1 Flaky 分析与策略生成流程图", loc="left", fontsize=13, fontweight="bold")
    steps = [
        ("读取 TestRecord 历史窗口\nstatus / elapsed / attempts", PALETTE["blue_light"], PALETTE["blue"]),
        ("状态二值化\nsuccess=0, failed/error=1", "#FFFFFF", PALETTE["blue"]),
        ("计算基础统计\n失败率、样本量、切换率", PALETTE["green_light"], PALETTE["green"]),
        ("Wilson 失败率上界\n控制小样本乐观偏差", PALETTE["green_light"], PALETTE["green"]),
        ("EWMA 近期失败趋势\n近期样本权重更高", PALETTE["orange_light"], PALETTE["orange"]),
        ("权重归一化融合\nflaky_score + risk_level", PALETTE["purple_light"], PALETTE["purple"]),
        ("至少一次成功投影\n1 - p^k, k=1..max_attempts", "#FFFFFF", PALETTE["purple"]),
        ("生成策略建议\nsuggested_retries + methodology", PALETTE["red_light"], PALETTE["red"]),
        ("供 run_smart / experiment_summary 消费\n并进入下一轮执行闭环", PALETTE["gray_light"], PALETTE["gray"]),
    ]
    x, w, h = 1.2, 7.6, 0.78
    y = 10.5
    for i, (text, fc, ec) in enumerate(steps):
        _box(ax, x, y - i * 1.12, w, h, text, fc=fc, ec=ec, fs=8.0, radius=0.06)
        if i < len(steps) - 1:
            _arrow(ax, (5.0, y - i * 1.12), (5.0, y - (i + 1) * 1.12 + h), lw=1.1, color="#475569")
    ax.text(1.2, 0.55, "边界说明：投影是工程启发式，不等同于对真实流水线成功率的严格概率证明。", fontsize=8.2, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig5-1_flaky_analysis_flow.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_sequence():
    fig, ax = plt.subplots(figsize=(11.5, 6.4), dpi=220)
    _setup_ax(ax, (0, 12), (0, 7))
    ax.set_title("图5-2 run_smart 与异步执行时序图", loc="left", fontsize=13, fontweight="bold")
    actors = [
        ("前端 Vue", 1.0),
        ("CaseViewSet", 2.9),
        ("Flaky 分析核", 4.8),
        ("Celery/队列", 6.7),
        ("TestEngine", 8.6),
        ("数据库/Media", 10.5),
    ]
    top, bottom = 6.1, 0.8
    for label, x in actors:
        _box(ax, x - 0.55, top, 1.1, 0.35, label, fc=PALETTE["blue_light"], ec=PALETTE["blue"], fs=7.0, radius=0.03)
        ax.plot([x, x], [bottom, top], color="#94A3B8", linestyle="--", linewidth=0.9)
    messages = [
        (1.0, 2.9, 5.55, "POST /cases/{id}/run_smart", "solid"),
        (2.9, 4.8, 5.05, "读取历史并计算策略", "solid"),
        (4.8, 2.9, 4.55, "suggested_retries + methodology", "dashed"),
        (2.9, 6.7, 4.05, "delay(case_id, env_id, retry_times)", "solid"),
        (6.7, 2.9, 3.55, "task_id", "dashed"),
        (1.0, 2.9, 3.05, "轮询 /api/task-status/{task_id}", "solid"),
        (6.7, 8.6, 2.55, "执行 HTTP/UI/SQL 步骤", "solid"),
        (8.6, 8.6, 2.0, "失败时截图\n成功即提前终止", "loop"),
        (8.6, 10.5, 1.45, "写入 TestRecord / attempt_logs / screenshot", "solid"),
        (2.9, 1.0, 0.95, "返回状态与 record 摘要", "dashed"),
    ]
    for x1, x2, y, text, kind in messages:
        if kind == "loop":
            ax.add_patch(patches.FancyArrowPatch((x1 + 0.1, y + 0.15), (x1 + 0.1, y - 0.35), connectionstyle="arc3,rad=-1.0", arrowstyle="->", mutation_scale=10, lw=0.9, color="#475569"))
            ax.text(x1 + 0.55, y - 0.1, text, fontsize=6.8, va="center", color="#334155")
            continue
        _arrow(ax, (x1, y), (x2, y), text, color="#334155", fs=6.6, lw=0.9, ls="dashed" if kind == "dashed" else "solid")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig5-2_run_smart_sequence.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _load_experiment():
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    df["strategy"] = df.apply(lambda r: "run_smart" if r["mode"] == "run_smart" else f"r={int(float(r['retry_times']))}", axis=1)
    order = ["r=0", "r=2", "run_smart"]
    df["strategy"] = pd.Categorical(df["strategy"], categories=order, ordered=True)
    return df


def _summary(df):
    g = df.groupby(["case_label", "strategy"], observed=True)
    out = g.agg(
        n=("success", "count"),
        success_rate=("success", "mean"),
        elapsed_mean=("elapsed_sec", "mean"),
        elapsed_std=("elapsed_sec", "std"),
        attempts_mean=("attempts_made", "mean"),
        flaky_score=("flaky_score", "mean"),
    ).reset_index()
    out["success_se"] = np.sqrt(out["success_rate"] * (1 - out["success_rate"]) / out["n"]).fillna(0)
    case_order = ["稳定型-HTTP", "波动型-UI", "高风险-HTTP"]
    out["case_label"] = pd.Categorical(out["case_label"], categories=case_order, ordered=True)
    out = out.sort_values(["case_label", "strategy"]).reset_index(drop=True)
    return out


def draw_success_rates():
    df = _summary(_load_experiment())
    cases = [str(x) for x in df["case_label"].drop_duplicates()]
    strategies = ["r=0", "r=2", "run_smart"]
    colors = {"r=0": "#7A869A", "r=2": "#4E79A7", "run_smart": "#59A14F"}
    fig, ax = plt.subplots(figsize=(10.8, 5.8), dpi=220)
    x = np.arange(len(cases))
    width = 0.24
    for i, s in enumerate(strategies):
        vals, errs, labels = [], [], []
        for c in cases:
            row = df[(df["case_label"] == c) & (df["strategy"].astype(str) == s)]
            if row.empty:
                vals.append(np.nan)
                errs.append(0)
                labels.append("")
            else:
                vals.append(float(row["success_rate"].iloc[0]))
                errs.append(float(row["success_se"].iloc[0]))
                labels.append(f"N={int(row['n'].iloc[0])}")
        offset = (i - 1) * width
        bars = ax.bar(x + offset, vals, width, yerr=errs, capsize=4, label=s, color=colors[s], edgecolor="#334155", linewidth=0.6)
        for bar, lab in zip(bars, labels):
            if not lab:
                continue
            ax.text(bar.get_x() + bar.get_width() / 2, 0.965, f"1.000\n{lab}", ha="center", va="top", fontsize=7.5, color="white", fontweight="bold")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("观测成功率 p_hat")
    ax.set_xticks(x)
    ax.set_xticklabels(cases)
    ax.set_title("图6-1 各用例与策略的观测成功率对比")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(title="策略", loc="lower right")
    ax.text(0.01, 0.06, "说明：本批归档样本均为成功，图中不据此外推“自适应策略显著提升成功率”。", transform=ax.transAxes, fontsize=8.2, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig6-1_success_rates.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_elapsed():
    df = _summary(_load_experiment())
    cases = [str(x) for x in df["case_label"].drop_duplicates()]
    strategies = ["r=0", "r=2", "run_smart"]
    colors = {"r=0": "#7A869A", "r=2": "#4E79A7", "run_smart": "#59A14F"}
    fig, ax = plt.subplots(figsize=(10.8, 5.8), dpi=220)
    x = np.arange(len(cases))
    width = 0.24
    for i, s in enumerate(strategies):
        vals, errs, labels = [], [], []
        for c in cases:
            row = df[(df["case_label"] == c) & (df["strategy"].astype(str) == s)]
            if row.empty:
                vals.append(np.nan)
                errs.append(0)
                labels.append("")
            else:
                vals.append(float(row["elapsed_mean"].iloc[0]))
                errs.append(float(row["elapsed_std"].fillna(0).iloc[0]))
                labels.append(f"{float(row['elapsed_mean'].iloc[0]):.3f}s")
        offset = (i - 1) * width
        bars = ax.bar(x + offset, vals, width, yerr=errs, capsize=4, label=s, color=colors[s], edgecolor="#334155", linewidth=0.6)
        for bar, lab in zip(bars, labels):
            if not lab or math.isnan(bar.get_height()):
                continue
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05, lab, ha="center", va="bottom", fontsize=7.2, rotation=0)
    ax.set_ylabel("平均 wall-clock 耗时（秒，误差线为标准差）")
    ax.set_xticks(x)
    ax.set_xticklabels(cases)
    ax.set_title("图6-2 各用例与策略的平均耗时对比")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(title="策略", loc="upper right")
    ax.text(0.01, 0.92, "说明：UI 用例耗时主要来自浏览器启动、页面渲染与显式等待。", transform=ax.transAxes, fontsize=8.2, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig6-2_mean_elapsed.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_flaky_gain():
    df = _summary(_load_experiment())
    strategies = ["r=2", "run_smart"]
    colors = {"r=2": "#4E79A7", "run_smart": "#59A14F"}
    markers = {"r=2": "s", "run_smart": "o"}
    fig, ax = plt.subplots(figsize=(9.8, 5.6), dpi=220)
    jitter_map = {"稳定型-HTTP": -0.06, "波动型-UI": 0.0, "高风险-HTTP": 0.06}
    for case in df["case_label"].drop_duplicates():
        base = df[(df["case_label"] == case) & (df["strategy"].astype(str) == "r=0")]
        if base.empty:
            continue
        base_rate = float(base["success_rate"].iloc[0])
        fs = float(base["flaky_score"].iloc[0])
        for i, s in enumerate(strategies):
            row = df[(df["case_label"] == case) & (df["strategy"].astype(str) == s)]
            if row.empty:
                continue
            delta = float(row["success_rate"].iloc[0]) - base_rate
            x = fs + jitter_map.get(case, 0) + (i - 0.5) * 0.018
            ax.scatter([x], [delta], s=95, marker=markers[s], color=colors[s], edgecolor="#1F2937", linewidth=0.7, label=s if case == df["case_label"].iloc[0] else None)
            ax.annotate(f"{case}\n{s}", (x, delta), textcoords="offset points", xytext=(8, 8 + i * 10), fontsize=7.2, arrowprops={"arrowstyle": "-", "color": "#94A3B8", "lw": 0.6})
    ax.axhline(0, color="#64748B", linewidth=0.9)
    ax.set_xlim(5.82, 6.18)
    ax.set_ylim(-0.08, 0.12)
    ax.set_xlabel("flaky_score（本批三个归档用例均为 low=6）")
    ax.set_ylabel("相对同用例 r=0 的观测成功率差")
    ax.set_title("图6-3 Flaky 分数与策略收益关系")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(title="策略", loc="upper right")
    ax.text(0.02, 0.08, "本批所有观测成功率均为 1.000，因此收益点落在 0；图用于说明统计口径，而非证明显著提升。", transform=ax.transAxes, fontsize=8.1, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig6-3_flaky_gain_combined.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    draw_use_case()
    draw_architecture()
    draw_domain_er()
    draw_database_er()
    draw_flaky_flow()
    draw_sequence()
    draw_success_rates()
    draw_elapsed()
    draw_flaky_gain()
    for p in sorted(OUT_DIR.glob("*.png")):
        print(f"Wrote {p}")


if __name__ == "__main__":
    main()
