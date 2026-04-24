# -*- coding: utf-8 -*-
"""
生成第 5 章图 5-1、图 5-2 的静态 PNG，供 Word/PDF 插入（不依赖 Mermaid 渲染器）。

运行（在仓库任意目录，建议）：
  cd docs/images && python gen_thesis_ch5_flow_figures.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT_DIR = Path(__file__).parent
ZH = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "DejaVu Sans"]


def set_zh_font():
    plt.rcParams["font.sans-serif"] = ZH + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def box(ax, x, y, w, h, t, fs=7, fc="#E3F2FD", ec="#1565C0"):
    p = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.02", linewidth=1.0, edgecolor=ec, facecolor=fc, zorder=2
    )
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs, zorder=3)


def arrow(ax, x1, y1, x2, y2, text=""):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="->", mutation_scale=10, linewidth=0.9, color="#333", zorder=1)
    ax.add_patch(a)
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, ha="center", va="bottom", fontsize=5.5, color="#555")


def draw_fig5_1(ax):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9.2)
    ax.axis("off")
    ax.set_title("图 5-1  Flaky 分析主路径（与附录 B 算法一致，示意）", fontsize=10, fontweight="bold", loc="left", pad=6)
    y, dy = 7.5, 0.82
    nodes = [
        "历史状态时间序列",
        "0/1 失败指示序列",
        "失败率估计 · EWMA · 相邻切换率",
        "Wilson 失败率上界 p",
        "权重归一化融合",
        "flaky_score / risk_level",
        "1-p^k 投影 与 target_success",
        "suggested_retries",
        "methodology 输出  →  供 run_smart 消费",
    ]
    w, h, x0 = 8.0, 0.62, 1.0
    for i, t in enumerate(nodes):
        box(ax, x0, y - i * dy, w, h, t, fs=6.5 if i < 8 else 6.0, fc="#E8F4FC" if i % 2 == 0 else "#FFF8E1", ec="#0D47A1")
        if i < len(nodes) - 1:
            ax.annotate(
                "", xy=(x0 + w / 2, y - (i + 1) * dy + h), xytext=(x0 + w / 2, y - i * dy), arrowprops=dict(arrowstyle="->", color="#1976D2", lw=1.0)
            )


def draw_fig5_2(ax):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.5)
    ax.axis("off")
    ax.set_title("图 5-2  run_smart 与 Celery 执行时序（示意）", fontsize=10, fontweight="bold", loc="left", pad=6)
    names = ["客户端", "ViewSet", "Flaky\n分析", "Celery", "run_test_case_task"]
    xs = [1.0, 2.8, 4.6, 6.4, 8.2]
    y0, y1 = 0.6, 5.0
    for x, n in zip(xs, names):
        ax.plot([x, x], [y0, y1], "k-", lw=0.8, alpha=0.45)
        ax.text(x, y1 + 0.2, n, ha="center", va="bottom", fontsize=6.5)
    # messages (y from top to bottom)
    rows = [
        (0, 1, "POST run_smart", 4.5, False),
        (1, 2, "Flaky 分析", 4.0, False),
        (2, 1, "strategy", 3.5, True),
        (1, 3, "delay(…)", 3.0, False),
        (3, 0, "task_id", 2.5, True),
        (0, 1, "轮询 task_status", 2.0, False),
        (3, 4, "执行与聚合 attempt_logs", 1.3, False),
        (4, 0, "完成 + record 摘要", 0.7, True),
    ]
    for r in rows:
        i0, i1, msg, yl, dash = r
        x0, x1 = xs[i0], xs[i1]
        ax.annotate(
            "",
            xy=(x1, yl),
            xytext=(x0, yl),
            arrowprops=dict(arrowstyle="->", color="#333" if not dash else "#666", linestyle="dashed" if dash else "solid", linewidth=0.9),
        )
        ax.text((x0 + x1) / 2, yl + 0.1, msg, ha="center", va="bottom", fontsize=5.5, color="#333")


def main():
    set_zh_font()
    p1 = OUT_DIR / "fig5-1_flaky_analysis_flow.png"
    p2 = OUT_DIR / "fig5-2_run_smart_sequence.png"
    fig1, ax1 = plt.subplots(1, 1, figsize=(6.2, 7.2), dpi=150)
    draw_fig5_1(ax1)
    fig1.savefig(p1, bbox_inches="tight", pad_inches=0.25, facecolor="white")
    plt.close(fig1)
    print("Wrote", p1)
    fig2, ax2 = plt.subplots(1, 1, figsize=(7.5, 3.4), dpi=150)
    draw_fig5_2(ax2)
    fig2.savefig(p2, bbox_inches="tight", pad_inches=0.2, facecolor="white")
    plt.close(fig2)
    print("Wrote", p2)


if __name__ == "__main__":
    main()
