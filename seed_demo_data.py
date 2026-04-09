import os
import shutil
import sys

import django
from django.db import connection
from django.db import transaction

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.append(BACKEND_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model

from api.models import (
    EnvConfig,
    PerfRecord,
    Project,
    ProjectMember,
    SuiteRun,
    TestCase,
    TestCaseVersion,
    TestRecord,
    TestSuite,
)


def _ui(action, *, url="", by="css", selector="", text="", timeout=10):
    return {
        "type": "ui",
        "action": action,
        "url": url,
        "by": by,
        "selector": selector,
        "text": text,
        "timeout": timeout,
    }


def _case(title, tags, steps, *, variables=None, status="active"):
    return {
        "title": title,
        "tags": tags,
        "steps": steps,
        "variables": variables or {},
        "status": status,
    }


def _http(method, url, *, headers=None, body="", capture=None, assertions=None):
    return {
        "type": "http",
        "method": method.upper(),
        "url": url,
        "headers": headers or {},
        "body": body,
        "capture": capture or {},
        "assertions": assertions or [],
    }


def _login_steps(username="{{username}}", password="{{password}}"):
    return [
        _ui("open", url="{{base_url}}"),
        _ui("wait_visible", by="id", selector="user-name"),
        _ui("input", by="id", selector="user-name", text=username),
        _ui("input", by="id", selector="password", text=password),
        _ui("click", by="id", selector="login-button"),
    ]


def build_saucedemo_cases():
    return [
        _case(
            "[UI] SD1-标准用户登录成功",
            ["SauceDemo", "登录", "冒烟"],
            _login_steps()
            + [
                _ui("wait_visible", by="css", selector=".inventory_list"),
            ],
            variables={"username": "standard_user", "password": "secret_sauce"},
        ),
        _case(
            "[UI] SD2-锁定用户登录失败提示",
            ["SauceDemo", "登录", "异常流程"],
            _login_steps(username="locked_out_user", password="secret_sauce")
            + [
                _ui("wait_visible", by="css", selector='h3[data-test="error"]'),
            ],
            variables={"username": "locked_out_user", "password": "secret_sauce"},
        ),
        _case(
            "[UI] SD3-单商品加入购物车",
            ["SauceDemo", "购物车", "核心流程"],
            _login_steps()
            + [
                _ui("wait_visible", by="id", selector="add-to-cart-sauce-labs-backpack"),
                _ui("click", by="id", selector="add-to-cart-sauce-labs-backpack"),
                _ui("wait_visible", by="id", selector="remove-sauce-labs-backpack"),
                _ui("wait_visible", by="css", selector=".shopping_cart_badge"),
            ],
            variables={"username": "standard_user", "password": "secret_sauce"},
        ),
        _case(
            "[UI] SD4-购物车查看与移除商品",
            ["SauceDemo", "购物车", "核心流程"],
            _login_steps()
            + [
                _ui("click", by="id", selector="add-to-cart-sauce-labs-backpack"),
                _ui("click", by="css", selector=".shopping_cart_link"),
                _ui("wait_visible", by="css", selector=".cart_item"),
                _ui("click", by="id", selector="remove-sauce-labs-backpack"),
                _ui("wait_visible", by="css", selector=".cart_list"),
            ],
            variables={"username": "standard_user", "password": "secret_sauce"},
        ),
        _case(
            "[UI] SD5-完整下单流程（Checkout）",
            ["SauceDemo", "下单", "端到端"],
            _login_steps()
            + [
                _ui("click", by="id", selector="add-to-cart-sauce-labs-backpack"),
                _ui("click", by="id", selector="add-to-cart-sauce-labs-bike-light"),
                _ui("click", by="css", selector=".shopping_cart_link"),
                _ui("wait_visible", by="id", selector="checkout"),
                _ui("click", by="id", selector="checkout"),
                _ui("wait_visible", by="id", selector="first-name"),
                _ui("input", by="id", selector="first-name", text="Demo"),
                _ui("input", by="id", selector="last-name", text="Tester"),
                _ui("input", by="id", selector="postal-code", text="100000"),
                _ui("click", by="id", selector="continue"),
                _ui("wait_visible", by="css", selector=".summary_info"),
                _ui("click", by="id", selector="finish"),
                _ui("wait_visible", by="css", selector=".complete-header"),
            ],
            variables={"username": "standard_user", "password": "secret_sauce"},
        ),
        _case(
            "[UI] SD6-登录后退出登录",
            ["SauceDemo", "会话", "回归"],
            _login_steps()
            + [
                _ui("wait_visible", by="id", selector="react-burger-menu-btn"),
                _ui("click", by="id", selector="react-burger-menu-btn"),
                _ui("wait_visible", by="id", selector="logout_sidebar_link"),
                _ui("click", by="id", selector="logout_sidebar_link"),
                _ui("wait_visible", by="id", selector="login-button"),
            ],
            variables={"username": "standard_user", "password": "secret_sauce"},
        ),
    ]


def build_api_perf_cases():
    return [
        _case(
            "[API] AP1-GET 查询参数回显",
            ["API", "HTTP", "冒烟", "压测可用"],
            [
                _http(
                    "GET",
                    "/get?source=perf_demo&sku={{sku}}",
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "operator": "eq", "path": "args.sku", "expected": "{{sku}}"},
                    ],
                )
            ],
            variables={"sku": "sku_1001"},
        ),
        _case(
            "[API] AP2-POST JSON 回显校验",
            ["API", "HTTP", "核心流程", "压测可用"],
            [
                _http(
                    "POST",
                    "/post",
                    headers={"Content-Type": "application/json"},
                    body={"order_id": "{{order_id}}", "amount": 199, "currency": "CNY"},
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "operator": "eq", "path": "json.order_id", "expected": "{{order_id}}"},
                        {"source": "json", "operator": "eq", "path": "json.amount", "expected": "199"},
                    ],
                )
            ],
            variables={"order_id": "ORDER_20260405_001"},
        ),
        _case(
            "[API] AP3-变量提取并透传 Header",
            ["API", "HTTP", "变量提取", "链路"],
            [
                _http(
                    "GET",
                    "/get?token={{token_seed}}",
                    capture={"access_token": {"from": "json", "path": "args.token"}},
                    assertions=[{"source": "status_code", "operator": "eq", "expected": "200"}],
                ),
                _http(
                    "GET",
                    "/get",
                    headers={"x-access-token": "{{access_token}}"},
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "operator": "eq", "path": "headers.x-access-token", "expected": "{{token_seed}}"},
                    ],
                ),
            ],
            variables={"token_seed": "DEMO_TOKEN_10086"},
        ),
        _case(
            "[API] AP4-PUT 更新资源模拟",
            ["API", "HTTP", "CRUD", "压测可用"],
            [
                _http(
                    "PUT",
                    "/put",
                    headers={"Content-Type": "application/json"},
                    body={"id": 101, "status": "paid"},
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "operator": "eq", "path": "json.status", "expected": "paid"},
                    ],
                )
            ],
        ),
        _case(
            "[API] AP5-DELETE 删除资源模拟",
            ["API", "HTTP", "CRUD", "压测可用"],
            [
                _http(
                    "DELETE",
                    "/delete",
                    assertions=[{"source": "status_code", "operator": "eq", "expected": "200"}],
                )
            ],
        ),
        _case(
            "[API] AP6-响应头断言",
            ["API", "HTTP", "断言", "冒烟"],
            [
                _http(
                    "GET",
                    "/response-headers?x-demo=ok",
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "header", "operator": "eq", "path": "x-demo", "expected": "ok"},
                    ],
                )
            ],
        ),
        _case(
            "[API] AP7-压测基线 GET",
            ["API", "HTTP", "压测", "基线"],
            [
                _http(
                    "GET",
                    "/get?load={{load_tag}}",
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "operator": "contains", "path": "args.load", "expected": "perf"},
                    ],
                )
            ],
            variables={"load_tag": "perf_baseline"},
        ),
        _case(
            "[API] AP8-下单风格链路（创建-查询）",
            ["API", "HTTP", "链路", "回归"],
            [
                _http(
                    "POST",
                    "/post",
                    headers={"Content-Type": "application/json"},
                    body={"order_no": "{{order_no}}", "items": 2, "amount": 399},
                    capture={"created_order_no": {"from": "json", "path": "json.order_no"}},
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "operator": "eq", "path": "json.order_no", "expected": "{{order_no}}"},
                    ],
                ),
                _http(
                    "GET",
                    "/get?order_no={{created_order_no}}",
                    assertions=[
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "operator": "eq", "path": "args.order_no", "expected": "{{order_no}}"},
                    ],
                ),
            ],
            variables={"order_no": "TRADE_20260405_9001"},
        ),
    ]


