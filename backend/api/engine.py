from __future__ import annotations

import time
import requests
import json
import sqlite3
import os
import re
import ipaddress
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urljoin
from jsonschema import validate
from faker import Faker
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 预编译变量渲染正则：同时匹配 {{var}} / {{ var }} / [[var]] / [[ var ]]
_VAR_RE = re.compile(r'\{\{[ ]?(\w+)[ ]?\}\}|\[\[[ ]?(\w+)[ ]?\]\]')
# 预编译 Faker 占位符：{{faker.method}} / [[faker.method]]
_FAKER_RE = re.compile(r'(\{\{|\[\[)faker\.(\w+)(\}\}|\]\])')

def validate_outbound_http_url(url, *, allowed_hosts=None):
    if not isinstance(url, str) or not url.strip():
        raise ValueError('url 不能为空')
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('仅允许 http/https')
    if parsed.username or parsed.password:
        raise ValueError('不允许 URL 携带用户名密码')
    host = (parsed.hostname or '').strip().lower()
    if not host:
        raise ValueError('url 缺少 host')
    if host == 'localhost':
        raise ValueError('禁止访问 localhost')
    if allowed_hosts:
        allowed = {str(h).strip().lower() for h in allowed_hosts if h}
        if host not in allowed:
            raise ValueError('目标 host 不在允许列表内')
        return
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception:
        raise ValueError('解析 host 失败')
    ips = []
    for info in infos:
        try:
            ips.append(info[4][0])
        except Exception:
            continue
    for ip_s in set(ips):
        try:
            ip = ipaddress.ip_address(ip_s)
        except Exception:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError('禁止访问内网/本机/特殊网段地址')

