#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论文第 6 章策略对照实验：批量触发 run / run_smart、轮询 task_status、导出 experiment_summary。

用法（在已启动后端、已创建用例与登录账号的前提下）：

  set THESIS_API_BASE=http://127.0.0.1:8000
  set THESIS_USERNAME=你的用户
  set THESIS_PASSWORD=你的密码

  # 1) 拉取实验汇总（制表用 execution_stats、flaky_analysis、strategy_comparison）
  python scripts/thesis_experiment.py summary --case-id 1

  # 2) 对某用例跑 N 次固定重试=0
  python scripts/thesis_experiment.py run-series --case-id 1 --mode run --retry-times 0 --n 30 --sleep 3

  # 3) 对某用例跑 N 次 run_smart
  python scripts/thesis_experiment.py run-series --case-id 1 --mode run_smart --n 15 --sleep 3

  # 4) 将结果追加到 CSV（列：timestamp,case_id,case_label,mode,...；--label 区分多批次）
  python scripts/thesis_experiment.py run-series --case-id 1 --mode run --retry-times 2 --n 15 --out runs.csv

环境变量：THESIS_API_BASE、THESIS_USERNAME、THESIS_PASSWORD；也可用命令行 --base-url、--user、--pass。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    print("需要安装 requests: pip install requests", file=sys.stderr)
    raise


def _base_url() -> str:
    return (os.environ.get("THESIS_API_BASE") or "http://127.0.0.1:8000").rstrip("/")


def _creds() -> tuple[str, str]:
    u = os.environ.get("THESIS_USERNAME") or ""
    p = os.environ.get("THESIS_PASSWORD") or ""
    return u, p


