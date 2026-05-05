#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据 thesis_experiment.py 导出的 CSV 或手工汇总表绘制第 6 章图 6-1～6-3。

依赖：pip install matplotlib pandas

示例：
  python scripts/enrich_thesis_csv_flaky_score.py runs.csv out.csv --json-dir docs/artifacts
  python scripts/plot_thesis_ch6_figures.py --csv out.csv --out-dir docs/images/ --flaky-json-dir docs/artifacts --fig6-3-combined-also
  # 无 --case-label 时：fig6-1/6-2/6-3 主文件名默认按 case_label=稳定型-HTTP 子集，避免多 case 混图
  python scripts/plot_thesis_ch6_figures.py --csv out.csv --case-label 波动型-UI --out-dir docs/images/ --flaky-json-dir docs/artifacts

CSV 列须含：case_id 或 case_label（可选）、mode、retry_times（run 模式）、success、elapsed_sec；图 6-3 另需 flaky_score 列或 --flaky-json-dir。
按 (case_id, 策略) 分组聚合：策略由 mode + retry_times 推导（run_smart 记为 run_smart）。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import numpy as np
    import pandas as pd
except ImportError:
    print("需要: pip install matplotlib pandas", file=sys.stderr)
    raise


from figure_fonts import configure_matplotlib_chinese


configure_matplotlib_chinese(plt, font_manager)


def _fig6_filenames(case_key: str | None) -> tuple[str, str, str]:
    """无筛选时用正文默认主图名；有 `--case-label` / `--case-id` 时在文件名中带区分片段。"""
    if case_key is None:
        return (
            "fig6-1_success_rates.png",
            "fig6-2_mean_elapsed.png",
            "fig6-3_flaky_gain.png",
        )
    tag = str(case_key)
    return (
        f"fig6-1_{tag}.png",
        f"fig6-2_{tag}.png",
        f"fig6-3_flaky_gain_{tag}.png",
    )


def _strategy_name(row) -> str:
    m = str(row.get("mode", ""))
    if m == "run_smart":
        return "run_smart"
    rt = row.get("retry_times", "")
    if rt == "" or (isinstance(rt, float) and np.isnan(rt)):
        return f"r=0"
    try:
        r = int(float(rt))
    except (TypeError, ValueError):
        r = 0
    return f"r={r}"


def _annotation_offset(index: int) -> tuple[int, int]:
    offsets = [(6, 8), (6, -14), (-44, 8), (-44, -14), (10, 20), (-56, 20)]
    return offsets[index % len(offsets)]


def _case_title(df: "pd.DataFrame", fallback: str | None = None) -> str:
    if fallback:
        return fallback
    if "case_label" in df.columns:
        labels = [str(x) for x in df["case_label"].dropna().unique() if str(x).strip()]
        if len(labels) == 1:
            return labels[0]
    if "case_id" in df.columns:
        ids = [str(int(x)) for x in df["case_id"].dropna().unique()]
        if len(ids) == 1:
            return f"case_id={ids[0]}"
    return "稳定型-HTTP"


def _ordered_strategies(strategies) -> list[str]:
    preferred = ["r=0", "r=1", "r=2", "r=3", "run_smart"]
    observed = [str(s) for s in strategies]
    ordered = [s for s in preferred if s in observed]
    ordered.extend(sorted(s for s in observed if s not in ordered))
    return ordered


def _load_flaky_map(json_dir: str) -> dict[int, float]:
    m: dict[int, float] = {}
    pattern = os.path.join(json_dir, "experiment_summary_case*.json")
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        cid = d.get("case_id")
        fa = d.get("flaky_analysis") or {}
        fs = fa.get("flaky_score")
        if cid is not None and fs is not None:
            m[int(cid)] = float(fs)
    return m


def load_df(path: str, *, flaky_json_dir: str | None = None) -> "pd.DataFrame":
    df = pd.read_csv(path)
    if "case_label" not in df.columns:
        df["case_label"] = ""
    if "strategy" not in df.columns:
        df["strategy"] = df.apply(_strategy_name, axis=1)
    if flaky_json_dir and (flaky_json_dir.strip() if isinstance(flaky_json_dir, str) else True):
        mp = _load_flaky_map(flaky_json_dir)
        if mp:
            df["flaky_score"] = df["case_id"].map(lambda x: mp.get(int(x)))
    return df


