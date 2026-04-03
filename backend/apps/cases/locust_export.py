"""从套件用例的 HTTP 步骤生成可运行的 Locust 脚本文本（无第三方生成依赖）。"""
from __future__ import annotations

import re
from typing import Any

from .models import TestSuite

_VAR_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _py_ident(s: str, fallback: str) -> str:
    t = _VAR_RE.sub("_", s).strip("_")
    if t and t[0].isdigit():
        t = "_" + t
    return (t[:48] or fallback).lower()


def _is_http_step(step: Any) -> bool:
    if not isinstance(step, dict):
        return False
    st = step.get("type", "http")
    if st in ("ui", "legacy_text"):
        return False
    if st == "http" or "url" in step:
        u = step.get("url")
        return isinstance(u, str) and bool(u.strip())
    return False


def _py_repr(obj: Any) -> str:
    return repr(obj)


def build_locust_script(suite: TestSuite) -> str:
    suite_vars = suite.variables if isinstance(suite.variables, dict) else {}
    blocks: list[str] = []

    task_n = 0
    for sc in suite.suite_cases.select_related("testcase").order_by("order", "id"):
        case = sc.testcase
        case_vars = case.variables if isinstance(case.variables, dict) else {}
        merged = {**suite_vars, **case_vars}
        steps = case.steps if isinstance(case.steps, list) else []
        cslug = _py_ident(case.title, f"case_{case.id}")

        for si, step in enumerate(steps):
            if not _is_http_step(step):
                continue
            task_n += 1
            method = (step.get("method") or "GET").upper()
            url = step.get("url")
            assert isinstance(url, str)
            headers = step.get("headers")
            if not isinstance(headers, dict):
                headers = {}
            timeout = step.get("timeout", 30)
            try:
                timeout_f = float(timeout)
            except (TypeError, ValueError):
                timeout_f = 30.0
            body = step.get("body")

            fn = f"t{task_n}_{cslug}_s{si}"
            lines = [
                f"    @task",
                f"    def {fn}(self):",
                f"        ctx = {_py_repr(merged)}",
                f'        method = {_py_repr(method)}',
                f"        url = _expand({_py_repr(url)}, ctx)",
                f"        headers = _expand({_py_repr(dict(headers))}, ctx)",
                f"        timeout = {timeout_f!r}",
            ]
            if isinstance(body, (dict, list)):
                lines.append(f"        payload = _expand({_py_repr(body)}, ctx)")
                lines.append(
                    "        self.client.request(method, url, headers=headers, json=payload, timeout=timeout)"
                )
            elif isinstance(body, str):
                lines.append(f"        raw = _expand({_py_repr(body)}, ctx)")
                lines.append("        hdrs = dict(headers)")
                lines.append(
                    "        if not any(str(k).lower() == 'content-type' for k in hdrs):"
                )
                lines.append(
                    "            hdrs['Content-Type'] = 'text/plain; charset=utf-8'"
                )
                lines.append(
                    "        self.client.request(method, url, headers=hdrs, data=raw.encode('utf-8'), timeout=timeout)"
                )
            elif body is not None:
                lines.append(f"        self.client.request(method, url, headers=headers, data={_py_repr(body)}, timeout=timeout)")
            else:
                lines.append(
                    "        self.client.request(method, url, headers=headers, timeout=timeout)"
                )
            blocks.append("\n".join(lines))

    if not blocks:
        blocks.append(
            "    @task\n"
            "    def _no_http_steps(self):\n"
            "        # 本套件无 HTTP 步骤（仅 UI 或其它类型）；请补充 @task 或调整用例。\n"
            "        pass\n"
        )

    pat = r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}"
    header = (
        '"""Locust 压测脚本（由测试平台按套件 HTTP 步骤自动生成）。\n'
        "运行: pip install locust && locust -f 本文件.py\n"
        '"""\n'
        "import re\n"
        "from locust import HttpUser, task, between\n"
        "\n"
        '_VAR = re.compile(r"' + pat + '")\n'
        "\n"
        "def _expand(obj, ctx):\n"
        "    if isinstance(obj, str):\n"
        "        return _VAR.sub(lambda m: str(ctx.get(m.group(1), '')), obj)\n"
        "    if isinstance(obj, dict):\n"
        "        return {k: _expand(v, ctx) for k, v in obj.items()}\n"
        "    if isinstance(obj, list):\n"
        "        return [_expand(v, ctx) for v in obj]\n"
        "    return obj\n"
        "\n"
        "\n"
        "class SuiteUser(HttpUser):\n"
        "    wait_time = between(1, 2)\n"
    )
    return header + "\n" + "\n\n".join(blocks) + "\n"