def get_token(
    base: str, username: str, password: str, timeout: float = 15.0
) -> str:
    r = requests.post(
        f"{base}/api/auth/token/",
        json={"username": username, "password": password},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    access = data.get("access")
    if not access:
        raise RuntimeError(f"响应无 access: {data}")
    return str(access)


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_experiment_summary(
    base: str,
    token: str,
    case_id: int,
    *,
    target_success: float = 0.95,
    max_attempts: int = 3,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    r = requests.get(
        f"{base}/api/cases/{case_id}/experiment_summary/",
        params={"target_success": target_success, "max_attempts": max_attempts},
        headers=_headers(token),
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def post_run(
    base: str,
    token: str,
    case_id: int,
    *,
    mode: str,
    retry_times: int = 0,
    target_success: float = 0.95,
    max_attempts: int = 3,
    env_id: Optional[int] = None,
    timeout: float = 30.0,
) -> str:
    url = f"{base}/api/cases/{case_id}/"
    if mode == "run":
        path = f"{url}run/"
        body: Dict[str, Any] = {"retry_times": retry_times}
    elif mode == "run_smart":
        path = f"{url}run_smart/"
        body = {"target_success": target_success, "max_attempts": max_attempts}
    else:
        raise ValueError("mode 须为 run 或 run_smart")
    if env_id is not None:
        body["env_id"] = env_id
    r = requests.post(path, json=body, headers=_headers(token), timeout=timeout)
    r.raise_for_status()
    data = r.json()
    tid = data.get("task_id")
    if not tid:
        raise RuntimeError(f"无 task_id: {data}")
    return str(tid)


def poll_task(
    base: str,
    token: str,
    task_id: str,
    *,
    poll_interval: float = 0.5,
    max_wait: float = 600.0,
) -> Dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < max_wait:
        r = requests.get(
            f"{base}/api/task-status/{task_id}/",
            headers=_headers(token),
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ready"):
            return data
        time.sleep(poll_interval)
    raise TimeoutError(f"task {task_id} 在 {max_wait}s 内未完成")


def _parse_outcome(ready_payload: Dict[str, Any]) -> tuple[bool, float, int, int]:
    """(success, elapsed_sec, attempts_made, retries_used) — 自 task_status.result。"""
    res = ready_payload.get("result")
    if not isinstance(res, dict):
        return False, 0.0, 0, 0
    st = str(res.get("status") or "").lower()
    success = st == "success"
    elapsed = 0.0
    et = res.get("elapsed_time")
    if et is not None:
        try:
            elapsed = float(et)
        except (TypeError, ValueError):
            pass
    am = int(res.get("attempts_made") or res.get("attempts") or 0)
    ru = int(res.get("retries_used") or 0)
    return success, elapsed, am, ru


def cmd_login(args: argparse.Namespace) -> None:
    u = args.user or _creds()[0]
    p = args.password or _creds()[1]
    if not u or not p:
        print("请设置 THESIS_USERNAME/THESIS_PASSWORD 或使用 --user/--password", file=sys.stderr)
        sys.exit(2)
    base = args.base_url or _base_url()
    token = get_token(base, u, p)
    print(json.dumps({"access": token, "base": base}, ensure_ascii=False, indent=2))


def cmd_summary(args: argparse.Namespace) -> None:
    u = args.user or _creds()[0]
    p = args.password or _creds()[1]
    if not u or not p:
        print("需要登录凭据", file=sys.stderr)
        sys.exit(2)
    base = args.base_url or _base_url()
    token = get_token(base, u, p)
    data = fetch_experiment_summary(
        base,
        token,
        args.case_id,
        target_success=args.target_success,
        max_attempts=args.max_attempts,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_summary_json(args: argparse.Namespace) -> None:
    u = args.user or _creds()[0]
    p = args.password or _creds()[1]
    if not u or not p:
        print("需要登录凭据", file=sys.stderr)
        sys.exit(2)
    base = args.base_url or _base_url()
    token = get_token(base, u, p)
    data = fetch_experiment_summary(
        base,
        token,
        args.case_id,
        target_success=args.target_success,
        max_attempts=args.max_attempts,
    )
    out = args.out
    _d = os.path.dirname(os.path.abspath(out))
    if _d:
        os.makedirs(_d, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(out, "written", file=sys.stderr)


def cmd_run_series(args: argparse.Namespace) -> None:
    u = args.user or _creds()[0]
    p = args.password or _creds()[1]
    if not u or not p:
        print("需要登录凭据", file=sys.stderr)
        sys.exit(2)
    base = args.base_url or _base_url()
    token = get_token(base, u, p)
    out_path = args.out
    f_out = open(out_path, "a", encoding="utf-8") if out_path else None
    if f_out and out_path:
        need_header = (not os.path.isfile(out_path)) or os.path.getsize(out_path) == 0
        if need_header:
            f_out.write(
                "timestamp,case_id,case_label,mode,retry_times,success,elapsed_sec,attempts_made,retries_used,task_id\n"
            )
    try:
        for i in range(args.n):
            tid = post_run(
                base,
                token,
                args.case_id,
                mode=args.mode,
                retry_times=args.retry_times,
                target_success=args.target_success,
                max_attempts=args.max_attempts,
                env_id=args.env_id,
            )
            ready = poll_task(base, token, tid, max_wait=args.max_wait)
            ok, el, am, ru = _parse_outcome(ready)
            row = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "case_id": args.case_id,
                "mode": args.mode,
                "retry_times": args.retry_times if args.mode == "run" else "",
                "success": ok,
                "elapsed_sec": round(el, 3),
                "attempts_made": am,
                "retries_used": ru,
                "task_id": tid,
            }
            rt = row["retry_times"] if args.mode == "run" else ""
            lab = getattr(args, "label", "") or ""
            line = f'{row["ts"]},{row["case_id"]},{lab},{row["mode"]},{rt},{1 if row["success"] else 0},{row["elapsed_sec"]},{row["attempts_made"]},{row["retries_used"]},{row["task_id"]}\n'
            if f_out:
                f_out.write(line)
            row_out = {**row, "case_label": lab}
            print(json.dumps(row_out, ensure_ascii=False), flush=True)
            if i + 1 < args.n:
                time.sleep(args.sleep)
    finally:
        if f_out:
            f_out.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="论文策略对照实验 API 批跑")
    ap.add_argument("--base-url", default=None, help="API 基址，默认 THESIS_API_BASE 或 127.0.0.1:8000")
    ap.add_argument("--user", default=None, help="用户名，默认 THESIS_USERNAME")
    ap.add_argument("--password", default=None, help="密码，默认 THESIS_PASSWORD")

    sub = ap.add_subparsers(dest="cmd", required=True)

    s_login = sub.add_parser("login", help="获取 JWT 并打印")
    s_login.set_defaults(func=cmd_login)

    s_sum = sub.add_parser("summary", help="GET experiment_summary JSON")
    s_sum.add_argument("--case-id", type=int, required=True)
    s_sum.add_argument("--target-success", type=float, default=0.95)
    s_sum.add_argument("--max-attempts", type=int, default=3)
    s_sum.set_defaults(func=cmd_summary)

    s_sumj = sub.add_parser("summary-json", help="同 summary，但写入 JSON 文件便于归档")
    s_sumj.add_argument("--case-id", type=int, required=True)
    s_sumj.add_argument("--out", required=True, help="输出 .json 路径")
    s_sumj.add_argument("--target-success", type=float, default=0.95)
    s_sumj.add_argument("--max-attempts", type=int, default=3)
    s_sumj.set_defaults(func=cmd_summary_json)

    s_run = sub.add_parser("run-series", help="连续触发 run 或 run_smart 并轮询")
    s_run.add_argument("--case-id", type=int, required=True)
    s_run.add_argument("--mode", choices=["run", "run_smart"], required=True)
    s_run.add_argument("--retry-times", type=int, default=0, help="仅 mode=run 时有效，0~3")
    s_run.add_argument("--target-success", type=float, default=0.95)
    s_run.add_argument("--max-attempts", type=int, default=3)
    s_run.add_argument("--env-id", type=int, default=None)
    s_run.add_argument("--n", type=int, default=30, help="重复次数")
    s_run.add_argument("--sleep", type=float, default=3.0, help="两次触发间隔秒数")
    s_run.add_argument("--max-wait", type=float, default=600.0, help="单任务最大等待秒数")
    s_run.add_argument("--out", default=None, help="追加 CSV 路径")
    s_run.add_argument(
        "--label",
        default="",
        help="写入 CSV 的 case_label 列，便于多批次合并后按组绘图（如 稳定型 / 波动型）",
    )
    s_run.set_defaults(func=cmd_run_series)

    args = ap.parse_args()
    if args.base_url:
        # inject for cmds
        os.environ["THESIS_API_BASE"] = args.base_url
    args.func(args)


if __name__ == "__main__":
    main()
