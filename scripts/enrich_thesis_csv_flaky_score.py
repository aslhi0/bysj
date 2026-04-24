#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 thesis_experiment 导出的 CSV 按 case_id 追加 flaky_score 列（来自 experiment_summary JSON）。

用法：
  python scripts/enrich_thesis_csv_flaky_score.py data/thesis_runs.csv out.csv --json-dir docs/artifacts

默认读取 json-dir 下 experiment_summary_case*.json，解析 flaky_analysis.flaky_score。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

try:
    import pandas as pd
except ImportError:
    print("需要: pip install pandas", file=sys.stderr)
    raise


def load_map(json_dir: str) -> dict[int, float]:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv")
    ap.add_argument("output_csv")
    ap.add_argument("--json-dir", required=True, help="含 experiment_summary_case*.json 的目录")
    args = ap.parse_args()
    mp = load_map(args.json_dir)
    if not mp:
        print("未找到任何 experiment_summary_case*.json 或缺少 flaky_score", file=sys.stderr)
        sys.exit(1)
    df = pd.read_csv(args.input_csv)
    if "case_id" not in df.columns:
        print("CSV 须含 case_id", file=sys.stderr)
        sys.exit(1)
    df["flaky_score"] = df["case_id"].map(lambda x: mp.get(int(x)))
    miss = df["flaky_score"].isna().sum()
    if miss:
        print(f"警告: {miss} 行未匹配到 flaky_score（case_id 不在 JSON 中）", file=sys.stderr)
    out_dir = os.path.dirname(os.path.abspath(args.output_csv))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    df.to_csv(args.output_csv, index=False, encoding="utf-8")
    print(args.output_csv, "written", f"cases: {sorted(mp.keys())}", file=sys.stderr)


if __name__ == "__main__":
    main()