def plot_fig6_3_combined(df: "pd.DataFrame", out_dir: str) -> None:
    """跨 case_id：每点 = (flaky_score, 同用例下相对 r=0 的观测成功率提升)，策略为除 r=0 外各策略。"""
    os.makedirs(out_dir, exist_ok=True)
    if "flaky_score" not in df.columns or df["flaky_score"].isna().all():
        print("提示：无 flaky_score，图 6-3（合并）跳过。使用 --flaky-json-dir 或 enrich_thesis_csv_flaky_score.py。")
        return
    if "case_id" not in df.columns:
        print("提示：CSV 无 case_id，图 6-3（合并）跳过。")
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    case_ids = sorted(int(x) for x in df["case_id"].dropna().unique())
    markers = ["o", "s", "^", "D", "v", "P"]
    label_index = 0
    for j, cid in enumerate(case_ids):
        sub = df[df["case_id"] == cid]
        if sub.empty:
            continue
        fs = float(sub["flaky_score"].dropna().iloc[0]) if sub["flaky_score"].notna().any() else float("nan")
        if pd.isna(fs):
            continue
        base_mask = sub["strategy"].str.match(r"^r=0$", na=False)
        base = float(sub.loc[base_mask, "success"].mean()) if base_mask.any() else float("nan")
        k = 0
        for s in sub["strategy"].unique():
            if s == "r=0":
                continue
            chunk = sub[sub["strategy"] == s]
            if chunk.empty:
                continue
            ms = float(chunk["success"].mean())
            delta = ms - base if pd.notna(base) else 0.0
            mk = markers[k % len(markers)]
            k += 1
            ax.scatter(
                [fs],
                [delta],
                s=80,
                marker=mk,
                alpha=0.85,
                label=f"用例 {cid} {s}",
            )
            ax.annotate(
                f"{cid}:{s}",
                (fs, delta),
                textcoords="offset points",
                xytext=_annotation_offset(label_index),
                fontsize=7,
                arrowprops={"arrowstyle": "-", "color": "#999999", "linewidth": 0.5},
            )
            label_index += 1
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("flaky_score")
    ax.set_ylabel("相对 r=0 的观测成功率提升（同用例）")
    ax.set_title("图 6-3 各用例：flaky_score 与策略收益（合并）")
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.3)
    ax.text(
        0.01,
        0.98,
        "注：点坐标为真实统计值；本批各策略观测成功率均为 1.000，故收益点重合在 0。",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        color="#555555",
    )
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    p3 = os.path.join(out_dir, "fig6-3_flaky_gain_combined.png")
    fig.savefig(p3, dpi=220)
    plt.close(fig)
    print("已写入", p3)


