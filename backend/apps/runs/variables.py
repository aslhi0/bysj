"""
全局变量池：步骤字符串中的 {{var}} 占位符替换（与用例 variables + 运行时 variables 合并）。
"""
from __future__ import annotations

import re
from typing import Any, Callable

_VAR_PATTERN = re.compile(r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}')


def expand_strings(obj: Any, replace: Callable[[str], str]) -> Any:
    """递归处理 dict/list，仅对 str 调用 replace。"""
    if isinstance(obj, str):
        return replace(obj)
    if isinstance(obj, dict):
        return {k: expand_strings(v, replace) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_strings(v, replace) for v in obj]
    return obj


def substitute_placeholders(template: str, context: dict[str, Any], on_missing) -> str:
    """将 {{name}} 替换为 context[name] 的字符串形式；缺失时调用 on_missing(name) 并替换为返回值。"""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in context:
            val = context[key]
            if val is None:
                return ''
            return str(val)
        return on_missing(key)

    return _VAR_PATTERN.sub(repl, template)