class TestEngine:
    __test__ = False

    def __init__(
        self,
        variables: Optional[Dict[str, Any]] = None,
        db_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.variables = variables or {}
        if isinstance(self.variables, dict):
            if 'base_url' in self.variables and 'base' not in self.variables:
                self.variables['base'] = self.variables.get('base_url')
            if 'base' in self.variables and 'base_url' not in self.variables:
                self.variables['base_url'] = self.variables.get('base')
        self.db_config = db_config or {}
        self.log = []
        self.step_results = []
        self.driver = None
        self.last_screenshot = None
        self.faker = Faker('zh_CN')

    def render_data(self, data):
        if isinstance(data, str):
            return self.render_string(data)
        if isinstance(data, list):
            return [self.render_data(v) for v in data]
        if isinstance(data, dict):
            return {k: self.render_data(v) for k, v in data.items()}
        return data

    def parse_jsonish(self, value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return self.render_data(value)
        if isinstance(value, str):
            s = self.render_string(value).strip()
            if not s:
                return default
            try:
                parsed = json.loads(s)
                return self.render_data(parsed)
            except Exception:
                return default
        return default

    def get_by_path(self, obj, path, max_depth=20):
        if obj is None:
            return None
        if not path:
            return obj
        parts = str(path).split('.')
        if len(parts) > int(max_depth):
            raise ValueError('path 深度过大')
        cur = obj
        for part in parts:
            if cur is None:
                return None
            if isinstance(cur, dict):
                cur = cur.get(part)
                continue
            if isinstance(cur, list):
                if part.isdigit():
                    idx = int(part)
                    if 0 <= idx < len(cur):
                        cur = cur[idx]
                    else:
                        return None
                    continue
                return None
            return None
        return cur

    def add_log(self, message):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def take_screenshot(self):
        if self.driver:
            try:
                self.last_screenshot = self.driver.get_screenshot_as_png()
                self.add_log("截图已捕获")
            except Exception as e:
                self.add_log(f"截图失败: {str(e)}")

    def render_string(self, text: Any) -> Any:
        """将 {{var}} / [[var]] 及 {{faker.method}} 占位符替换为变量或随机值。

        使用预编译正则一次性扫描字符串，O(n) 而非 O(n×m)。
        Faker 方法动态调用，支持 faker 库中所有可用属性/方法。
        """
        if not isinstance(text, str):
            return text

        # 先替换 faker 占位符（避免变量名恰好为 'faker.xxx' 时误替换）
        if 'faker.' in text:
            def _faker_sub(m: re.Match) -> str:
                method = m.group(2)
                # id_card 是平台约定的别名，映射到 faker.ssn()
                if method == 'id_card':
                    method = 'ssn'
                attr = getattr(self.faker, method, None)
                if attr is None:
                    return m.group(0)
                try:
                    return str(attr() if callable(attr) else attr)
                except Exception:
                    return m.group(0)
            text = _FAKER_RE.sub(_faker_sub, text)

        # 再替换普通变量
        if self.variables:
            def _var_sub(m: re.Match) -> str:
                key = m.group(1) or m.group(2)
                if key in self.variables:
                    return str(self.variables[key])
                return m.group(0)
            text = _VAR_RE.sub(_var_sub, text)

        return text

    def run_step(self, step: Dict[str, Any]) -> bool:
        """按步骤 type 分发到 HTTP / UI 等执行器并记录步骤结果。"""
        step_type = step.get('type')
        start_time = time.time()
        success = False
        
        if step_type == 'http':
            success = self.run_http(step)
        elif step_type == 'ui':
            success = self.run_ui(step)
        else:
            self.add_log(f"未知步骤类型: {step_type}")
        
        elapsed = time.time() - start_time
        self.step_results.append({
            'type': step_type,
            'name': f"{step_type.upper()} 步骤",
            'status': 'success' if success else 'failed',
            'elapsed': f"{elapsed:.2f}",
            'log': self.log[-3:] # 获取最后几行日志
        })
        return success

    def run_http(self, step):
        method = step.get('method', 'GET').upper()
        raw_url = self.render_string(step.get('url', ''))
        base_url = self.variables.get('base_url') or self.variables.get('base')
        url = raw_url
        if isinstance(raw_url, str) and isinstance(base_url, str) and base_url.strip():
            if raw_url.startswith('/'):
                url = base_url.rstrip('/') + raw_url
            elif '://' not in raw_url:
                url = urljoin(base_url.rstrip('/') + '/', raw_url.lstrip('/'))
        headers = self.parse_jsonish(step.get('headers', {}), default={})
        if not isinstance(headers, dict):
            headers = {}
        body = self.render_data(step.get('body', ''))
        
        self.add_log(f"HTTP {method} {url}")
        try:
            allowed_host = None
            if isinstance(base_url, str) and base_url.strip():
                try:
                    allowed_host = urlparse(base_url).hostname
                except Exception:
                    allowed_host = None
            if isinstance(url, str) and (url.startswith('http://') or url.startswith('https://')):
                validate_outbound_http_url(url, allowed_hosts=[allowed_host] if allowed_host else None)
            start_time = time.time()
            req_kwargs = {'headers': headers, 'timeout': 30, 'allow_redirects': False}
            if isinstance(body, (dict, list)):
                req_kwargs['json'] = body
            else:
                req_kwargs['data'] = body
            response = requests.request(method, url, **req_kwargs)
            elapsed = time.time() - start_time
            self.add_log(f"响应码: {response.status_code}, 耗时: {elapsed:.2f}s")
            
            # Multi-dimensional Assertions
            success = response.status_code < 400
            assertions = step.get('assertions', [])
            if assertions:
                for ass in assertions:
                    if not self.run_assertion(response, ass):
                        success = False
            
            # Capture variables
            capture = self.parse_jsonish(step.get('capture', {}), default={})
            if isinstance(capture, dict) and capture and response.status_code < 400:
                try:
                    resp_json = response.json()
                    for var_name, config in capture.items():
                        if config.get('from') == 'json':
                            path = config.get('path')
                            val = self.get_by_path(resp_json, path)
                            self.variables[var_name] = val
                            self.add_log(f"提取变量: {var_name} = {val}")
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
                    self.add_log(f"变量提取失败: {str(e)}")
            
            return success
        except requests.Timeout:
            self.add_log("请求异常: Timeout")
            return False
        except requests.ConnectionError:
            self.add_log("请求异常: ConnectionError")
            return False
        except requests.RequestException as e:
            self.add_log(f"请求异常: {str(e)}")
            return False
        except Exception as e:
            self.add_log(f"请求异常: {str(e)}")
            return False

    def run_assertion(self, response, ass):
        source = ass.get('source') # status_code, json, header, database, schema
        operator = ass.get('operator') # eq, contains, gt, lt, validate
        expected = self.render_string(ass.get('expected'))
        actual = None
        
        try:
            if source == 'status_code':
                actual = str(response.status_code)
            elif source == 'json':
                path = ass.get('path')
                resp_json = response.json()
                actual = self.get_by_path(resp_json, path)
                actual = str(actual)
            elif source == 'header':
                actual = response.headers.get(ass.get('path'))
            elif source == 'database':
                actual = self.run_db_query(ass.get('path')) # path here is SQL
            elif source == 'schema':
                # JSON Schema 校验
                schema = json.loads(expected)
                validate(instance=response.json(), schema=schema)
                self.add_log(f"断言 [JSON Schema]: 校验通过")
                return True
            
            res = False
            if operator == 'eq':
                res = str(actual) == str(expected)
            elif operator == 'contains':
                res = str(expected) in str(actual)
            elif operator == 'gt':
                try:
                    res = float(actual) > float(expected)
                except (ValueError, TypeError):
                    self.add_log(f"断言异常: 无法将 {actual} 转换为数字")
                    res = False
            elif operator == 'lt':
                try:
                    res = float(actual) < float(expected)
                except (ValueError, TypeError):
                    self.add_log(f"断言异常: 无法将 {actual} 转换为数字")
                    res = False
            
            self.add_log(f"断言 [{source} {operator} {expected}]: {'通过' if res else '失败'} (实际值: {actual})")
            return res
        except Exception as e:
            self.add_log(f"断言异常: {str(e)}")
            return False

    def run_db_query(self, sql, execute=False):
        sql = self.render_string(sql)
        self.add_log(f"执行数据库{'命令' if execute else '查询'}: {sql}")
        try:
            raw = (sql or '').strip()
            if not raw:
                raise ValueError('SQL 不能为空')
            if len(raw) > 20000:
                raise ValueError('SQL 过长')
            if ';' in raw.rstrip(';'):
                raise ValueError('禁止多语句 SQL')
            danger = re.compile(r"\b(attach|detach|pragma|vacuum|reindex|load_extension|readfile|writefile)\b", re.I)
            if danger.search(raw):
                raise ValueError('SQL 包含危险关键字')
            if execute:
                if not re.match(r'^\s*(insert|update|delete)\b', raw, re.I):
                    raise ValueError('execute 模式仅允许 INSERT/UPDATE/DELETE')
            else:
                if not re.match(r'^\s*select\b', raw, re.I):
                    raise ValueError('查询模式仅允许 SELECT')

            from django.conf import settings
            base_dir = str(getattr(settings, 'BASE_DIR', os.getcwd()))
            db_name = None
            if isinstance(self.db_config, dict):
                for k in ['sqlite_path', 'path', 'NAME', 'name', 'db', 'database']:
                    v = self.db_config.get(k)
                    if v:
                        db_name = v
                        break
            if not db_name:
                db_name = settings.DATABASES.get('default', {}).get('NAME', 'db.sqlite3')
            db_name = str(db_name)
            if os.path.isabs(db_name):
                raise ValueError('禁止使用绝对 sqlite_path')
            abs_db = os.path.normpath(os.path.join(base_dir, os.path.normpath(db_name)))
            base_norm = os.path.normpath(base_dir)
            if not abs_db.startswith(base_norm + os.sep) and abs_db != base_norm:
                raise ValueError('sqlite_path 越界')
            conn = sqlite3.connect(abs_db)
            cursor = conn.cursor()
            if execute:
                cursor.execute(raw)
                conn.commit()
                res = "Executed"
            else:
                cursor.execute(raw)
                res = cursor.fetchone()
            conn.close()
            return str(res[0]) if res and not execute else str(res)
        except Exception as e:
            self.add_log(f"数据库操作异常: {str(e)}")
            return "Error"

    def run_setup(self, sql):
        if sql:
            self.add_log("--- 执行前置数据准备 ---")
            self.run_db_query(sql, execute=True)

    def run_teardown(self, sql):
        if sql:
            self.add_log("--- 执行后置数据清理 ---")
            self.run_db_query(sql, execute=True)

    def run_ui(self, step):
        action = step.get('action')
        url = self.render_string(step.get('url', ''))
        selector = self.render_string(step.get('selector', ''))
        text = self.render_string(step.get('text', ''))
        timeout = int(step.get('timeout', 10))

        if not self.driver:
            self.add_log("初始化浏览器 (Headless模式)...")
            browser_cfg = step.get('browser') if isinstance(step.get('browser'), dict) else {}
            headless = browser_cfg.get('headless')
            if headless is None:
                headless = step.get('headless')
            if headless is None:
                headless = True
            options = webdriver.ChromeOptions()
            if headless:
                options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            try:
                options.set_capability('pageLoadStrategy', 'eager')
            except Exception:
                pass
            win_size = browser_cfg.get('window_size') or browser_cfg.get('windowSize') or step.get('window_size')
            if isinstance(win_size, str) and win_size.strip():
                options.add_argument(f'--window-size={win_size.strip()}')
            self.driver = webdriver.Chrome(options=options)
            try:
                self.driver.set_page_load_timeout(30)
                self.driver.set_script_timeout(30)
            except Exception:
                pass

        self.add_log(f"UI 动作: {action} {url or selector or ''}")
        try:
            by_raw = step.get('by') or 'css'
            by_key = str(by_raw).strip().lower()
            by_map = {
                'css': By.CSS_SELECTOR,
                'css_selector': By.CSS_SELECTOR,
                'xpath': By.XPATH,
                'id': By.ID,
                'name': By.NAME,
                'class': By.CLASS_NAME,
                'class_name': By.CLASS_NAME,
                'tag': By.TAG_NAME,
                'tag_name': By.TAG_NAME,
                'link_text': By.LINK_TEXT,
                'partial_link_text': By.PARTIAL_LINK_TEXT,
            }
            by = by_map.get(by_key, By.CSS_SELECTOR)
            if action == 'open':
                if isinstance(url, str) and (url.startswith('http://') or url.startswith('https://')):
                    validate_outbound_http_url(url)
                self.driver.get(url)
            elif action == 'click':
                el = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((by, selector))
                )
                el.click()
            elif action == 'input':
                el = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, selector))
                )
                el.clear()
                el.send_keys(text)
            elif action == 'wait_visible':
                WebDriverWait(self.driver, timeout).until(
                    EC.visibility_of_element_located((by, selector))
                )
            elif action == 'sleep':
                seconds = step.get('seconds')
                if seconds is None:
                    seconds = url or 1
                time.sleep(float(seconds))
            
            return True
        except Exception as e:
            self.add_log(f"UI 异常: {str(e)}")
            self.take_screenshot()
            return False

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_full_log(self):
        return "\n".join(self.log)
