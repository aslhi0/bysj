#!/usr/bin/env python
"""
自动化执行相关环境自检（Selenium 浏览器驱动、Locust）。
用法（在 backend 目录或项目根目录均可）:
  python check_env.py
  python check_env.py --smoke   # 尝试启动一次无头 Chrome（较慢，需本机已装 Chrome）
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_locust() -> bool:
    if not _has_module('locust'):
        print('[FAIL] 未安装 locust（pip install locust）')
        return False
    import locust

    print(f'[OK] locust 已安装，版本 {locust.__version__}')
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'locust', '--version'],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            print(f'[OK] locust CLI: {r.stdout.strip() or r.stderr.strip()}')
        else:
            print(f'[WARN] locust --version 退出码 {r.returncode}')
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f'[WARN] 无法执行 locust CLI: {e}')
    return True


def check_selenium() -> bool:
    if not _has_module('selenium'):
        print('[FAIL] 未安装 selenium（pip install selenium）')
        return False
    import selenium

    print(f'[OK] selenium 已安装，版本 {selenium.__version__}')
    return True


def check_drivers_in_path() -> None:
    for label, names in (
        ('Chrome chromedriver', ('chromedriver', 'chromedriver.exe')),
        ('Edge msedgedriver', ('msedgedriver', 'msedgedriver.exe')),
    ):
        found = None
        for n in names:
            p = shutil.which(n)
            if p:
                found = p
                break
        if found:
            print(f'[OK] {label} 在 PATH 中: {found}')
        else:
            print(
                f'[INFO] 未在 PATH 中发现 {label}；Selenium 4.6+ 通常可通过 Selenium Manager 自动下载匹配驱动'
            )


def smoke_chrome() -> None:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    print('[INFO] 尝试启动无头 Chrome（首次可能下载驱动，需数十秒）…')
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get('about:blank')
        print('[OK] Chrome WebDriver 可正常启动')
    finally:
        driver.quit()


def main() -> int:
    parser = argparse.ArgumentParser(description='自动化测试环境检查')
    parser.add_argument(
        '--smoke',
        action='store_true',
        help='尝试启动一次无头 Chrome（可选，较慢）',
    )
    args = parser.parse_args()

    ok = True
    ok = check_locust() and ok
    ok = check_selenium() and ok
    if ok:
        check_drivers_in_path()
    if args.smoke and ok:
        try:
            smoke_chrome()
        except Exception as e:
            print(f'[FAIL] Chrome 冒烟失败: {e}')
            ok = False

    if ok:
        print('\n结论: Python 侧依赖就绪；若冒烟失败请检查本机是否安装 Chrome 或网络是否可拉取驱动。')
        return 0
    print('\n结论: 请先安装缺失依赖后再开发执行引擎。')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
