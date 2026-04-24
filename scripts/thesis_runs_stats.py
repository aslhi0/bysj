#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对 thesis_experiment.py 导出的 CSV 按 (case_id, 策略) 做描述统计，便于填写表 6-3
并报告「观测成功率」的均值/标准差（二项可补充标准误 SE=sqrt(p̂(1-p̂)/n)）。

用法：
  python scripts/thesis_runs_stats.py data/thesis_runs.csv
  python scripts/thesis_runs_stats.py data/thesis_runs.csv --by-label

需列：case_id, mode, retry_times(可为空), success, elapsed_sec；可选 case_label。
"""
from __future__ import annotations

import argparse
import math
import os
import sys

try:
    import pandas as pd
except ImportError:
    print("需要: pip install pandas", file=sys.stderr)
    raise


def _strategy(row) -> str:
    m = str(row.get("mode", ""))
    if m == "run_smart":
        return "run_smart"
    rt = row.get("retry_times", "")
    if rt is None or (isinstance(rt, float) and pd.isna(rt)) or str(rt).strip() == "":
        return "r=0"
    try:
        r = int(float(rt))
    except (TypeError, ValueError):
        r = 0
    return f"r={r}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="thesis_experiment run-series 导出的 CSV")
    ap.add_argument(
        "--by-label",
        action="store_true",
        help="按 case_label 再分组（多类用例合并一表时）",
    )
    args = ap.parse_args()
    path = args.csv
    if not os.path.isfile(path):
        print("文件不存在:", path, file=sys.stderr)
        sys.exit(1)
    df = pd.read_csv(path)
    df["strategy"] = df.apply(_strategy, axis=1)
    keys = ["case_id", "strategy"]
    if args.by_label and "case_label" in df.columns:
        keys = ["case_label"] + keys

    g = df.groupby(keys, dropna=False)
    rows = []
    for name, part in g:
        n = len(part)
        p_hat = part["success"].mean()
        se = math.sqrt(p_hat * (1.0 - p_hat) / n) if n else 0.0
        t_mean = part["elapsed_sec"].mean()
        t_std = part["elapsed_sec"].std()
        if pd.isna(t_std):
            t_std = 0.0
        am = part["attempts_made"].mean() if "attempts_made" in part.columns else float("nan")
        rows.append(
            {
                "group": name,
                "n": n,
                "obs_success_mean": p_hat,
                "obs_success_se": se,
                "elapsed_mean": t_mean,
                "elapsed_std": t_std,
                "attempts_mean": am,
            }
        )
    out = pd.DataFrame(rows)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}" if abs(x) < 10 else f"{x:.2f}")
    print(out.to_string(index=False))
    print(
        "\n[Note] obs_success_mean: obs. success rate; obs_success_se: binomial SE. "
        "For p_hat=0/1, SE=0; consider reporting n or a Wilson/CP interval in prose."
    )
    print("Do not use projected_success as observed pass rate in the thesis table.")


if __name__ == "__main__":
    main()
