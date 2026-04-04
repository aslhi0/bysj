import os
import django
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')

sys.path.append(BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import Project, EnvConfig, TestCase, TestSuite, TestCaseVersion
from api.crypto_utils import encrypt_json, decrypt_json, is_encrypted, ENC_PREFIX

def seed():
    print("开始初始化演示数据...")

    username = os.getenv('DEMO_USERNAME') or 'demo'
    password = os.getenv('DEMO_PASSWORD') or 'Demo123456'
    User = get_user_model()
    user, u_created = User.objects.get_or_create(username=username)
    if u_created:
        user.set_password(password)
        user.save(update_fields=['password'])
        print(f"已创建演示用户: {username} / {password}")
    else:
        print(f"演示用户已存在: {username}")

    project, p_created = Project.objects.get_or_create(
        owner=user,
        name="Demo-HTTPBin",
        defaults={"description": "使用 httpbin.org 演示接口自动化/变量提取/断言/报告/压测/版本回滚"}
    )
    if p_created:
        print(f"已创建项目: {project.name}")
    else:
        if project.owner_id != user.id:
            project.owner = user
            project.save(update_fields=['owner'])
        print(f"项目已存在: {project.name}")

    def ensure_encrypted_dict(d):
        if not isinstance(d, dict):
            return {}
        out = dict(d)
        for k, v in list(out.items()):
            if isinstance(v, str) and v.startswith(ENC_PREFIX):
                continue
            lk = str(k).lower()
            if lk in {'token', 'password', 'secret', 'api_key', 'authorization', 'client_secret', 'access_token', 'refresh_token'}:
                out = encrypt_json(out)
                break
        return out

    env, e_created = EnvConfig.objects.get_or_create(
        project=project,
        name="公网演示环境",
        defaults={
            "base_url": "https://httpbin.org",
            "variables": encrypt_json({"token": "demo-secret-token", "tenant": "demo"}),
            "db_config": encrypt_json({"password": "p@ssw0rd", "sqlite_path": "db.sqlite3"}),
            "is_default": True
        }
    )
    if not e_created:
        updated = False
        if env.base_url != "https://httpbin.org":
            env.base_url = "https://httpbin.org"
            updated = True
        if isinstance(env.variables, dict):
            new_vars = ensure_encrypted_dict(env.variables)
            if new_vars != env.variables:
                env.variables = new_vars
                updated = True
        else:
            env.variables = encrypt_json({"token": "demo-secret-token", "tenant": "demo"})
            updated = True
        if isinstance(env.db_config, dict):
            new_db = ensure_encrypted_dict(env.db_config)
            if new_db != env.db_config:
                env.db_config = new_db
                updated = True
        else:
            env.db_config = encrypt_json({"password": "p@ssw0rd", "sqlite_path": "db.sqlite3"})
            updated = True
        if not env.is_default:
            env.is_default = True
            updated = True
        if updated:
            env.save()
        print(f"环境已存在: {env.name}")
    else:
        print(f"已创建环境: {env.name}")

    case_api, c_created = TestCase.objects.get_or_create(
        project=project,
        title="A1-获取UUID并回传校验",
        defaults={
            "status": "active",
            "variables": {},
            "steps": [
                {
                    "type": "http",
                    "method": "GET",
                    "url": "{{base_url}}/uuid",
                    "headers": {},
                    "body": "",
                    "capture": {"uid": {"from": "json", "path": "uuid"}},
                    "assertions": [
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "path": "uuid", "operator": "contains", "expected": "-"},
                    ]
                },
                {
                    "type": "http",
                    "method": "GET",
                    "url": "{{base_url}}/get?uid={{uid}}",
                    "headers": {},
                    "body": "",
                    "capture": {},
                    "assertions": [
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "path": "args.uid", "operator": "eq", "expected": "{{uid}}"},
                    ]
                }
            ]
        }
    )
    if c_created:
        print(f"已创建用例: {case_api.title}")
    else:
        print(f"用例已存在: {case_api.title}")

    if not TestCaseVersion.objects.filter(case=case_api).exists():
        v1 = 1
        TestCaseVersion.objects.create(
            case=case_api,
            version=v1,
            snapshot={
                "project": case_api.project_id,
                "title": case_api.title,
                "steps": case_api.steps,
                "variables": case_api.variables,
                "tags": case_api.tags,
                "setup_sql": case_api.setup_sql,
                "teardown_sql": case_api.teardown_sql,
                "status": case_api.status,
                "updated_at": str(case_api.updated_at),
            },
            created_by=user,
        )
        case_api.title = "A1-获取UUID并回传校验（示例：已更新，可回滚）"
        case_api.save(update_fields=['title'])
        TestCaseVersion.objects.create(
            case=case_api,
            version=v1 + 1,
            snapshot={
                "project": case_api.project_id,
                "title": case_api.title,
                "steps": case_api.steps,
                "variables": case_api.variables,
                "tags": case_api.tags,
                "setup_sql": case_api.setup_sql,
                "teardown_sql": case_api.teardown_sql,
                "status": case_api.status,
                "updated_at": str(case_api.updated_at),
            },
            created_by=user,
        )
        print("已生成用例版本 v1/v2（可用于前端演示回滚）")

    case_ui, ui_created = TestCase.objects.get_or_create(
        project=project,
        title="U1-UI演示（可选：失败截图）",
        defaults={
            "status": "draft",
            "steps": [
                {
                    "type": "ui",
                    "action": "open",
                    "url": "https://example.com",
                    "timeout": 15,
                    "headless": True
                },
                {
                    "type": "ui",
                    "action": "click",
                    "by": "css",
                    "selector": "a",
                    "timeout": 10,
                    "headless": True
                },
                {
                    "type": "ui",
                    "action": "sleep",
                    "seconds": 1
                },
                {
                    "type": "ui",
                    "action": "click",
                    "by": "css",
                    "selector": "#non-exist-button-for-demo",
                    "timeout": 5,
                    "headless": True
                }
            ]
        }
    )
    if ui_created:
        print(f"已创建用例: {case_ui.title}（默认草稿，可手动启用）")

    suite, s_created = TestSuite.objects.get_or_create(
        project=project,
        name="Demo-冒烟套件",
        defaults={
            "description": "包含 A1 用例，演示套件批量执行、历史与汇总",
            "variables": {},
            "ordered_case_ids": [case_api.id],
        }
    )
    if not s_created:
        ids = suite.ordered_case_ids or []
        if case_api.id not in ids:
            suite.ordered_case_ids = [case_api.id] + ids
            suite.save(update_fields=['ordered_case_ids'])
    print(f"套件已就绪: {suite.name}")

    masked_vars = decrypt_json(env.variables) if isinstance(env.variables, dict) else {}
    print("\n数据初始化完成！")
    print(f"- 登录账号：{username} / {password}")
    print(f"- 项目：{project.name}")
    print(f"- 默认环境：{env.name} base_url={env.base_url}")
    if masked_vars.get('token'):
        print("- 环境 variables.token 已加密存储，接口返回将显示为 ******")

if __name__ == "__main__":
    seed()
