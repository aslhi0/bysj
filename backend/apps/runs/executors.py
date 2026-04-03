"""
同步混合执行器：同一 TestCase.steps 内交替执行 HTTP（requests）与 UI（Selenium 4 / WebDriver）。

type: http — 见模块内 HTTP 说明；type: ui — 见下方 action 列表。

全局变量池、HTTP capture/assert 与 HTTP 步骤相同；UI 步骤中字符串同样支持 {{var}}。

UI 步骤（type: ui）常用字段：
  - action: open | navigate | goto — 打开 url（需安装 Chrome；browser.headless 默认 false 便于本地调试）
  - action: click | wait_click — selector + 可选 by（css|xpath|id|name|class）
  - action: input | type | fill — selector、text（或 value）、clear 默认 true
  - action: wait_visible | wait — 等待元素可见
  - action: sleep — seconds，无需浏览器
  - browser: { "headless": true/false, "args": ["--disable-extensions"], "window_size": [1280,900] }
  - timeout: 显式等待秒数，默认 15
"""
from __future__ import annotations

import copy
import time
import traceback
from typing import Any

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from apps.cases.models import TestCase
from apps.runs.assertions import AssertionErrorDetail, get_by_path, run_http_assertions
from apps.runs.models import TestRecord
from apps.runs.variables import expand_strings, substitute_placeholders


