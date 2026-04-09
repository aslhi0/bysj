"""从 HTTP 用例步骤生成 Locust 压测脚本（供异步压测与脚本下载复用）。"""
from __future__ import annotations

import ast
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .engine import TestEngine


def _build_request_specs(steps: List[Dict], engine: TestEngine) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """从步骤列表中提取 HTTP 请求并归一化为 request specs。"""
    specs: List[Dict[str, Any]] = []
    inferred_host: Optional[str] = None

    for step in steps:
        if step.get("type") != "http":
            continue

        method = str(step.get("method", "GET")).upper().strip() or "GET"
        raw_url = step.get("url", "/")
        rendered = engine.render_string(raw_url) if isinstance(raw_url, str) else raw_url
        target = rendered if isinstance(rendered, str) else "/"

        if target.startswith("http://") or target.startswith("https://"):
            u = urlparse(target)
            if not inferred_host and u.scheme and u.netloc:
                inferred_host = f"{u.scheme}://{u.netloc}"
            path = u.path or "/"
            if u.query:
                path = f"{path}?{u.query}"
            target = path

        if not isinstance(target, str) or not target:
            target = "/"
        if not target.startswith("/"):
            target = f"/{target}"

        headers = engine.parse_jsonish(step.get("headers", {}), default={})
        if not isinstance(headers, dict):
            headers = {}

        body_raw = step.get("body", "")
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

        spec: Dict[str, Any] = {
            "method": method,
            "target": target,
            "name": f"{method} {target}",
        }
        if headers:
            spec["headers"] = headers
        if body_obj is not None:
            spec["json"] = body_obj
        elif body_text:
            spec["data"] = body_text
        specs.append(spec)

    return specs, inferred_host


def _literal_node(value: Any) -> ast.expr:
    """Safely convert Python literal to AST node."""
    return ast.parse(repr(value), mode="eval").body


def _build_request_expr(spec: Dict[str, Any]) -> ast.Expr:
    keywords = [
        ast.keyword(arg="name", value=_literal_node(spec["name"])),
    ]
    if "headers" in spec:
        keywords.append(ast.keyword(arg="headers", value=_literal_node(spec["headers"])))
    if "json" in spec:
        keywords.append(ast.keyword(arg="json", value=_literal_node(spec["json"])))
    elif "data" in spec:
        keywords.append(ast.keyword(arg="data", value=_literal_node(spec["data"])))

    call = ast.Call(
        func=ast.Attribute(
            value=ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="client", ctx=ast.Load()),
            attr="request",
            ctx=ast.Load(),
        ),
        args=[_literal_node(spec["method"]), _literal_node(spec["target"])],
        keywords=keywords,
    )
    return ast.Expr(value=call)


def _render_locust_module(*, class_name: str, method_name: str, host: str, specs: List[Dict[str, Any]]) -> str:
    method_body: List[ast.stmt]
    if specs:
        method_body = [_build_request_expr(s) for s in specs]
    else:
        method_body = [ast.Pass()]

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="locust",
                names=[
                    ast.alias(name="HttpUser"),
                    ast.alias(name="task"),
                    ast.alias(name="between"),
                ],
                level=0,
            ),
            ast.ClassDef(
                name=class_name,
                bases=[ast.Name(id="HttpUser", ctx=ast.Load())],
                keywords=[],
                decorator_list=[],
                body=[
                    ast.Assign(
                        targets=[ast.Name(id="host", ctx=ast.Store())],
                        value=_literal_node(host),
                    ),
                    ast.Assign(
                        targets=[ast.Name(id="wait_time", ctx=ast.Store())],
                        value=ast.Call(
                            func=ast.Name(id="between", ctx=ast.Load()),
                            args=[ast.Constant(value=1), ast.Constant(value=2)],
                            keywords=[],
                        ),
                    ),
                    ast.FunctionDef(
                        name=method_name,
                        args=ast.arguments(
                            posonlyargs=[],
                            args=[ast.arg(arg="self")],
                            kwonlyargs=[],
                            kw_defaults=[],
                            defaults=[],
                        ),
                        body=method_body,
                        decorator_list=[ast.Name(id="task", ctx=ast.Load())],
                        returns=None,
                        type_comment=None,
                    ),
                ],
            ),
        ],
        type_ignores=[],
    )
    return ast.unparse(ast.fix_missing_locations(module)) + "\n"


def generate_locust_code(
    case: Any,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> str:
    """根据用例中的 HTTP 步骤生成可运行的 Locust 文件内容。"""
    engine_vars = variables if isinstance(variables, dict) else {}
    if base_url:
        engine_vars = {**engine_vars, "base_url": base_url, "base": base_url}
    engine = TestEngine(variables=engine_vars)
    specs, inferred_host = _build_request_specs(case.steps or [], engine)
    host = base_url or inferred_host or "http://127.0.0.1"
    return _render_locust_module(
        class_name="QuickstartUser",
        method_name="functional_case_task",
        host=host,
        specs=specs,
    )


def generate_locust_code_for_suite(
    suite: Any,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> str:
    """根据套件中所有用例的 HTTP 步骤生成可运行的 Locust 文件内容。"""
    from .models import TestCase  # 延迟导入避免循环依赖

    engine_vars = variables if isinstance(variables, dict) else {}
    if base_url:
        engine_vars = {**engine_vars, "base_url": base_url, "base": base_url}
    engine = TestEngine(variables=engine_vars)

    ordered_ids = suite.ordered_case_ids or []
    cases = TestCase.objects.filter(id__in=ordered_ids)
    case_map = {c.id: c for c in cases}

    all_specs: List[Dict[str, Any]] = []
    inferred_host: Optional[str] = None
    for cid in ordered_ids:
        case = case_map.get(cid)
        if not case:
            continue
        specs, host = _build_request_specs(case.steps or [], engine)
        all_specs.extend(specs)
        if not inferred_host and host:
            inferred_host = host

    host = base_url or inferred_host or "http://127.0.0.1"
    return _render_locust_module(
        class_name=f"suite_{suite.id}",
        method_name="run_suite",
        host=host,
        specs=all_specs,
    )
