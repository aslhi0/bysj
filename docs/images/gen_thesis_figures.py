# -*- coding: utf-8 -*-
"""生成毕设用图：单张 PNG，含 (a) 系统架构 (b) 核心 E-R 示意 (c) Flaky+run_smart 流程。运行：python gen_thesis_figures.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).with_name("thesis_figures.png")
ZH = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "DejaVu Sans"]


def set_zh_font():
    plt.rcParams["font.sans-serif"] = ZH + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def box(ax, x, y, w, h, t, fs=8, fc="#E8F4FC", ec="#1a5f7a"):
    p = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.2, edgecolor=ec, facecolor=fc, zorder=2,
    )
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs, wrap=True, zorder=3)
    return p


def arrow(ax, x1, y1, x2, y2, s=""):
    a = FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle="->", mutation_scale=12,
        linewidth=1.0, color="#333", zorder=1,
    )
    ax.add_patch(a)
    if s:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my + 0.08, s, ha="center", va="bottom", fontsize=6, color="#555")


def draw_architecture(ax, title):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left", y=0.98)
    # top: Vue
    box(ax, 2.0, 4.2, 6.0, 0.9, "表现层\nVue 3 + Element Plus", fs=8.5, fc="#E3F2FD", ec="#1565C0")
    # middle: API
    box(ax, 1.0, 2.6, 3.2, 0.9, "服务层\nDjango + DRF", fs=8, fc="#E8F5E9", ec="#2E7D32")
    box(ax, 5.8, 2.6, 3.2, 0.9, "分析 / 策略\nflaky_analysis", fs=7.5, fc="#FFF3E0", ec="#E65100")
    # celery
    box(ax, 2.0, 1.0, 6.0, 0.9, "执行层 Celery Worker\nengine + tasks", fs=8, fc="#F3E5F5", ec="#6A1B9A")
    # bottom: db
    box(ax, 2.0, 0.15, 6.0, 0.65, "数据层  SQLite/PostgreSQL + 媒体/报告/CSV", fs=7.5, fc="#ECEFF1", ec="#455A64")
    arrow(ax, 5, 4.2, 5, 3.5)
    arrow(ax, 2.6, 2.6, 2.5, 1.9, "")
    arrow(ax, 6.2, 2.6, 6.0, 1.9, "")
    arrow(ax, 3.0, 1.0, 3.2, 0.8, "")
    ax.text(5, 3.7, "REST / JSON", ha="center", fontsize=6.5, color="#444")
    ax.text(0.3, 3.0, "认证\nJWT", fontsize=6, color="#666")


def draw_er(ax, title):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left", y=0.98)
    # User
    box(ax, 0.2, 5.0, 1.3, 0.6, "User", fs=7, fc="#E1F5FE", ec="#0277BD")
    # Project
    box(ax, 2.0, 5.0, 1.6, 0.6, "Project", fs=7.5, fc="#C8E6C9", ec="#2E7D32")
    # members
    box(ax, 0.1, 3.2, 1.4, 0.55, "Project\nMember", fs=6.5, fc="#DCEDC8", ec="#558B2F")
    # children of project
    box(ax, 3.2, 5.0, 1.3, 0.55, "EnvConfig", fs=6.5, fc="#FFF9C4", ec="#F9A825")
    box(ax, 4.6, 5.0, 1.3, 0.55, "TestSuite", fs=6.5, fc="#FFF9C4", ec="#F9A825")
    box(ax, 3.0, 1.0, 1.4, 0.55, "TestCase", fs=7, fc="#FFE0B2", ec="#E65100")
    box(ax, 4.5, 1.0, 1.3, 0.55, "TestCase\nVersion", fs=6, fc="#FFCCBC", ec="#BF360C")
    # records
    box(ax, 6.2, 2.0, 1.4, 0.55, "TestRecord", fs=6.5, fc="#E1BEE7", ec="#6A1B9A")
    box(ax, 6.0, 0.3, 1.3, 0.5, "Perf\nRecord", fs=6, fc="#D1C4E9", ec="#4527A0")
    box(ax, 3.0, 3.0, 1.3, 0.5, "SuiteRun", fs=6.5, fc="#B2DFDB", ec="#00695C")
    arrow(ax, 1.0, 5.0, 1.4, 3.7)
    arrow(ax, 1.2, 5.3, 1.2, 3.2)
    arrow(ax, 2.8, 5.3, 2.0, 3.2)
    arrow(ax, 2.8, 3.0, 3.3, 1.6)
    arrow(ax, 2.0, 5.3, 2.0, 3.0)
    arrow(ax, 3.5, 5.0, 3.2, 1.5)
    arrow(ax, 4.1, 1.0, 4.2, 1.0)
    arrow(ax, 4.3, 1.55, 4.0, 1.55, "")
    ax.plot([2.8, 2.8], [5.0, 1.0], "k--", alpha=0.2)
    arrow(ax, 4.4, 1.3, 6.0, 2.0, "1:N")
    arrow(ax, 3.5, 1.0, 5.5, 0.55, "1:N")
    ax.text(0.1, 6.0, "owner", fontsize=5.5, color="#666", rotation=0)
    ax.text(1.0, 4.0, "N:N", fontsize=5.5, color="#666")
    ax.text(2.0, 2.0, "聚合于\nProject 域", fontsize=5.5, color="#666")


def draw_flow(ax, title):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left", y=0.98)
    y = 6.4
    dy = 0.95
    items = [
        "读取用例历史状态序列",
        "二值化 failed/error → 失败指示",
        "Wilson 失败率上界 p · 切换率 · EWMA",
        "加权融合得 flaky_score、risk_level",
        "投影 1−p^k，求 suggested_retries",
        "run_smart 注入 retry_times，Celery 入队",
        "Worker 多尝试 → 单条 TestRecord + attempt_logs",
        "新记录进入下一窗口分析",
    ]
    for i, t in enumerate(items):
        box(ax, 0.5, y - i * dy, 9, 0.7, t, fs=6.8, fc="#FAFAFA", ec="#37474F")
        if i < len(items) - 1:
            ax.annotate(
                "", xy=(5, y - (i + 1) * dy + 0.7), xytext=(5, y - i * dy),
                arrowprops=dict(arrowstyle="->", color="#1976D2", lw=1.2),
            )


def main():
    set_zh_font()
    fig = plt.figure(figsize=(8.5, 16), dpi=150)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 1.15, 1.4], hspace=0.28)
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[1, 0])
    ax2 = fig.add_subplot(gs[2, 0])
    draw_architecture(ax0, "(a)  总体四层架构")
    draw_er(ax1, "(b)  核心领域实体关系（示意）")
    draw_flow(ax2, "(c)  Flaky 分析至自适应执行与记录回流")
    fig.suptitle("自动化测试平台：架构 · 数据模型 · 分析执行流程", fontsize=11, fontweight="bold", y=0.995)
    fig.savefig(OUT, bbox_inches="tight", pad_inches=0.35, facecolor="white")
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
