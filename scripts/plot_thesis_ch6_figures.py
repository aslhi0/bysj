#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据 thesis_experiment.py 导出的 CSV 或手工汇总表绘制第 6 章图 6-1～6-3。

依赖：pip install matplotlib pandas

示例：
  python scripts/plot_thesis_ch6_figures.py --csv runs.csv --out-dir docs/images/
  python scripts/plot_thesis_ch6_figures.py --csv runs.csv --case-label 稳定型-A --out-dir docs/images/

CSV 列须含：case_id 或 case_label（可选）、mode、retry_times（run 模式）、success、elapsed_sec。
按 (case_id, 策略) 分组聚合：策略由 mode + retry_times 推导（run_smart 记为 adaptive）。
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("需要: pip install matplotlib pandas", file=sys.stderr)
    raise


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


def load_df(path: str) -> "pd.DataFrame":
    df = pd.read_csv(path)
    if "case_label" not in df.columns:
        df["case_label"] = ""
    if "strategy" not in df.columns:
        df["strategy"] = df.apply(_strategy_name, axis=1)
    return df


def plot_figures(df: "pd.DataFrame", case_key: str | None, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    if case_key is not None and "case_label" in df.columns:
        sub = df[df["case_label"] == case_key]
    elif case_key is not None:
        sub = df[df["case_id"].astype(str) == str(case_key)]
    else:
        sub = df
    if sub.empty:
        raise SystemExit("筛选后无数据，请检查 --case-label 或 CSV")

    g = sub.groupby("strategy", dropna=False)
    mean_succ = g["success"].mean()
    std_succ = g["success"].std().fillna(0)
    mean_time = g["elapsed_sec"].mean()

    strategies = list(mean_succ.index)
    x = np.arange(len(strategies))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(x, mean_succ.values, yerr=std_succ.values, capsize=4, color="steelblue", ecolor="gray", alpha=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(strategies, rotation=15, ha="right")
    ax.set_ylabel("观测成功率")
    ax.set_title("图 6-1 各策略观测成功率（均值±标准差）")
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    p1 = os.path.join(out_dir, "fig6-1_success_rates.png")
    fig.savefig(p1, dpi=150)
    plt.close(fig)
    print("已写入", p1)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(x, mean_time.values, color="coral", alpha=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(strategies, rotation=15, ha="right")
    ax.set_ylabel("平均 wall-clock 耗时 (s)")
    ax.set_title("图 6-2 各策略平均耗时")
    fig.tight_layout()
    p2 = os.path.join(out_dir, "fig6-2_mean_elapsed.png")
    fig.savefig(p2, dpi=150)
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
    for x, y, lab in zip(xs, ys, labels):
        ax.annotate(lab, (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("flaky_score")
    ax.set_ylabel("相对 r=0 的观测成功率提升")
    ax.set_title("图 6-3 flaky_score 与 run_smart/固定重试之收益")
    fig.tight_layout()
    p3 = os.path.join(out_dir, "fig6-3_flaky_gain.png")
    fig.savefig(p3, dpi=150)
    plt.close(fig)
    print("已写入", p3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="run-series 产出的 CSV")
    ap.add_argument("--out-dir", default="docs/images", help="PNG 输出目录")
    ap.add_argument("--case-label", default=None, help="仅绘制某一类用例（需 CSV 有 case_label 或 case_id）")
    ap.add_argument("--case-id", default=None, help="仅绘制指定 case_id")
    args = ap.parse_args()
    df = load_df(args.csv)
    key = None
    if args.case_label:
        key = args.case_label
    elif args.case_id:
        key = args.case_id
    plot_figures(df, key, args.out_dir)


if __name__ == "__main__":
    main()
