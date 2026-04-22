"""Flaky 风险分析：Wilson 失败率上界、切换率、EWMA 融合与重试投影。

可配置项见 `core.settings`（环境变量 FLAKY_*）。纯函数便于单测与论文复现实验。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from django.conf import settings


def _analysis_config() -> Dict[str, Any]:
    return {
        "recent_window": int(getattr(settings, "FLAKY_RECENT_WINDOW", 30)),
        "weight_wilson": float(getattr(settings, "FLAKY_WEIGHT_WILSON", 0.5)),
        "weight_transition": float(getattr(settings, "FLAKY_WEIGHT_TRANSITION", 0.3)),
        "weight_ewma": float(getattr(settings, "FLAKY_WEIGHT_EWMA", 0.2)),
        "ewma_alpha": float(getattr(settings, "FLAKY_EWMA_ALPHA", 0.35)),
        "wilson_z": float(getattr(settings, "FLAKY_WILSON_Z", 1.96)),
    }


def _build_methodology(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": "1.1",
        "recent_window": cfg["recent_window"],
        "weights": {
            "wilson_failure_upper": cfg["weight_wilson"],
            "transition_rate": cfg["weight_transition"],
            "ewma_failure": cfg["weight_ewma"],
        },
        "ewma_alpha": cfg["ewma_alpha"],
        "wilson_z": cfg["wilson_z"],
        "assumptions": [
            "将窗口内每次执行视为同分布伯努利试验的样本；失败率用 Wilson 区间上界以控制小样本乐观偏差。",
            (
                "至少一次成功概率的投影使用 P(至少一次成功) ≈ 1 - p^k，其中 p 为 Wilson "
                "失败率上界、k 为连续独立尝试次数；各次尝试独立、同分布。"
            ),
        ],
        "limitations": [
            "未显式建模失败之间的相关性（例如基础设施连片故障、共享资源争用）。",
            "强顺序漂移或样本非平稳时，EWMA 与切换率可能放大短期波动；宜结合更大窗口或分段分析。",
        ],
    }


def _is_failure_status(status: str) -> bool:
    return status in {"failed", "error"}


def compute_flaky_analysis_from_statuses(
    statuses_chronological: Sequence[str],
    *,
    target_success: float = 0.95,
    max_attempts: int = 3,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """根据时间正序（由旧到新）的执行状态序列计算 Flaky 指标。

    ``statuses_chronological`` 应与原实现一致：先取最近 N 条记录再 ``reversed`` 得到时间正序。
    """
    cfg = dict(_analysis_config() if config is None else {**_analysis_config(), **config})
    methodology = _build_methodology(cfg)

    seq: List[int] = []
    for st in statuses_chronological:
        seq.append(1 if _is_failure_status(str(st)) else 0)

    if not seq:
        return {
            "sample_size": 0,
            "flaky_score": 0,
            "risk_level": "unknown",
            "failure_rate": 0.0,
            "ewma_failure": 0.0,
            "transition_rate": 0.0,
            "wilson_failure_upper": 0.0,
            "suggested_retries": 0,
            "suggested_attempts": 1,
            "projections": [],
            "message": "暂无执行样本，请先运行该用例后再分析。",
            "warning": "样本量不足，分析结果不可靠",
            "meta": {
                "target_success": float(target_success),
                "max_attempts": int(max_attempts),
            },
            "methodology": methodology,
        }

    n = len(seq)
    fail_count = sum(seq)
    failure_rate = fail_count / n if n else 0.0

    if n < 5:
        warning = f"当前样本量仅 {n} 次，建议至少运行 5 次后再依据分析结果制定策略。"
        confidence_level = "low"
    elif n < 10:
        warning = f"当前样本量为 {n} 次，建议增加至 10 次以上以提高分析可信度。"
        confidence_level = "medium"
    else:
        warning = None
        confidence_level = "high"

    alpha = float(cfg["ewma_alpha"])
    alpha = max(0.01, min(alpha, 0.99))
    ewma = float(seq[0]) if seq else 0.0
    for x in seq[1:]:
        ewma = alpha * x + (1 - alpha) * ewma

    transitions = 0
    for i in range(1, n):
        if seq[i] != seq[i - 1]:
            transitions += 1
    transition_rate = transitions / (n - 1) if n > 1 else 0.0

    z = float(cfg["wilson_z"])
    if n > 0:
        p = failure_rate
        denom = 1 + (z * z) / n
        center = (p + (z * z) / (2 * n)) / denom
        margin = z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n) / denom
        wilson_upper = min(1.0, max(0.0, center + margin))
    else:
        wilson_upper = 0.0

    w1 = float(cfg["weight_wilson"])
    w2 = float(cfg["weight_transition"])
    w3 = float(cfg["weight_ewma"])
    wsum = w1 + w2 + w3
    if wsum <= 0:
        w1, w2, w3 = 0.5, 0.3, 0.2
    else:
        w1, w2, w3 = w1 / wsum, w2 / wsum, w3 / wsum

    flaky_score = int(
        round(
            min(
                100.0,
                max(
                    0.0,
                    100.0 * (w1 * wilson_upper + w2 * transition_rate + w3 * ewma),
                ),
            )
        )
    )

    if flaky_score >= 70:
        risk_level = "high"
    elif flaky_score >= 45:
        risk_level = "medium"
    else:
        risk_level = "low"

    projections = []
    suggested_attempts = int(max_attempts)
    for attempts in range(1, int(max_attempts) + 1):
        projected_success = 1 - (wilson_upper**attempts)
        projections.append(
            {
                "attempts": attempts,
                "projected_success": round(projected_success, 4),
            }
        )
        if projected_success >= float(target_success) and suggested_attempts == int(max_attempts):
            suggested_attempts = attempts

    suggested_retries = max(0, suggested_attempts - 1)

    if n >= 10:
        message = "分值越高表示该用例近期越不稳定；建议按预测成功率动态设置重试次数。"
    else:
        message = f"当前样本量为 {n} 次，分析结果可信度有限。建议增加执行次数后再依据分析结果制定策略。"

    result: Dict[str, Any] = {
        "sample_size": n,
        "flaky_score": flaky_score,
        "risk_level": risk_level,
        "failure_rate": round(failure_rate, 4),
        "ewma_failure": round(float(ewma), 4),
        "transition_rate": round(transition_rate, 4),
        "wilson_failure_upper": round(wilson_upper, 4),
        "suggested_retries": suggested_retries,
        "suggested_attempts": suggested_attempts,
        "projections": projections,
        "message": message,
        "confidence_level": confidence_level,
        "meta": {
            "target_success": float(target_success),
            "max_attempts": int(max_attempts),
            "weights_effective": {"wilson": w1, "transition": w2, "ewma": w3},
        },
        "methodology": methodology,
    }

    if warning:
        result["warning"] = warning

    return result


def compute_flaky_analysis_for_case(case, *, target_success: float = 0.95, max_attempts: int = 3) -> Dict[str, Any]:
    """从用例关联的 ``TestRecord`` 读取最近窗口并计算 Flaky 分析。"""
    window = max(5, min(int(getattr(settings, "FLAKY_RECENT_WINDOW", 30)), 200))
    recent_records = list(case.records.all().order_by("-created_at")[:window])
    statuses = [r.status for r in reversed(recent_records)]
    return compute_flaky_analysis_from_statuses(
        statuses,
        target_success=target_success,
        max_attempts=max_attempts,
    )


def build_strategy_comparison(flaky_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """生成便于论文对比表/API 展示的固定重试 vs 自适应策略行。"""
    projections = flaky_payload.get("projections") or []
    proj_by_attempts = {int(p["attempts"]): p["projected_success"] for p in projections if "attempts" in p}

    rows: List[Dict[str, Any]] = []
    for retry_times in range(0, 4):
        attempts = retry_times + 1
        rows.append(
            {
                "kind": "fixed",
                "label": f"固定策略：retry_times={retry_times}（等价单次 run 指定重试）",
                "retry_times": retry_times,
                "max_attempts": attempts,
                "projected_at_least_one_success": proj_by_attempts.get(attempts),
            }
        )

    rows.append(
        {
            "kind": "adaptive",
            "label": "自适应策略：run_smart 当前建议",
            "retry_times": int(flaky_payload.get("suggested_retries", 0)),
            "max_attempts": int(flaky_payload.get("suggested_attempts", 1)),
            "projected_at_least_one_success": proj_by_attempts.get(int(flaky_payload.get("suggested_attempts", 1))),
            "flaky_score": flaky_payload.get("flaky_score"),
            "risk_level": flaky_payload.get("risk_level"),
        }
    )
    return rows


def build_execution_stats_for_case(case) -> Dict[str, Any]:
    """与 Flaky 分析同一窗口的执行耗时与成败统计（用于实验摘要）。"""
    window = max(5, min(int(getattr(settings, "FLAKY_RECENT_WINDOW", 30)), 200))
    recent = list(case.records.all().order_by("-created_at")[:window])
    if not recent:
        return {
            "window_cap": window,
            "sample_size": 0,
            "success": 0,
            "failed": 0,
            "error": 0,
            "other": 0,
            "empirical_failure_rate": 0.0,
            "avg_elapsed_seconds": 0.0,
            "min_elapsed_seconds": None,
            "max_elapsed_seconds": None,
        }

    success = failed = err = other = 0
    elapsed: List[float] = []
    for r in recent:
        st = r.status
        if st == "success":
            success += 1
        elif st == "failed":
            failed += 1
        elif st == "error":
            err += 1
        else:
            other += 1
        elapsed.append(float(r.elapsed_time or 0.0))

    n = len(recent)
    fail_like = failed + err
    return {
        "window_cap": window,
        "sample_size": n,
        "success": success,
        "failed": failed,
        "error": err,
        "other": other,
        "empirical_failure_rate": round(fail_like / n, 4) if n else 0.0,
        "avg_elapsed_seconds": round(sum(elapsed) / n, 4) if n else 0.0,
        "min_elapsed_seconds": round(min(elapsed), 4) if elapsed else None,
        "max_elapsed_seconds": round(max(elapsed), 4) if elapsed else None,
    }