def plot_figures(df: "pd.DataFrame", case_key: str | None, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    if case_key is not None and "case_label" in df.columns:
        sub = df[df["case_label"] == case_key]
    elif case_key is not None:
        sub = df[df["case_id"].astype(str) == str(case_key)]
    else:
        # 无 --case-id / --case-label 时：与论文 6.4.6「主文默认稳定型-HTTP 子集」一致，避免多 case 混在一张柱图里
        if "case_label" in df.columns and (df["case_label"] == "稳定型-HTTP").any():
            sub = df[df["case_label"] == "稳定型-HTTP"]
        else:
            sub = df
    if sub.empty:
        raise SystemExit("筛选后无数据，请检查 --case-label 或 CSV")
    title_case = _case_title(sub, case_key)
    g = sub.groupby("strategy", dropna=False)
    count = g["success"].count()
    mean_succ = g["success"].mean()
    se_succ = np.sqrt(mean_succ * (1 - mean_succ) / count).fillna(0)
    mean_time = g["elapsed_sec"].mean()
    std_time = g["elapsed_sec"].std().fillna(0)

    strategies = _ordered_strategies(mean_succ.index)
    count = count.reindex(strategies)
    mean_succ = mean_succ.reindex(strategies)
    se_succ = se_succ.reindex(strategies)
    mean_time = mean_time.reindex(strategies)
    std_time = std_time.reindex(strategies)
    x = np.arange(len(strategies))
    fn1, fn2, fn3 = _fig6_filenames(case_key)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(
        x,
        mean_succ.values,
        yerr=se_succ.values,
        capsize=4,
        color="#4E79A7",
        ecolor="#555555",
        alpha=0.92,
        linewidth=0.8,
        edgecolor="#2F4F6F",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(strategies, rotation=15, ha="right")
    ax.set_ylabel("观测成功率 p_hat")
    ax.set_title(f"图 6-1 {title_case}：各策略观测成功率（p_hat±SE）")
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.35)
    for bar, p_hat, se, n in zip(bars, mean_succ.values, se_succ.values, count.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            max(bar.get_height() - 0.035, 0.04),
            f"{p_hat:.3f}\nSE={se:.3f}\nN={int(n)}",
            ha="center",
            va="top" if bar.get_height() > 0.15 else "bottom",
            fontsize=8,
            color="white" if bar.get_height() > 0.15 else "#222222",
            fontweight="bold",
        )
    fig.tight_layout()
    p1 = os.path.join(out_dir, fn1)
    fig.savefig(p1, dpi=220)
    plt.close(fig)
    print("已写入", p1)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(
        x,
        mean_time.values,
        yerr=std_time.values,
        capsize=4,
        color="#F28E2B",
        ecolor="#555555",
        alpha=0.92,
        linewidth=0.8,
        edgecolor="#9B5418",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(strategies, rotation=15, ha="right")
    ax.set_ylabel("wall-clock 耗时 (s)")
    ax.set_title(f"图 6-2 {title_case}：各策略平均耗时（mean±std）")
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.35)
    top = float((mean_time + std_time).max()) if len(mean_time) else 0
    ax.set_ylim(0, max(top * 1.22, 0.1))
    for bar, avg, std, n in zip(bars, mean_time.values, std_time.values, count.values):
        ax.annotate(
            f"{avg:.3f}s\n±{std:.3f}\nN={int(n)}",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            va="bottom",
            fontsize=8,
        )
    fig.tight_layout()
    p2 = os.path.join(out_dir, fn2)
    fig.savefig(p2, dpi=220)
    plt.close(fig)
    print("已写入", p2)

    # 图 6-3：需各策略有同一 flaky_score；可在 CSV 增加常数列或在汇总后手填
    if "flaky_score" not in sub.columns:
        print("提示：CSV 无 flaky_score 列，图 6-3 跳过。可将 experiment_summary 的 flaky_score 写为常数列后重画。")
        return

    base_mask = sub["strategy"].str.match(r"^r=0$", na=False)
    base = sub.loc[base_mask, "success"].mean()
    xs, ys, labels = [], [], []
    for s in strategies:
        if s == "r=0":
            continue
        chunk = sub[sub["strategy"] == s]
        if chunk.empty:
            continue
        ms = chunk["success"].mean()
        fs = float(chunk["flaky_score"].iloc[0])
        xs.append(fs)
        ys.append(float(ms - base) if pd.notna(base) else 0.0)
        labels.append(s)
    if not xs:
        print("提示：无除 r=0 外的策略行，图 6-3 跳过。")
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter(xs, ys, s=60, c="green", alpha=0.7)
    for idx, (x, y, lab) in enumerate(zip(xs, ys, labels)):
        ax.annotate(
            lab,
            (x, y),
            textcoords="offset points",
            xytext=_annotation_offset(idx),
            fontsize=8,
            arrowprops={"arrowstyle": "-", "color": "#999999", "linewidth": 0.5},
        )
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("flaky_score")
    ax.set_ylabel("相对 r=0 的观测成功率提升")
    ax.set_title(f"图 6-3 {title_case}：flaky_score 与策略收益")
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.3)
    ax.text(
        0.01,
        0.98,
        "注：点坐标为真实统计值；本批成功率均为 1.000，故收益为 0。",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout()
    p3 = os.path.join(out_dir, fn3)
    fig.savefig(p3, dpi=220)
    plt.close(fig)
    print("已写入", p3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="run-series 产出的 CSV")
    ap.add_argument("--out-dir", default="docs/images", help="PNG 输出目录")
    ap.add_argument("--case-label", default=None, help="仅绘制某一类用例（需 CSV 有 case_label 或 case_id）")
    ap.add_argument("--case-id", default=None, help="仅绘制指定 case_id")
    ap.add_argument(
        "--flaky-json-dir",
        default=None,
        help="含 experiment_summary_case*.json 时，为每行注入 flaky_score（可不先手工改 CSV）",
    )
    ap.add_argument(
        "--fig6-3-combined-only",
        action="store_true",
        help="仅生成跨 case 的图 6-3（fig6-3_flaky_gain_combined.png），不画 6-1/6-2",
    )
    ap.add_argument(
        "--fig6-3-combined-also",
        action="store_true",
        help="在常规出图后额外写一张跨 case 的 fig6-3",
    )
    args = ap.parse_args()
    df = load_df(args.csv, flaky_json_dir=args.flaky_json_dir)
    if args.fig6_3_combined_only:
        plot_fig6_3_combined(df, args.out_dir)
        return
    key = None
    if args.case_label:
        key = args.case_label
    elif args.case_id:
        key = args.case_id
    plot_figures(df, key, args.out_dir)
    if args.fig6_3_combined_also:
        plot_fig6_3_combined(df, args.out_dir)


if __name__ == "__main__":
    main()
