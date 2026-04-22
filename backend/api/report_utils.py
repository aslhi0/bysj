"""Utilities for rendering reports and parsing perf CSV files."""
from __future__ import annotations

import csv
import html
import os


def sanitize_filename(value, default="record"):
    s = "" if value is None else str(value)
    if not s.strip():
        return default
    for ch in ["\\", "/", ":", "*", "?", '"', "<", ">", "|", "\r", "\n"]:
        s = s.replace(ch, "_")
    s = s.strip()
    return s or default


def build_test_record_report_json_payload(record, screenshot_url):
    case = record.case
    project = case.project
    return {
        "record_id": record.id,
        "case_id": case.id,
        "case_title": case.title,
        "project_id": project.id,
        "project_name": project.name,
        "status": record.status,
        "elapsed_time": record.elapsed_time,
        "attempts": getattr(record, "attempts", 1),
        "attempt_logs": getattr(record, "attempt_logs", []) or [],
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "result_log": record.result_log or "",
        "step_results": record.step_results or [],
        "screenshot_url": screenshot_url,
    }


def build_test_record_report_html(record, screenshot_url):
    case = record.case
    project = case.project

    status_map = {
        "success": ("通过", "#67C23A"),
        "failed": ("失败", "#F56C6C"),
        "running": ("执行中", "#909399"),
        "error": ("异常", "#E6A23C"),
    }
    status_text, status_color = status_map.get(record.status, (record.status, "#909399"))

    def esc(s):
        return html.escape("" if s is None else str(s))

    step_rows = []
    for i, sr in enumerate(record.step_results or []):
        name = esc(sr.get("name") or f"步骤 {i + 1}")
        st = sr.get("status") or ""
        st_text = "通过" if st == "success" else "失败"
        st_color = "#67C23A" if st == "success" else "#F56C6C"
        elapsed = esc(sr.get("elapsed") or "")
        logs = sr.get("log") or []
        if not isinstance(logs, list):
            logs = [logs]
        logs_html = "<br/>".join(esc(l) for l in logs if l is not None)
        step_rows.append(
            f"<tr>"
            f"<td>{i + 1}</td>"
            f"<td>{name}</td>"
            f"<td style='color:{st_color};font-weight:600'>{st_text}</td>"
            f"<td>{elapsed}</td>"
            f"<td style='font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size:12px'>{logs_html}</td>"
            f"</tr>"
        )

    full_log = esc(record.result_log or "")
    created_at = esc(record.created_at)
    elapsed_time = esc(f"{record.elapsed_time:.2f}")
    title = esc(case.title)
    project_name = esc(project.name)
    attempts_val = int(getattr(record, "attempts", 1) or 1)
    attempt_logs_val = getattr(record, "attempt_logs", []) or []

    attempts_block = ""
    if attempts_val > 1 and isinstance(attempt_logs_val, list) and attempt_logs_val:
        att_rows = []
        for item in attempt_logs_val:
            if not isinstance(item, dict):
                continue
            att_st = str(item.get("status") or "")
            att_color = "#67C23A" if att_st == "success" else ("#E6A23C" if att_st == "error" else "#F56C6C")
            att_label = {"success": "通过", "failed": "失败", "error": "异常"}.get(att_st, att_st)
            att_rows.append(
                f"<tr>"
                f"<td>{esc(item.get('attempt'))}</td>"
                f"<td style='color:{att_color};font-weight:600'>{esc(att_label)}</td>"
                f"<td>{esc(item.get('elapsed'))}</td>"
                f"<td style='font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size:12px'>{esc(item.get('error_message') or '')}</td>"
                f"</tr>"
            )
        attempts_block = (
            f"<h2>重试历史（共 {attempts_val} 次尝试）</h2>"
            "<table>"
            "<thead><tr><th>#</th><th>结果</th><th>耗时(s)</th><th>错误信息</th></tr></thead>"
            f"<tbody>{''.join(att_rows)}</tbody></table>"
        )

    screenshot_block = ""
    if screenshot_url:
        screenshot_block = (
            f"<h2>失败截图</h2>"
            f"<div style='margin: 8px 0'>"
            f"<a href='{esc(screenshot_url)}' target='_blank' rel='noreferrer'>打开原图</a>"
            f"</div>"
            f"<img src='{esc(screenshot_url)}' style='max-width:100%; border:1px solid #eee' />"
        )

    return (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'/>"
        f"<title>测试报告 - Record #{record.id}</title>"
        "<style>"
        "body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;max-width:1100px;margin:24px auto;padding:0 16px;}"
        "h1{font-size:20px;margin:0 0 8px 0;}"
        "h2{font-size:16px;margin:20px 0 8px 0;}"
        ".meta{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;}"
        ".tag{display:inline-block;padding:4px 8px;border-radius:6px;background:#f5f7fa;font-size:12px;}"
        "table{border-collapse:collapse;width:100%;}"
        "th,td{border:1px solid #ebeef5;padding:8px 10px;font-size:13px;vertical-align:top;}"
        "th{background:#fafafa;text-align:left;}"
        "pre{background:#0b1020;color:#e6edf3;padding:12px;border-radius:8px;overflow:auto;font-size:12px;line-height:1.5;}"
        "</style>"
        "</head><body>"
        f"<h1>测试报告 - Record #{record.id}</h1>"
        "<div class='meta'>"
        f"<span class='tag'>项目：{project_name}</span>"
        f"<span class='tag'>用例：{title}</span>"
        f"<span class='tag'>时间：{created_at}</span>"
        f"<span class='tag'>耗时：{elapsed_time}s</span>"
        f"<span class='tag' style='background:{status_color};color:#fff'>结果：{esc(status_text)}</span>"
        "</div>"
        "<h2>步骤明细</h2>"
        "<table>"
        "<thead><tr><th>#</th><th>步骤</th><th>状态</th><th>耗时(s)</th><th>简要日志</th></tr></thead>"
        "<tbody>"
        + "".join(step_rows)
        + "</tbody></table>"
        f"{attempts_block}"
        f"{screenshot_block}"
        "<h2>原始日志</h2>"
        f"<pre>{full_log}</pre>"
        "</body></html>"
    )


def read_csv_rows(file_path):
    rows = []
    if not os.path.exists(file_path):
        return rows
    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def parse_int(v, default=0):
    try:
        if v is None:
            return default
        s = str(v).strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def parse_float(v, default=0.0):
    try:
        if v is None:
            return default
        s = str(v).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default


def pick_aggregated_row(stats_rows):
    for r in stats_rows:
        name = (r.get("Name") or r.get("name") or "").strip().lower()
        typ = (r.get("Type") or r.get("type") or "").strip().lower()
        if name in {"aggregated", "total"} or typ in {"aggregated", "total"}:
            return r
    if stats_rows:
        return stats_rows[0]
    return None
