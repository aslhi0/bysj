"""
从 OpenAPI 3.x / Swagger 2.0 文档生成接口用例骨架（单操作单用例，步骤为一条 HTTP）。
路径参数 {id} 转为占位符 {{id}}；默认变量 base_url 取自 servers / host+basePath。
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests
import yaml

from apps.cases.models import TestCase
from apps.projects.models import Project


def load_spec_dict(
    *,
    spec: dict[str, Any] | None = None,
    spec_url: str | None = None,
    spec_yaml: str | None = None,
) -> dict[str, Any]:
    """从三种来源之一加载 OpenAPI 文档为 dict。"""
    if spec is not None:
        if not isinstance(spec, dict):
            raise ValueError('spec 须为 JSON 对象')
        return spec
    if spec_url:
        try:
            resp = requests.get(spec_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f'无法拉取 spec_url: {exc}') from exc
        text = resp.text.strip()
        if text.startswith('{'):
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f'JSON 解析失败: {exc}') from exc
        else:
            loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ValueError('URL 返回内容须为 JSON/YAML 对象')
        return loaded
    if spec_yaml is not None and spec_yaml.strip():
        parsed = yaml.safe_load(spec_yaml)
        if not isinstance(parsed, dict):
            raise ValueError('YAML 须解析为对象')
        return parsed
    raise ValueError('缺少 OpenAPI 文档内容')

HTTP_METHODS = ('get', 'post', 'put', 'patch', 'delete')


def _path_to_url_template(path: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return '{{' + match.group(1) + '}}'

    return re.sub(r'\{([^}]+)\}', repl, path)


def _default_base_url(spec: dict[str, Any]) -> str:
    ver = spec.get('openapi')
    if isinstance(ver, str) and ver.startswith('3'):
        servers = spec.get('servers') or []
        if servers and isinstance(servers[0], dict):
            u = (servers[0].get('url') or '').strip().rstrip('/')
            if u:
                return u
        return 'https://api.example.com'

    if spec.get('swagger') == '2.0':
        schemes = spec.get('schemes') or ['https']
        scheme = 'https' if 'https' in schemes else str(schemes[0])
        host = (spec.get('host') or '').strip() or 'api.example.com'
        base_path = spec.get('basePath') or '/'
        if not str(base_path).startswith('/'):
            base_path = '/' + str(base_path)
        root = f'{scheme}://{host}'.rstrip('/')
        if base_path and base_path != '/':
            return (root + base_path).rstrip('/')
        return root

    return 'https://api.example.com'


def _expected_status_for_method(method: str) -> list[int]:
    m = method.lower()
    if m == 'post':
        return [200, 201, 204]
    if m == 'delete':
        return [200, 204]
    return [200]


def _operation_title(method: str, path: str, op: dict[str, Any]) -> str:
    summary = op.get('summary')
    op_id = op.get('operationId')
    if summary and isinstance(summary, str):
        return f'{summary.strip()} [{method.upper()} {path}]'
    if op_id and isinstance(op_id, str):
        return f'{op_id.strip()} [{method.upper()} {path}]'
    return f'{method.upper()} {path}'


def _merge_parameters(path_item: dict[str, Any], op: dict[str, Any]) -> list[Any]:
    out = []
    for chunk in (path_item.get('parameters'), op.get('parameters')):
        if isinstance(chunk, list):
            out.extend(chunk)
    return out


def _example_json_body(op: dict[str, Any], spec: dict[str, Any]) -> Any | None:
    """OpenAPI 3 requestBody content application/json schema 简单示例占位（可选）。"""
    rb = op.get('requestBody')
    if not isinstance(rb, dict):
        return None
    content = rb.get('content')
    if not isinstance(content, dict):
        return None
    app_json = content.get('application/json') or content.get('application/*+json')
    if not isinstance(app_json, dict):
        return None
    schema = app_json.get('schema')
    if not isinstance(schema, dict):
        return None
    return _schema_to_example(schema, spec)


def _schema_to_example(schema: dict[str, Any], spec: dict[str, Any], depth: int = 0) -> Any:
    if depth > 8:
        return None
    ref = schema.get('$ref')
    if isinstance(ref, str) and ref.startswith('#/'):
        resolved = _resolve_ref(spec, ref)
        if resolved:
            return _schema_to_example(resolved, spec, depth + 1)
    if 'example' in schema:
        return schema['example']
    typ = schema.get('type')
    props = schema.get('properties')
    if typ == 'object' or (typ is None and isinstance(props, dict)):
        if isinstance(props, dict):
            return {k: _schema_to_example(v, spec, depth + 1) for k, v in props.items()}
        return {}
    if typ == 'array':
        inner = schema.get('items')
        if isinstance(inner, dict):
            return [_schema_to_example(inner, spec, depth + 1)]
        return []
    if typ == 'string':
        return schema.get('default') or ''
    if typ == 'integer':
        return schema.get('default', 0)
    if typ == 'number':
        return schema.get('default', 0.0)
    if typ == 'boolean':
        return schema.get('default', False)
    return None


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any] | None:
    # #/components/schemas/Foo
    parts = ref.strip('#/').split('/')
    cur: Any = spec
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur if isinstance(cur, dict) else None


def _swagger_body_param(spec: dict[str, Any], parameters: list[Any]) -> dict[str, Any] | None:
    for p in parameters:
        if not isinstance(p, dict):
            continue
        if p.get('in') == 'body' and 'schema' in p:
            sch = p['schema']
            if isinstance(sch, dict):
                ex = _schema_to_example(sch, spec)
                if ex is not None:
                    return ex
    return None


def build_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """返回 {method, path, title, step} 列表。"""
    base = _default_base_url(spec)
    paths = spec.get('paths')
    if not isinstance(paths, dict):
        return []

    out: list[dict[str, Any]] = []
    is_oas3 = isinstance(spec.get('openapi'), str) and spec['openapi'].startswith('3')

    for path_key, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        url_suffix = _path_to_url_template(path_key)
        for method in HTTP_METHODS:
            if method not in path_item:
                continue
            op = path_item[method]
            if not isinstance(op, dict):
                continue

            title = _operation_title(method, path_key, op)
            params = _merge_parameters(path_item, op)

            step: dict[str, Any] = {
                'type': 'http',
                'method': method.upper(),
                'url': '{{base_url}}' + (url_suffix if url_suffix.startswith('/') else '/' + url_suffix),
                'assert': {'status_code': _expected_status_for_method(method)},
            }

            if is_oas3:
                body = _example_json_body(op, spec)
                if body is not None:
                    step['body'] = body
            else:
                body = _swagger_body_param(spec, params)
                if body is not None:
                    step['body'] = body

            out.append(
                {
                    'method': method,
                    'path': path_key,
                    'title': title[:300],
                    'step': step,
                    'variables': {'base_url': base},
                }
            )

    return out


def import_from_spec(spec: dict[str, Any], project: Project) -> dict[str, Any]:
    """
    为 project 批量创建 TestCase。返回 {created_ids, count, warnings}。
    """
    warnings: list[str] = []
    ops = build_operations(spec)
    if not ops:
        warnings.append('未解析到任何 paths 下的 get/post/put/patch/delete 操作')
        return {'created_ids': [], 'count': 0, 'warnings': warnings}

    created_ids: list[int] = []
    for item in ops:
        tc = TestCase.objects.create(
            project=project,
            title=item['title'],
            steps=[item['step']],
            variables=item['variables'],
            status=TestCase.Status.DRAFT,
        )
        created_ids.append(tc.id)

    return {'created_ids': created_ids, 'count': len(created_ids), 'warnings': warnings}
