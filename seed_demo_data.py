import os
import django
import sys

# 获取项目根目录 (d:\test)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')

# 将 backend 目录加入 python 路径，这样可以找到 core.settings 和 api 模块
sys.path.append(BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Project, EnvConfig, TestCase

def seed():
    print("开始初始化方案一演示数据...")

    # 1. 创建项目
    project, created = Project.objects.get_or_create(
        name="毕设演示项目 (方案一)",
        defaults={"description": "使用 HTTPBin 和 百度 进行全链路自动化测试演示"}
    )
    if created: print(f"已创建项目: {project.name}")

    # 2. 创建环境
    env, created = EnvConfig.objects.get_or_create(
        project=project,
        name="线上生产环境",
        defaults={
            "base_url": "https://httpbin.org",
            "variables": {"global_token": "demo_token_123"},
            "is_default": True
        }
    )
    if created: print(f"已创建环境: {env.name}")

    # 3. 创建接口用例
    case_api, created = TestCase.objects.get_or_create(
        project=project,
        title="API 接口全链路演示 (变量提取+多重断言)",
        defaults={
            "status": "active",
            "variables": {},
            "steps": [
                {
                    "type": "http",
                    "method": "GET",
                    "url": "{{base_url}}/uuid",
                    "headers": "{}",
                    "body": "",
                    "capture": '{"sys_uuid": {"from": "json", "path": "uuid"}}',
                    "assertions": []
                },
                {
                    "type": "http",
                    "method": "POST",
                    "url": "{{base_url}}/post",
                    "headers": '{"Content-Type": "application/json"}',
                    "body": '{"id": "{{sys_uuid}}", "user": "{{faker.name}}", "env": "prod"}',
                    "capture": "{}",
                    "assertions": [
                        {"source": "status_code", "operator": "eq", "expected": "200"},
                        {"source": "json", "path": "json.id", "operator": "eq", "expected": "{{sys_uuid}}"},
                        {"source": "header", "path": "Content-Type", "operator": "contains", "expected": "application/json"}
                    ]
                }
            ]
        }
    )
    if created: print(f"已创建用例: {case_api.title}")

    # 4. 创建 UI 用例 (包含故意失败以展示截图)
    case_ui, created = TestCase.objects.get_or_create(
        project=project,
        title="UI 自动化演示 (百度搜索+失败截图)",
        defaults={
            "status": "active",
            "steps": [
                {
                    "type": "ui",
                    "action": "open",
                    "url": "https://www.baidu.com",
                    "timeout": 10
                },
                {
                    "type": "ui",
                    "action": "input",
                    "selector": "#kw",
                    "text": "Trae IDE 自动化测试",
                    "timeout": 5
                },
                {
                    "type": "ui",
                    "action": "click",
                    "selector": "#su",
                    "timeout": 5
                },
                {
                    "type": "ui",
                    "action": "sleep",
                    "url": "2"
                },
                {
                    "type": "ui",
                    "action": "click",
                    "selector": "#non-exist-button-for-demo",
                    "timeout": 5
                }
            ]
        }
    )
    if created: print(f"已创建用例: {case_ui.title}")

    print("\n数据初始化完成！请刷新网页查看。")

if __name__ == "__main__":
    seed()
