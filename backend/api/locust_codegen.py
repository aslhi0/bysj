"""从 HTTP 用例步骤生成 Locust 压测脚本（供异步压测与脚本下载复用）。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .engine import TestEngine


def _build_task_lines(steps: List[Dict], engine: TestEngine) -> tuple[List[str], Optional[str]]:
    """从步骤列表中提取 HTTP 请求，返回 (task_lines, inferred_host)。

    task_lines 是缩进好的 Python 代码行列表（供嵌入 @task 方法体）。
    inferred_host 是从第一个绝对 URL 推断出的 host，若无绝对 URL 则为 None。
    """
    task_lines: List[str] = []
    inferred_host: Optional[str] = None

    for step in steps:
        if step.get('type') != 'http':
            continue

        method = str(step.get('method', 'GET')).upper().strip() or 'GET'
        raw_url = step.get('url', '/')
        rendered = engine.render_string(raw_url) if isinstance(raw_url, str) else raw_url
        target = rendered if isinstance(rendered, str) else '/'

        if target.startswith('http://') or target.startswith('https://'):
            u = urlparse(target)
            if not inferred_host and u.scheme and u.netloc:
                inferred_host = f'{u.scheme}://{u.netloc}'
            path = u.path or '/'
            if u.query:
                path = f'{path}?{u.query}'
            target = path

        if not isinstance(target, str) or not target:
            target = '/'
        if not target.startswith('/'):
            target = f'/{target}'

        headers = engine.parse_jsonish(step.get('headers', {}), default={})
        if not isinstance(headers, dict):
            headers = {}

        body_raw = step.get('body', '')
        body_obj = None
        body_text = None
        if isinstance(body_raw, (dict, list)):
            body_obj = engine.render_data(body_raw)
        elif isinstance(body_raw, str):
            s = engine.render_string(body_raw)
            try:
                parsed = json.loads(s) if s.strip() else None
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, (dict, list)):
                body_obj = engine.render_data(parsed)
            else:
                body_text = s

        kwargs = []
        if headers:
            kwargs.append(f'headers={json.dumps(headers, ensure_ascii=False)}')
        if body_obj is not None:
            kwargs.append(f'json={json.dumps(body_obj, ensure_ascii=False)}')
        elif body_text:
            kwargs.append(f'data={json.dumps(body_text, ensure_ascii=False)}')
        kwargs.append(f'name={json.dumps(f"{method} {target}", ensure_ascii=False)}')

        kw = (', ' + ', '.join(kwargs)) if kwargs else ''
        task_lines.append(
            f'        self.client.request({json.dumps(method)}, {json.dumps(target)}{kw})'
        )

    return task_lines, inferred_host


def _render_host(host: str) -> str:
    """将 host 字符串序列化为可安全嵌入 Python 字符串字面量的形式。

    使用 json.dumps 保证换行符、反斜杠、双引号等特殊字符均被正确转义。
    """
    # json.dumps 产出形如 '"http://example.com"'，去掉两端引号后即为转义后的内容
    return json.dumps(host)[1:-1]


def generate_locust_code(
    case: Any,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> str:
    """根据用例中的 HTTP 步骤生成可运行的 Locust 文件内容。"""
    engine_vars = variables if isinstance(variables, dict) else {}
    if base_url:
        engine_vars = {**engine_vars, 'base_url': base_url, 'base': base_url}
    engine = TestEngine(variables=engine_vars)

    task_lines, inferred_host = _build_task_lines(case.steps or [], engine)
    if not task_lines:
        task_lines = ['        pass']

    host = base_url or inferred_host or 'http://127.0.0.1'
    safe_host = _render_host(host)

    return (
        f'from locust import HttpUser, task, between\n'
        f'\n'
        f'class QuickstartUser(HttpUser):\n'
        f'    host = "{safe_host}"\n'
        f'    wait_time = between(1, 2)\n'
        f'\n'
        f'    @task\n'
        f'    def functional_case_task(self):\n'
        + '\n'.join(task_lines) + '\n'
    )


def generate_locust_code_for_suite(
    suite: Any,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> str:
    """根据套件中所有用例的 HTTP 步骤生成可运行的 Locust 文件内容。

    套件内所有用例步骤合并为单一 @task，保持原始顺序。
    """
    from .models import TestCase  # 延迟导入避免循环依赖

    engine_vars = variables if isinstance(variables, dict) else {}
    if base_url:
        engine_vars = {**engine_vars, 'base_url': base_url, 'base': base_url}
    engine = TestEngine(variables=engine_vars)

    ordered_ids = suite.ordered_case_ids or []
    cases = TestCase.objects.filter(id__in=ordered_ids)
    case_map = {c.id: c for c in cases}

    all_task_lines: List[str] = []
    inferred_host: Optional[str] = None

    for cid in ordered_ids:
        case = case_map.get(cid)
        if not case:
            continue
        lines, host = _build_task_lines(case.steps or [], engine)
        all_task_lines.extend(lines)
        if not inferred_host and host:
            inferred_host = host

    if not all_task_lines:
        all_task_lines = ['        pass']

    host = base_url or inferred_host or 'http://127.0.0.1'
    safe_host = _render_host(host)
    safe_class = f'suite_{suite.id}'

    return (
        f'from locust import HttpUser, task, between\n'
        f'\n'
        f'class {safe_class}(HttpUser):\n'
        f'    host = "{safe_host}"\n'
        f'    wait_time = between(1, 2)\n'
        f'\n'
        f'    @task\n'
        f'    def run_suite(self):\n'
        + '\n'.join(all_task_lines) + '\n'
    )