class HttpExecutor:
    """混合执行 HTTP + UI 步骤；兼容旧称 HttpExecutor。"""

    def __init__(
        self,
        test_case: TestCase,
        runtime_variables: dict[str, Any] | None = None,
    ):
        self.test_case = test_case
        self._runtime = runtime_variables or {}
        self._lines: list[str] = []
        self._ctx: dict[str, Any] = {}
        self._current_step_index = 0
        self._logged_missing_keys: set[tuple[int, str]] = set()
        self._driver: webdriver.Chrome | None = None

    def _log(self, message: str) -> None:
        self._lines.append(message)

    def _init_context(self) -> None:
        base = self.test_case.variables
        if not isinstance(base, dict):
            base = {}
        merged = {**base, **self._runtime}
        self._ctx = dict(merged)
        if self._ctx:
            keys = ', '.join(sorted(self._ctx.keys()))
            self._log(f'变量池（合并后键）: {keys}')

    def _replace_placeholders(self, text: str) -> str:
        step = self._current_step_index

        def on_missing(key: str) -> str:
            sig = (step, key)
            if sig not in self._logged_missing_keys:
                self._logged_missing_keys.add(sig)
                self._log(f'步骤{step}: 变量 {key!r} 未定义，替换为空')
            return ''

        return substitute_placeholders(text, self._ctx, on_missing)

    def _expand_value(self, obj: Any) -> Any:
        return expand_strings(obj, self._replace_placeholders)

    def _quit_driver(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
            self._log('UI: 已关闭浏览器')

    def _ensure_driver(self, browser_cfg: dict[str, Any] | None) -> bool:
        if self._driver is not None:
            return True
        cfg = browser_cfg if isinstance(browser_cfg, dict) else {}
        options = webdriver.ChromeOptions()
        if cfg.get('headless', False):
            options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        ws = cfg.get('window_size')
        if isinstance(ws, (list, tuple)) and len(ws) >= 2:
            options.add_argument(f'--window-size={int(ws[0])},{int(ws[1])}')
        else:
            options.add_argument('--window-size=1280,900')
        for arg in cfg.get('args', []) or []:
            if isinstance(arg, str) and arg.strip():
                options.add_argument(arg)
        try:
            self._driver = webdriver.Chrome(options=options)
            self._log('UI: 已启动 Chrome（Selenium 4 / W3C WebDriver）')
        except WebDriverException as exc:
            self._log(f'UI: Chrome 启动失败 — {exc}')
            return False
        return True

    @staticmethod
    def _by_tuple(by: str | None, selector: str) -> tuple[str, str]:
        b = (by or 'css').lower()
        mapping = {
            'css': By.CSS_SELECTOR,
            'css_selector': By.CSS_SELECTOR,
            'xpath': By.XPATH,
            'id': By.ID,
            'name': By.NAME,
            'class': By.CLASS_NAME,
            'class_name': By.CLASS_NAME,
            'tag': By.TAG_NAME,
        }
        return mapping.get(b, By.CSS_SELECTOR), selector

    @staticmethod
    def _parse_wait_timeout(raw: Any, default: float = 15.0) -> float:
        try:
            t = float(raw)
            return max(0.5, min(t, 120.0))
        except (TypeError, ValueError):
            return default

    def _run_ui_step(self, index: int, step: dict[str, Any]) -> bool:
        self._current_step_index = index
        step = self._expand_value(copy.deepcopy(step))
        action = (step.get('action') or '').lower()
        browser_cfg = step.get('browser') if isinstance(step.get('browser'), dict) else {}
        timeout = self._parse_wait_timeout(step.get('timeout'), 15.0)

        try:
            if action in ('sleep', 'wait_seconds'):
                try:
                    sec = float(step.get('seconds', step.get('duration', 1)))
                except (TypeError, ValueError):
                    sec = 1.0
                sec = max(0.0, min(sec, 60.0))
                time.sleep(sec)
                self._log(f'步骤{index}: UI 等待 {sec}s')
                return True

            if action in ('open', 'navigate', 'goto'):
                url = step.get('url')
                if not url or not isinstance(url, str):
                    self._log(f'步骤{index}: UI open/navigate 需要 url')
                    return False
                if not self._ensure_driver(browser_cfg):
                    return False
                assert self._driver is not None
                self._driver.get(url)
                self._log(f'步骤{index}: UI 打开 {url}')
                return True

            if action in ('click', 'wait_click'):
                if not self._ensure_driver(browser_cfg):
                    return False
                assert self._driver is not None
                selector = step.get('selector')
                if not selector or not isinstance(selector, str):
                    self._log(f'步骤{index}: click 需要 selector 字符串')
                    return False
                by, sel = self._by_tuple(step.get('by'), selector)
                el = WebDriverWait(self._driver, timeout).until(
                    EC.element_to_be_clickable((by, sel))
                )
                el.click()
                self._log(f'步骤{index}: UI 点击 {by}={sel!r}')
                return True

            if action in ('input', 'type', 'send_keys', 'fill'):
                if not self._ensure_driver(browser_cfg):
                    return False
                assert self._driver is not None
                selector = step.get('selector')
                if not selector or not isinstance(selector, str):
                    self._log(f'步骤{index}: input 需要 selector')
                    return False
                text = step.get('text', step.get('value', ''))
                if not isinstance(text, str):
                    text = str(text)
                by, sel = self._by_tuple(step.get('by'), selector)
                el = WebDriverWait(self._driver, timeout).until(
                    EC.visibility_of_element_located((by, sel))
                )
                if step.get('clear', True):
                    el.clear()
                el.send_keys(text)
                self._log(f'步骤{index}: UI 输入 -> {by}={sel!r}')
                return True

            if action in ('wait_visible', 'wait_element', 'wait'):
                if not self._ensure_driver(browser_cfg):
                    return False
                assert self._driver is not None
                selector = step.get('selector')
                if not selector or not isinstance(selector, str):
                    self._log(f'步骤{index}: wait_visible 需要 selector')
                    return False
                by, sel = self._by_tuple(step.get('by'), selector)
                WebDriverWait(self._driver, timeout).until(
                    EC.visibility_of_element_located((by, sel))
                )
                self._log(f'步骤{index}: UI 元素已可见 {by}={sel!r}')
                return True

            self._log(f'步骤{index}: 未知 UI action={action!r}（支持 open/click/input/wait_visible/sleep）')
            return False

        except TimeoutException as exc:
            self._log(f'步骤{index}: UI 显式等待超时 — {exc}')
            return False
        except WebDriverException as exc:
            self._log(f'步骤{index}: WebDriver 异常 — {exc}')
            return False

    def _apply_capture(self, index: int, resp: requests.Response, spec: Any) -> bool:
        if spec is None:
            return True
        if not isinstance(spec, dict):
            self._log(f'步骤{index}: capture 须为 JSON 对象')
            return False
        for var_name, rule in spec.items():
            if not isinstance(rule, dict):
                self._log(f'步骤{index}: capture[{var_name!r}] 须为对象')
                return False
            src = rule.get('from')
            try:
                if src == 'json':
                    path = rule.get('path', '')
                    if not isinstance(path, str):
                        self._log(f'步骤{index}: capture[{var_name!r}] path 须为字符串')
                        return False
                    data = resp.json()
                    val = get_by_path(data, path)
                    self._ctx[var_name] = val
                elif src == 'header':
                    name = rule.get('name')
                    if not name or not isinstance(name, str):
                        self._log(f'步骤{index}: capture[{var_name!r}] 缺少 name')
                        return False
                    val = resp.headers.get(name) or resp.headers.get(name.title())
                    self._ctx[var_name] = val
                elif src == 'text':
                    self._ctx[var_name] = resp.text
                else:
                    self._log(f'步骤{index}: capture[{var_name!r}] 未知 from={src!r}')
                    return False
            except Exception as exc:
                self._log(f'步骤{index}: 捕获变量 {var_name!r} 失败: {exc}')
                return False
            preview = repr(self._ctx[var_name])
            if len(preview) > 160:
                preview = preview[:157] + '...'
            self._log(f'步骤{index}: 捕获 {var_name} = {preview}')
        return True

    def execute(self) -> tuple[str, str, float]:
        start = time.perf_counter()
        overall = TestRecord.Status.SUCCESS
        self._init_context()

        try:
            steps = self.test_case.steps
            if steps is None:
                self._log('错误: steps 为空')
                return TestRecord.Status.FAILED, '\n'.join(self._lines), time.perf_counter() - start

            if not isinstance(steps, list):
                self._log(f'错误: steps 须为 JSON 数组，当前类型为 {type(steps).__name__}')
                return TestRecord.Status.FAILED, '\n'.join(self._lines), time.perf_counter() - start

            if len(steps) == 0:
                self._log('提示: 无步骤，视为成功（未发起任何请求）')
                elapsed = time.perf_counter() - start
                return overall, '\n'.join(self._lines), elapsed

            for idx, raw in enumerate(steps, start=1):
                if not isinstance(raw, dict):
                    self._log(f'步骤{idx}: 非法（非 JSON 对象），标记失败')
                    overall = TestRecord.Status.FAILED
                    continue

                step_type = raw.get('type', 'http')
                if step_type == 'legacy_text':
                    self._log(f'步骤{idx}: [legacy_text] 跳过')
                    continue

                if step_type == 'ui':
                    ok = self._run_ui_step(idx, raw)
                    if not ok:
                        overall = TestRecord.Status.FAILED
                    continue

                if step_type == 'http' or 'url' in raw:
                    ok = self._run_http_step(idx, raw)
                    if not ok:
                        overall = TestRecord.Status.FAILED
                    continue

                self._log(f'步骤{idx}: 未知 type={step_type!r} 且无 url，跳过')
                overall = TestRecord.Status.FAILED

        except Exception:
            self._log(traceback.format_exc())
            overall = TestRecord.Status.FAILED
        finally:
            self._quit_driver()

        elapsed = time.perf_counter() - start
        return overall, '\n'.join(self._lines), elapsed

    def _run_http_step(self, index: int, step: dict[str, Any]) -> bool:
        self._current_step_index = index
        step = self._expand_value(copy.deepcopy(step))

        url = step.get('url')
        method = (step.get('method') or 'GET').upper()
        if not url or not isinstance(url, str):
            self._log(f'步骤{index}: 缺少有效 url')
            return False

        headers = step.get('headers')
        if headers is None:
            headers = {}
        if not isinstance(headers, dict):
            self._log(f'步骤{index}: headers 必须为 JSON 对象')
            return False

        timeout_raw = step.get('timeout', 30)
        try:
            timeout = float(timeout_raw)
        except (TypeError, ValueError):
            self._log(f'步骤{index}: timeout 非法，使用默认 30s')
            timeout = 30.0

        body = step.get('body')
        kwargs: dict[str, Any] = {
            'method': method,
            'url': url,
            'headers': dict(headers),
            'timeout': timeout,
        }
        if body is not None:
            if isinstance(body, (dict, list)):
                kwargs['json'] = body
            elif isinstance(body, str):
                hdrs = kwargs['headers']
                if not any(str(k).lower() == 'content-type' for k in hdrs):
                    hdrs['Content-Type'] = 'text/plain; charset=utf-8'
                kwargs['data'] = body.encode('utf-8')
            else:
                kwargs['data'] = body

        try:
            t0 = time.perf_counter()
            resp = requests.request(**kwargs)
            dt = time.perf_counter() - t0
        except requests.RequestException as exc:
            self._log(f'步骤{index}: 请求异常 {type(exc).__name__}: {exc}')
            return False

        snippet = self._response_snippet(resp)
        self._log(
            f'步骤{index}: {method} {url} -> HTTP {resp.status_code}，'
            f'耗时 {dt:.3f}s，响应摘要:\n{snippet}'
        )

        capture = step.get('capture')
        if capture is not None:
            if not self._apply_capture(index, resp, capture):
                return False

        assert_cfg = step.get('assert')
        if isinstance(assert_cfg, dict) and assert_cfg:
            if 'status_code' not in assert_cfg and resp.status_code >= 400:
                self._log(
                    f'步骤{index}: HTTP {resp.status_code}，未声明 assert.status_code 时默认视为失败'
                )
                return False
            try:
                run_http_assertions(resp, dt, assert_cfg)
            except AssertionErrorDetail as exc:
                self._log(f'步骤{index}: 断言失败 — {exc}')
                return False
            self._log(f'步骤{index}: 断言通过')
        elif resp.status_code >= 400:
            self._log(f'步骤{index}: 状态码 >=400，判定本用例失败')
            return False
        return True

    @staticmethod
    def _response_snippet(resp: requests.Response, limit: int = 2000) -> str:
        text = resp.text or ''
        if len(text) > limit:
            return text[:limit] + f'\n... (截断，共 {len(text)} 字符)'
        return text or '(空响应体)'