def reset_primary_key_sequences():
    """
    在清空测试业务表后重置自增主键序列。
    仅用于演示环境，避免删除重建后 ID 继续累加。
    """
    table_names = [
        "api_projectmember",
        "api_envconfig",
        "api_testcaseversion",
        "api_testrecord",
        "api_suiterun",
        "api_perfrecord",
        "api_testsuite",
        "api_testcase",
        "api_project",
    ]
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            placeholders = ",".join(["%s"] * len(table_names))
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", table_names)
        elif connection.vendor == "postgresql":
            for table in table_names:
                cursor.execute(f'ALTER SEQUENCE "{table}_id_seq" RESTART WITH 1')


@transaction.atomic
def reset_and_seed():
    print("开始重建数据：清空旧项目/用例/套件，切换到 SauceDemo 场景...")

    demo_username = os.getenv("DEMO_USERNAME") or "demo"
    demo_password = os.getenv("DEMO_PASSWORD") or "Demo123456"
    viewer_username = os.getenv("VIEWER_USERNAME") or "viewer"
    viewer_password = os.getenv("VIEWER_PASSWORD") or "Viewer123456"

    User = get_user_model()
    demo_user, _ = User.objects.get_or_create(username=demo_username)
    demo_user.is_staff = True
    demo_user.is_superuser = False
    demo_user.is_active = True
    demo_user.set_password(demo_password)
    demo_user.save()

    viewer_user, _ = User.objects.get_or_create(username=viewer_username)
    viewer_user.is_staff = False
    viewer_user.is_superuser = False
    viewer_user.is_active = True
    viewer_user.set_password(viewer_password)
    viewer_user.save()

    ProjectMember.objects.all().delete()
    Project.objects.all().delete()
    TestRecord.objects.filter(case__isnull=True).delete()
    SuiteRun.objects.filter(suite__isnull=True).delete()
    PerfRecord.objects.filter(case__isnull=True).delete()
    TestCaseVersion.objects.filter(case__isnull=True).delete()
    reset_primary_key_sequences()
    print("已清空历史项目、成员授权及关联测试数据")

    project = Project.objects.create(
        owner=demo_user,
        name="Demo-SauceDemo-Ecommerce",
        description="基于 SauceDemo 的真实电商 UI 测试集：登录、加购、购物车、结算、退出。",
    )

    env = EnvConfig.objects.create(
        project=project,
        name="SauceDemo 公网环境",
        base_url="https://www.saucedemo.com",
        variables={"base_url": "https://www.saucedemo.com"},
        db_config={},
        is_default=True,
    )

    ProjectMember.objects.create(project=project, user=viewer_user, is_active=True)

    cases = []
    ui_cases = []
    for item in build_saucedemo_cases():
        case = TestCase.objects.create(
            project=project,
            title=item["title"],
            tags=item["tags"],
            status=item["status"],
            variables=item["variables"],
            steps=item["steps"],
        )
        TestCaseVersion.objects.create(
            case=case,
            version=1,
            snapshot={
                "project": case.project_id,
                "title": case.title,
                "steps": case.steps,
                "variables": case.variables,
                "tags": case.tags,
                "setup_sql": case.setup_sql,
                "teardown_sql": case.teardown_sql,
                "status": case.status,
                "updated_at": str(case.updated_at),
            },
            created_by=demo_user,
        )
        cases.append(case)
        ui_cases.append(case)
        print(f"  + 用例: {case.title}")

    smoke_ids = [c.id for c in cases if c.title.startswith("[UI] SD1") or c.title.startswith("[UI] SD3")]
    e2e_ids = [c.id for c in cases if c.title.startswith("[UI] SD1") or c.title.startswith("[UI] SD5")]
    regression_ids = [c.id for c in cases]
    negative_ids = [c.id for c in cases if c.title.startswith("[UI] SD2")]

    TestSuite.objects.create(
        project=project,
        name="SauceDemo-冒烟套件",
        description="登录成功 + 单商品加购。",
        variables={},
        ordered_case_ids=smoke_ids,
    )
    TestSuite.objects.create(
        project=project,
        name="SauceDemo-交易链路套件",
        description="登录 -> 加购 -> Checkout 完整业务链路。",
        variables={},
        ordered_case_ids=e2e_ids,
    )
    TestSuite.objects.create(
        project=project,
        name="SauceDemo-异常流程套件",
        description="锁定用户登录失败校验。",
        variables={},
        ordered_case_ids=negative_ids,
    )
    TestSuite.objects.create(
        project=project,
        name="SauceDemo-回归套件",
        description="覆盖登录、加购、购物车、结算、退出。",
        variables={},
        ordered_case_ids=regression_ids,
    )

    api_project = Project.objects.create(
        owner=demo_user,
        name="Demo-HTTP-API-Perf",
        description="用于接口自动化与压测演示的 HTTP 用例集，包含断言、变量提取和链路流程。",
    )
    api_env = EnvConfig.objects.create(
        project=api_project,
        name="Postman Echo 公网环境",
        base_url="https://postman-echo.com",
        variables={"base_url": "https://postman-echo.com"},
        db_config={},
        is_default=True,
    )
    ProjectMember.objects.create(project=api_project, user=viewer_user, is_active=True)

    api_cases = []
    for item in build_api_perf_cases():
        case = TestCase.objects.create(
            project=api_project,
            title=item["title"],
            tags=item["tags"],
            status=item["status"],
            variables=item["variables"],
            steps=item["steps"],
        )
        TestCaseVersion.objects.create(
            case=case,
            version=1,
            snapshot={
                "project": case.project_id,
                "title": case.title,
                "steps": case.steps,
                "variables": case.variables,
                "tags": case.tags,
                "setup_sql": case.setup_sql,
                "teardown_sql": case.teardown_sql,
                "status": case.status,
                "updated_at": str(case.updated_at),
            },
            created_by=demo_user,
        )
        cases.append(case)
        api_cases.append(case)
        print(f"  + 用例: {case.title}")

    api_smoke_ids = [c.id for c in api_cases if c.title.startswith("[API] AP1") or c.title.startswith("[API] AP2")]
    api_chain_ids = [c.id for c in api_cases if c.title.startswith("[API] AP3") or c.title.startswith("[API] AP8")]
    api_perf_ids = [c.id for c in api_cases if c.title.startswith("[API] AP1") or c.title.startswith("[API] AP7")]
    api_regression_ids = [c.id for c in api_cases]

    TestSuite.objects.create(
        project=api_project,
        name="HTTP-API-冒烟套件",
        description="GET/POST 接口可用性与核心断言。",
        variables={},
        ordered_case_ids=api_smoke_ids,
    )
    TestSuite.objects.create(
        project=api_project,
        name="HTTP-API-链路套件",
        description="变量提取与创建-查询业务链路。",
        variables={},
        ordered_case_ids=api_chain_ids,
    )
    TestSuite.objects.create(
        project=api_project,
        name="HTTP-API-压测套件",
        description="压测前基线接口：可直接用于 Locust 压测入口。",
        variables={},
        ordered_case_ids=api_perf_ids,
    )
    TestSuite.objects.create(
        project=api_project,
        name="HTTP-API-回归套件",
        description="覆盖 GET/POST/PUT/DELETE、变量提取、响应头断言。",
        variables={},
        ordered_case_ids=api_regression_ids,
    )

    perf_dir = os.path.join(BACKEND_DIR, "media", "perf")
    if os.path.isdir(perf_dir):
        shutil.rmtree(perf_dir, ignore_errors=True)
    os.makedirs(perf_dir, exist_ok=True)

    print("\n重建完成：")
    print(f"- 管理员账号：{demo_username} / {demo_password}")
    print(f"- 普通用户账号：{viewer_username} / {viewer_password}")
    print(f"- 项目1：{project.name}")
    print(f"- 环境1：{env.name} ({env.base_url})")
    print(f"- 项目2：{api_project.name}")
    print(f"- 环境2：{api_env.name} ({api_env.base_url})")
    print(f"- 用例总数：{len(cases)}（UI: {len(ui_cases)}，HTTP: {len(api_cases)}）")
    print("- 套件总数：8（UI 4 + HTTP 4）")


if __name__ == "__main__":
    reset_and_seed()
