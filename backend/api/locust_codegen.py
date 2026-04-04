"""从 HTTP 用例步骤生成 Locust 压测脚本（供异步压测与脚本下载复用）。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .engine import TestEngine


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
    tasks: List[str] = []
    inferred_host = None
    for step in case.steps or []:
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
        tasks.append(f'        self.client.request({json.dumps(method)}, {json.dumps(target)}{kw})')
    if not tasks:
        tasks = ['        pass']

    host = base_url or inferred_host or 'http://127.0.0.1'
    safe_host = str(host).replace('"', '\\"')

    template = f"""
from locust import HttpUser, task, between

class QuickstartUser(HttpUser):
    host = "{safe_host}"
    wait_time = between(1, 2)

    @task
    def functional_case_task(self):
{chr(10).join(tasks)}
"""
    return template.lstrip()
