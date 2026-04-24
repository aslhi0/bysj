#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从当前 Django DB 写出与 experiment_summary 接口结构一致的 JSON（论文归档）。"""
from __future__ import annotations

import argparse
import json
import os
import sys

import django

NOTES = {
    "fixed_rows": "retry_times 0~3 对应 POST /cases/{id}/run/ 的手动重试上限；投影基于 Wilson 失败率上界与独立尝试假设。",
    "adaptive_row": "与 POST /cases/{id}/run_smart/ 使用的建议一致；请在相同 target_success/max_attempts 下对比。",
}


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", type=int, action="append", required=True, dest="case_ids")
    ap.add_argument("--out-dir", required=True, help="每用例写 experiment_summary_case{id}.json")
    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    backend = os.path.normpath(os.path.join(here, "..", "backend"))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    django.setup()

    from api.flaky_analysis import compute_flaky_analysis_for_case
    from api.models import TestCase
    from api.views_case import build_execution_stats_for_case, build_strategy_comparison

    out_dir = args.out_dir
    for cid in args.case_ids:
        case = TestCase.objects.get(pk=cid)
        flaky = compute_flaky_analysis_for_case(
            case, target_success=0.95, max_attempts=3
        )
        out = {
            "case_id": case.id,
            "case_title": case.title,
            "execution_stats": build_execution_stats_for_case(case),
            "flaky_analysis": flaky,
            "strategy_comparison": build_strategy_comparison(flaky),
            "notes": NOTES,
        }
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"experiment_summary_case{case.id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            print(path, file=sys.stderr)


if __name__ == "__main__":
    main()
