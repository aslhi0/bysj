import os
from celery import Celery

# 设置 Django 默认配置模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('autotest_platform')

# 使用字符串，这样 worker 不必序列化对象
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现所有已安装应用中的任务
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
