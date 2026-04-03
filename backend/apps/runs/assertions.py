"""
HTTP 响应多维度断言（与开题报告「状态码 / 耗时 / JSON 字段 / JSON Schema」对齐）。
步骤中可选字段 assert 示例见 HttpExecutor 文档字符串。
"""
from __future__ import annotations

import json
from typing import Any

import requests

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


class AssertionErrorDetail(Exception):
    """断言失败时携带可读说明。"""


def get_by_path(data: Any, path: str) -> Any:
    """点分路径访问 dict/list，如 slideshow.author 或 items.0.id。"""
    cur = data
    for segment in path.split('.'):
        if segment == '':
            continue
        if isinstance(cur, dict):
            if segment not in cur:
                raise KeyError(segment)
            cur = cur[segment]
        elif isinstance(cur, list):
            if not segment.isdigit():
                raise TypeError(f'路径 {path!r} 在列表处需要数字下标，得到 {segment!r}')
            idx = int(segment)
            cur = cur[idx]
        else:
            raise TypeError(f'无法在 {type(cur).__name__} 上继续访问路径 {path!r}')
    return cur


def run_http_assertions(
    resp: requests.Response,
    request_elapsed_s: float,
    assert_cfg: dict[str, Any] | None,
) -> None:
    """
    根据 assert_cfg 校验响应；不通过则抛出 AssertionErrorDetail。
    assert_cfg 为 None 或 {} 时不做额外断言（由调用方处理默认状态码规则）。
    """
    if not assert_cfg:
        return

    if not isinstance(assert_cfg, dict):
        raise AssertionErrorDetail('assert 必须为 JSON 对象')

    if 'status_code' in assert_cfg:
        expected = assert_cfg['status_code']
        allowed = expected if isinstance(expected, (list, tuple)) else [expected]
        if resp.status_code not in allowed:
            raise AssertionErrorDetail(
                f'状态码期望 {allowed}，实际 {resp.status_code}'
            )

    max_s = assert_cfg.get('max_elapsed_seconds')
    max_ms = assert_cfg.get('max_elapsed_ms')
    if max_s is not None:
        try:
            limit = float(max_s)
        except (TypeError, ValueError):
            raise AssertionErrorDetail('max_elapsed_seconds 须为数字') from None
        if request_elapsed_s > limit:
            raise AssertionErrorDetail(
                f'响应耗时 {request_elapsed_s:.3f}s 超过上限 {limit}s'
            )
    if max_ms is not None:
        try:
            limit_ms = float(max_ms)
        except (TypeError, ValueError):
            raise AssertionErrorDetail('max_elapsed_ms 须为数字') from None
        if request_elapsed_s * 1000 > limit_ms:
            raise AssertionErrorDetail(
                f'响应耗时 {request_elapsed_s * 1000:.1f}ms 超过上限 {limit_ms}ms'
            )

    body_contains = assert_cfg.get('body_contains')
    if body_contains is not None:
        if not isinstance(body_contains, str):
            raise AssertionErrorDetail('body_contains 须为字符串')
        if body_contains not in (resp.text or ''):
            raise AssertionErrorDetail(f'响应体未包含子串: {body_contains!r}')

    json_paths = assert_cfg.get('json_paths')
    if json_paths is not None:
        if not isinstance(json_paths, list):
            raise AssertionErrorDetail('json_paths 须为数组')
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AssertionErrorDetail(f'响应非合法 JSON，无法做 json_paths 断言: {exc}') from exc
        for i, rule in enumerate(json_paths, start=1):
            if not isinstance(rule, dict):
                raise AssertionErrorDetail(f'json_paths[{i}] 须为对象')
            path = rule.get('path')
            if not path or not isinstance(path, str):
                raise AssertionErrorDetail(f'json_paths[{i}] 缺少 path 字符串')
            try:
                got = get_by_path(data, path)
            except (KeyError, IndexError, TypeError) as exc:
                raise AssertionErrorDetail(f'json_paths[{i}] 路径 {path!r} 取值失败: {exc}') from exc
            if 'equals' in rule:
                if got != rule['equals']:
                    raise AssertionErrorDetail(
                        f'json_paths[{i}] path={path!r} 期望 {rule["equals"]!r} 实际 {got!r}'
                    )
            if 'contains' in rule:
                sub = rule['contains']
                if not isinstance(sub, str):
                    raise AssertionErrorDetail(f'json_paths[{i}] contains 须为字符串')
                if sub not in str(got):
                    raise AssertionErrorDetail(
                        f'json_paths[{i}] path={path!r} 值 {got!r} 不包含 {sub!r}'
                    )

    schema = assert_cfg.get('json_schema')
    if schema is not None:
        if jsonschema is None:
            raise AssertionErrorDetail('未安装 jsonschema 库，无法执行 json_schema 断言')
        if not isinstance(schema, dict):
            raise AssertionErrorDetail('json_schema 须为 JSON Schema 对象')
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AssertionErrorDetail(f'响应非合法 JSON，无法做 json_schema 校验: {exc}') from exc
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as exc:
            raise AssertionErrorDetail(f'JSON Schema 校验失败: {exc.message}') from exc
