import subprocess
import os
import signal
import time
import json
import requests
import yaml
import csv
import html
from urllib.parse import urlparse
from django.core.files.base import ContentFile
from django.conf import settings
from django.http import HttpResponse
from celery import current_app
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.response import Response
from celery.result import AsyncResult
from .models import Project, TestCase, TestSuite, TestRecord, SuiteRun, EnvConfig, PerfRecord
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from .serializers import (
    ProjectSerializer, TestCaseSerializer, TestSuiteSerializer, 
    TestRecordSerializer, SuiteRunSerializer, EnvConfigSerializer,
    PeriodicTaskSerializer, CrontabScheduleSerializer, PerfRecordSerializer
)
from .engine import TestEngine
from .tasks import run_test_case_task, run_test_suite_task, run_perf_test_task

class ApiKeyOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        api_key = os.getenv('API_KEY')
        if not api_key:
            return True
        provided = request.headers.get('X-API-Key') or request.query_params.get('api_key')
        return provided == api_key

class EnvConfigViewSet(viewsets.ModelViewSet):
    queryset = EnvConfig.objects.all()
    serializer_class = EnvConfigSerializer
    permission_classes = [ApiKeyOrReadOnly]

class CrontabScheduleViewSet(viewsets.ModelViewSet):
    queryset = CrontabSchedule.objects.all()
    serializer_class = CrontabScheduleSerializer
    permission_classes = [ApiKeyOrReadOnly]

class PeriodicTaskViewSet(viewsets.ModelViewSet):
    queryset = PeriodicTask.objects.all()
    serializer_class = PeriodicTaskSerializer
    permission_classes = [ApiKeyOrReadOnly]

    @action(detail=True, methods=['post'])
    def trigger(self, request, pk=None):
        pt = self.get_object()
        try:
            args = json.loads(pt.args or '[]')
        except Exception:
            args = []
        try:
            kwargs = json.loads(pt.kwargs or '{}')
        except Exception:
            kwargs = {}
        try:
            async_result = current_app.send_task(pt.task, args=args, kwargs=kwargs)
            return Response({'task_id': async_result.id, 'message': '已触发执行'})
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [ApiKeyOrReadOnly]

class TestCaseViewSet(viewsets.ModelViewSet):
    queryset = TestCase.objects.all()
    serializer_class = TestCaseSerializer
    permission_classes = [ApiKeyOrReadOnly]

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        case = self.get_object()
        extra_vars = request.data.get('variables', {})
        env_id = request.data.get('env_id')
        if not env_id:
            env = (
                EnvConfig.objects.filter(project=case.project, is_default=True)
                .order_by('-created_at')
                .first()
            )
            if env is not None:
                env_id = env.id
        
        # 异步执行任务
        task = run_test_case_task.delay(case.id, env_id, extra_vars)
        
        return Response({
            'status': 'pending',
            'task_id': task.id,
            'message': '测试任务已进入队列'
        })

    def get_or_create_crontab(self, request):
        crontab_id = request.data.get('crontab_id')
        if crontab_id:
            try:
                return CrontabSchedule.objects.get(id=crontab_id)
            except CrontabSchedule.DoesNotExist:
                return None

        minute = request.data.get('minute', '*')
        hour = request.data.get('hour', '*')
        day_of_week = request.data.get('day_of_week', '*')
        day_of_month = request.data.get('day_of_month', '*')
        month_of_year = request.data.get('month_of_year', '*')
        timezone = request.data.get('timezone') or getattr(settings, 'TIME_ZONE', 'Asia/Shanghai')

        crontab, _ = CrontabSchedule.objects.get_or_create(
            minute=str(minute),
            hour=str(hour),
            day_of_week=str(day_of_week),
            day_of_month=str(day_of_month),
            month_of_year=str(month_of_year),
            timezone=str(timezone),
        )
        return crontab

    def create_periodic_task(self, *, name, task, crontab, args, enabled, description):
        payload_args = json.dumps(args, ensure_ascii=False)
        pt = PeriodicTask.objects.create(
            name=name,
            task=task,
            crontab=crontab,
            args=payload_args,
            kwargs='{}',
            enabled=bool(enabled),
            description=description,
        )
        return pt

    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        case = self.get_object()
        env_id = request.data.get('env_id')
        if not env_id:
            env = (
                EnvConfig.objects.filter(project=case.project, is_default=True)
                .order_by('-created_at')
                .first()
            )
            if env is not None:
                env_id = env.id

        extra_vars = request.data.get('variables', {}) or {}
        enabled = request.data.get('enabled', True)
        crontab = self.get_or_create_crontab(request)
        if crontab is None:
            return Response({'detail': 'Cron 周期不存在'}, status=status.HTTP_400_BAD_REQUEST)

        name = request.data.get('name') or f"case#{case.id} {case.title} @ {int(time.time())}"
        description = json.dumps({'type': 'case', 'case_id': case.id}, ensure_ascii=False)
        pt = self.create_periodic_task(
            name=name,
            task='api.tasks.run_test_case_task',
            crontab=crontab,
            args=[case.id, env_id, extra_vars],
            enabled=enabled,
            description=description,
        )
        return Response(PeriodicTaskSerializer(pt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def schedules(self, request, pk=None):
        case = self.get_object()
        qs = PeriodicTask.objects.filter(description__contains=f'"type": "case"').filter(description__contains=f'"case_id": {case.id}')
        return Response(PeriodicTaskSerializer(qs.order_by('-id'), many=True).data)

    @action(detail=True, methods=['post'])
    def run_perf(self, request, pk=None):
        case = self.get_object()
        users = request.data.get('users', 10)
        spawn_rate = request.data.get('spawn_rate', 1)
        duration = request.data.get('duration', '60s')
        env_id = request.data.get('env_id')

        env = None
        if env_id:
            try:
                env = EnvConfig.objects.get(id=env_id)
            except EnvConfig.DoesNotExist:
                env = None
        if env is None:
            env = (
                EnvConfig.objects.filter(project=case.project, is_default=True)
                .order_by('-created_at')
                .first()
            )
        base_url = None
        if env and env.base_url:
            base_url = env.base_url
        merged_vars = {}
        if env and isinstance(env.variables, dict):
            merged_vars.update(env.variables)
        if isinstance(case.variables, dict):
            merged_vars.update(case.variables)
        if base_url:
            merged_vars['base_url'] = base_url
        
        # Create PerfRecord
        perf_record = PerfRecord.objects.create(
            case=case,
            users=users,
            spawn_rate=spawn_rate,
            duration=duration,
            csv_prefix='',
            status='running'
        )

        # Generate Locust file (per-record to avoid collisions)
        locust_code = self.generate_locust_code(case, base_url=base_url, variables=merged_vars)
        locust_file = f"perf_{perf_record.id}.py"
        base_dir = str(getattr(settings, 'BASE_DIR', os.getcwd()))
        locust_path = os.path.join(base_dir, locust_file)
        with open(locust_path, 'w', encoding='utf-8') as f:
            f.write(locust_code)

        # Run Locust in headless mode
        csv_prefix = f"perf_{case.id}_{perf_record.id}_{int(time.time())}"
        perf_record.csv_prefix = csv_prefix
        perf_record.save(update_fields=['csv_prefix'])

        # 异步执行压测任务
        run_perf_test_task.delay(perf_record.id)
        
        return Response({
            'message': '性能测试已进入后台队列', 
            'perf_record_id': perf_record.id,
            'csv_prefix': csv_prefix
        })

    def generate_locust_code(self, case, base_url=None, variables=None):
        engine_vars = variables if isinstance(variables, dict) else {}
        if base_url:
            engine_vars = {**engine_vars, 'base_url': base_url, 'base': base_url}
        engine = TestEngine(variables=engine_vars)
        tasks = []
        inferred_host = None
        for idx, step in enumerate(case.steps or []):
            if step.get('type') != 'http':
                continue

            method = str(step.get('method', 'GET')).upper().strip() or 'GET'
            raw_url = step.get('url', '/')
            rendered = engine.render_string(raw_url) if isinstance(raw_url, str) else raw_url
            target = rendered if isinstance(rendered, str) else '/'
            if target.startswith('http://') or target.startswith('https://'):
                u = urlparse(target)
                if not inferred_host and u.scheme and u.netloc:
                    inferred_host = f"{u.scheme}://{u.netloc}"
                path = u.path or '/'
                if u.query:
                    path = f"{path}?{u.query}"
                target = path
            if not isinstance(target, str) or not target:
                target = '/'
            if not target.startswith('/'):
                target = f"/{target}"

            headers = engine.parse_jsonish(step.get('headers', {}), default={})
            if not isinstance(headers, dict):
                headers = {}

            body_raw = step.get('body', '')
            body_obj = None
            body_text = None
            if isinstance(body_raw, (dict, list)):
                body_obj = engine.render_data(body_raw)
            elif isinstance(body_raw, str):
                s = engine.render_string(body_raw)
                try:
                    parsed = json.loads(s) if s.strip() else None
                except Exception:
                    parsed = None
                if isinstance(parsed, (dict, list)):
                    body_obj = engine.render_data(parsed)
                else:
                    body_text = s

            kwargs = []
            if headers:
                kwargs.append(f"headers={json.dumps(headers, ensure_ascii=False)}")
            if body_obj is not None:
                kwargs.append(f"json={json.dumps(body_obj, ensure_ascii=False)}")
            elif body_text:
                kwargs.append(f"data={json.dumps(body_text, ensure_ascii=False)}")
            kwargs.append(f"name={json.dumps(f'{method} {target}', ensure_ascii=False)}")

            kw = (', ' + ', '.join(kwargs)) if kwargs else ''
            tasks.append(f"        self.client.request({json.dumps(method)}, {json.dumps(target)}{kw})")
        if not tasks:
            tasks = ["        pass"]

        host = base_url or inferred_host or 'http://127.0.0.1'
        safe_host = str(host).replace('"', '\\"')
        
        template = f"""
from locust import HttpUser, task, between

class QuickstartUser(HttpUser):
    host = "{safe_host}"
    wait_time = between(1, 2)

    @task
    def functional_case_task(self):
{chr(10).join(tasks)}
"""
        return template.lstrip()

    @action(detail=True, methods=['get'])
    def records(self, request, pk=None):
        case = self.get_object()
        records = case.records.all().order_by('-created_at')[:50]
        serializer = TestRecordSerializer(records, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='import-openapi')
    def import_openapi(self, request):
        project_id = request.data.get('project')
        spec = request.data.get('spec')
        spec_url = request.data.get('spec_url')
        spec_yaml = request.data.get('spec_yaml')
        # Simplified OpenAPI import logic
        if not project_id:
            return Response({'detail': '缺少项目 ID'}, status=status.HTTP_400_BAD_REQUEST)
        if spec is None and not spec_url and not spec_yaml:
            return Response({'detail': '缺少 spec / spec_url / spec_yaml'}, status=status.HTTP_400_BAD_REQUEST)

        if spec is None:
            if spec_url:
                try:
                    resp = requests.get(str(spec_url), timeout=15)
                    resp.raise_for_status()
                    spec = resp.json()
                except Exception as e:
                    return Response({'detail': f'拉取或解析 spec_url 失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            elif spec_yaml:
                try:
                    spec = yaml.safe_load(spec_yaml)
                except Exception as e:
                    return Response({'detail': f'解析 spec_yaml 失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except Exception as e:
                return Response({'detail': f'spec 不是合法 JSON: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        
        project = Project.objects.get(id=project_id)
        paths = spec.get('paths', {})
        count = 0
        allowed_methods = {'get', 'post', 'put', 'delete', 'patch', 'head', 'options'}
        for path, methods in paths.items():
            for method, info in methods.items():
                if str(method).lower() not in allowed_methods:
                    continue
                title = f"{method.upper()} {path} - {info.get('summary', 'OpenAPI Import')}"
                TestCase.objects.create(
                    project=project,
                    title=title,
                    steps=[{
                        'type': 'http',
                        'method': method.upper(),
                        'url': f"{{{{base_url}}}}{path}",
                        'headers': '{}',
                        'body': '',
                        'capture': '{}'
                    }],
                    status='draft'
                )
                count += 1
        return Response({'count': count})

class TestSuiteViewSet(viewsets.ModelViewSet):
    queryset = TestSuite.objects.all()
    serializer_class = TestSuiteSerializer
    permission_classes = [ApiKeyOrReadOnly]

    def build_suite_locust_code(self, suite, base_url=None):
        engine = TestEngine(variables={'base_url': base_url, 'base': base_url} if base_url else {})
        tasks = []
        inferred_host = None

        ordered_ids = suite.ordered_case_ids or []
        cases = TestCase.objects.filter(id__in=ordered_ids)
        case_map = {c.id: c for c in cases}
        for cid in ordered_ids:
            case = case_map.get(cid)
            if not case:
                continue
            for step in case.steps or []:
                if step.get('type') != 'http':
                    continue
                method = str(step.get('method', 'GET')).lower()
                raw_url = step.get('url', '/')
                rendered = engine.render_string(raw_url) if isinstance(raw_url, str) else raw_url
                target = rendered if isinstance(rendered, str) else '/'
                if target.startswith('http://') or target.startswith('https://'):
                    u = urlparse(target)
                    if not inferred_host and u.scheme and u.netloc:
                        inferred_host = f"{u.scheme}://{u.netloc}"
                    path = u.path or '/'
                    if u.query:
                        path = f"{path}?{u.query}"
                    target = path
                if not isinstance(target, str) or not target:
                    target = '/'
                if not target.startswith('/'):
                    target = f"/{target}"
                tasks.append(f"        self.client.{method}('{target}')")

        if not tasks:
            tasks = ["        pass"]

        host = base_url or inferred_host or 'http://127.0.0.1'
        safe_host = str(host).replace('"', '\\"')
        safe_name = f"suite_{suite.id}"

        template = f"""
from locust import HttpUser, task, between

class {safe_name}(HttpUser):
    host = "{safe_host}"
    wait_time = between(1, 2)

    @task
    def run_suite(self):
{chr(10).join(tasks)}
"""
        return template.lstrip()

    def sanitize_filename(self, value, default='suite'):
        s = '' if value is None else str(value)
        if not s.strip():
            return default
        for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\r', '\n']:
            s = s.replace(ch, '_')
        s = s.strip()
        return s or default

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        suite = self.get_object()
        extra_vars = request.data.get('variables', {})
        env_id = request.data.get('env_id')
        stop_on_failure = request.data.get('stop_on_failure', False)
        if not env_id:
            env = (
                EnvConfig.objects.filter(project=suite.project, is_default=True)
                .order_by('-created_at')
                .first()
            )
            if env is not None:
                env_id = env.id
        
        # 异步执行任务
        task = run_test_suite_task.delay(suite.id, env_id, extra_vars, stop_on_failure)
        
        return Response({
            'status': 'pending',
            'task_id': task.id,
            'message': '测试套件任务已进入队列'
        })

    @action(detail=True, methods=['get'])
    def export_locust(self, request, pk=None):
        suite = self.get_object()
        env = (
            EnvConfig.objects.filter(project=suite.project, is_default=True)
            .order_by('-created_at')
            .first()
        )
        base_url = env.base_url if env and env.base_url else None

        code = self.build_suite_locust_code(suite, base_url=base_url)
        filename = f"locust_suite_{suite.id}_{self.sanitize_filename(suite.name)}.py"

        resp = HttpResponse(code, content_type='text/x-python; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        suite = self.get_object()
        env_id = request.data.get('env_id')
        if not env_id:
            env = (
                EnvConfig.objects.filter(project=suite.project, is_default=True)
                .order_by('-created_at')
                .first()
            )
            if env is not None:
                env_id = env.id

        extra_vars = request.data.get('variables', {}) or {}
        stop_on_failure = bool(request.data.get('stop_on_failure', False))
        enabled = request.data.get('enabled', True)

        minute = request.data.get('minute', '*')
        hour = request.data.get('hour', '*')
        day_of_week = request.data.get('day_of_week', '*')
        day_of_month = request.data.get('day_of_month', '*')
        month_of_year = request.data.get('month_of_year', '*')
        timezone = request.data.get('timezone') or getattr(settings, 'TIME_ZONE', 'Asia/Shanghai')
        crontab_id = request.data.get('crontab_id')
        crontab = None
        if crontab_id:
            try:
                crontab = CrontabSchedule.objects.get(id=crontab_id)
            except CrontabSchedule.DoesNotExist:
                crontab = None
        if crontab is None:
            crontab, _ = CrontabSchedule.objects.get_or_create(
                minute=str(minute),
                hour=str(hour),
                day_of_week=str(day_of_week),
                day_of_month=str(day_of_month),
                month_of_year=str(month_of_year),
                timezone=str(timezone),
            )

        name = request.data.get('name') or f"suite#{suite.id} {suite.name} @ {int(time.time())}"
        description = json.dumps({'type': 'suite', 'suite_id': suite.id}, ensure_ascii=False)
        pt = PeriodicTask.objects.create(
            name=name,
            task='api.tasks.run_test_suite_task',
            crontab=crontab,
            args=json.dumps([suite.id, env_id, extra_vars, stop_on_failure], ensure_ascii=False),
            kwargs='{}',
            enabled=bool(enabled),
            description=description,
        )
        return Response(PeriodicTaskSerializer(pt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def schedules(self, request, pk=None):
        suite = self.get_object()
        qs = PeriodicTask.objects.filter(description__contains=f'"type": "suite"').filter(description__contains=f'"suite_id": {suite.id}')
        return Response(PeriodicTaskSerializer(qs.order_by('-id'), many=True).data)

    @action(detail=True, methods=['get'])
    def runs(self, request, pk=None):
        suite = self.get_object()
        runs = suite.runs.all().order_by('-created_at')[:50]
        serializer = SuiteRunSerializer(runs, many=True)
        return Response(serializer.data)

class TestRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestRecord.objects.all().order_by('-created_at')
    serializer_class = TestRecordSerializer
    permission_classes = [ApiKeyOrReadOnly]

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        record = self.get_object()
        case = record.case
        project = case.project
        screenshot_url = None
        if record.screenshot:
            try:
                screenshot_url = request.build_absolute_uri(record.screenshot.url)
            except Exception:
                screenshot_url = record.screenshot.url

        status_map = {
            'success': ('通过', '#67C23A'),
            'failed': ('失败', '#F56C6C'),
            'running': ('执行中', '#909399'),
            'error': ('异常', '#E6A23C'),
        }
        status_text, status_color = status_map.get(record.status, (record.status, '#909399'))

        def esc(s):
            return html.escape('' if s is None else str(s))

        step_rows = []
        for i, sr in enumerate(record.step_results or []):
            name = esc(sr.get('name') or f'步骤 {i + 1}')
            st = sr.get('status') or ''
            st_text = '通过' if st == 'success' else '失败'
            st_color = '#67C23A' if st == 'success' else '#F56C6C'
            elapsed = esc(sr.get('elapsed') or '')
            logs = sr.get('log') or []
            if not isinstance(logs, list):
                logs = [logs]
            logs_html = '<br/>'.join(esc(l) for l in logs if l is not None)
            step_rows.append(
                f"<tr>"
                f"<td>{i + 1}</td>"
                f"<td>{name}</td>"
                f"<td style='color:{st_color};font-weight:600'>{st_text}</td>"
                f"<td>{elapsed}</td>"
                f"<td style='font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size:12px'>{logs_html}</td>"
                f"</tr>"
            )

        full_log = esc(record.result_log or '')
        created_at = esc(record.created_at)
        elapsed_time = esc(f"{record.elapsed_time:.2f}")
        title = esc(case.title)
        project_name = esc(project.name)

        screenshot_block = ''
        if screenshot_url:
            screenshot_block = (
                f"<h2>失败截图</h2>"
                f"<div style='margin: 8px 0'>"
                f"<a href='{esc(screenshot_url)}' target='_blank' rel='noreferrer'>打开原图</a>"
                f"</div>"
                f"<img src='{esc(screenshot_url)}' style='max-width:100%; border:1px solid #eee' />"
            )

        html_text = (
            "<!doctype html>"
            "<html><head><meta charset='utf-8'/>"
            f"<title>测试报告 - Record #{record.id}</title>"
            "<style>"
            "body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;max-width:1100px;margin:24px auto;padding:0 16px;}"
            "h1{font-size:20px;margin:0 0 8px 0;}"
            "h2{font-size:16px;margin:20px 0 8px 0;}"
            ".meta{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;}"
            ".tag{display:inline-block;padding:4px 8px;border-radius:6px;background:#f5f7fa;font-size:12px;}"
            "table{border-collapse:collapse;width:100%;}"
            "th,td{border:1px solid #ebeef5;padding:8px 10px;font-size:13px;vertical-align:top;}"
            "th{background:#fafafa;text-align:left;}"
            "pre{background:#0b1020;color:#e6edf3;padding:12px;border-radius:8px;overflow:auto;font-size:12px;line-height:1.5;}"
            "</style>"
            "</head><body>"
            f"<h1>测试报告 - Record #{record.id}</h1>"
            "<div class='meta'>"
            f"<span class='tag'>项目：{project_name}</span>"
            f"<span class='tag'>用例：{title}</span>"
            f"<span class='tag'>时间：{created_at}</span>"
            f"<span class='tag'>耗时：{elapsed_time}s</span>"
            f"<span class='tag' style='background:{status_color};color:#fff'>结果：{esc(status_text)}</span>"
            "</div>"
            "<h2>步骤明细</h2>"
            "<table>"
            "<thead><tr><th>#</th><th>步骤</th><th>状态</th><th>耗时(s)</th><th>简要日志</th></tr></thead>"
            "<tbody>"
            + "".join(step_rows)
            + "</tbody></table>"
            f"{screenshot_block}"
            "<h2>原始日志</h2>"
            f"<pre>{full_log}</pre>"
            "</body></html>"
        )

        resp = HttpResponse(html_text, content_type='text/html; charset=utf-8')
        if request.query_params.get('download') in {'1', 'true', 'yes'}:
            resp['Content-Disposition'] = f'attachment; filename=\"record_{record.id}.html\"'
        return resp

    @action(detail=False, methods=['get'])
    def recent(self, request):
        records = self.get_queryset()[:10]
        serializer = self.get_serializer(records, many=True)
        return Response(serializer.data)

class SuiteRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SuiteRun.objects.all().order_by('-created_at')
    serializer_class = SuiteRunSerializer
    permission_classes = [ApiKeyOrReadOnly]

class PerfRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PerfRecord.objects.all().order_by('-created_at')
    serializer_class = PerfRecordSerializer
    permission_classes = [ApiKeyOrReadOnly]

    def sanitize_filename(self, value, default='record'):
        s = '' if value is None else str(value)
        if not s.strip():
            return default
        for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\r', '\n']:
            s = s.replace(ch, '_')
        s = s.strip()
        return s or default

    def read_csv_rows(self, file_path):
        rows = []
        if not os.path.exists(file_path):
            return rows
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
        return rows

    def parse_int(self, v, default=0):
        try:
            if v is None:
                return default
            s = str(v).strip()
            if s == '':
                return default
            return int(float(s))
        except Exception:
            return default

    def parse_float(self, v, default=0.0):
        try:
            if v is None:
                return default
            s = str(v).strip()
            if s == '':
                return default
            return float(s)
        except Exception:
            return default

    def pick_aggregated_row(self, stats_rows):
        for r in stats_rows:
            name = (r.get('Name') or r.get('name') or '').strip().lower()
            typ = (r.get('Type') or r.get('type') or '').strip().lower()
            if name in {'aggregated', 'total'} or typ in {'aggregated', 'total'}:
                return r
        if stats_rows:
            return stats_rows[0]
        return None

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        record = self.get_object()
        if not record.csv_prefix:
            return Response({'detail': '该记录暂无 CSV 输出前缀'}, status=status.HTTP_404_NOT_FOUND)
        base_dir = str(getattr(settings, 'BASE_DIR', os.getcwd()))
        prefix = record.csv_prefix
        stats_path = os.path.join(base_dir, f'{prefix}_stats.csv')
        history_path = os.path.join(base_dir, f'{prefix}_stats_history.csv')

        stats_rows = self.read_csv_rows(stats_path)
        history_rows = self.read_csv_rows(history_path)
        agg = self.pick_aggregated_row(stats_rows)
        if not agg and not history_rows:
            return Response(
                {'detail': '未找到压测 CSV 文件，请确认压测是否已完成并生成 CSV'},
                status=status.HTTP_404_NOT_FOUND,
            )

        summary = {}
        if agg:
            req_count = self.parse_int(agg.get('Request Count') or agg.get('request_count') or agg.get('Requests'))
            fail_count = self.parse_int(agg.get('Failure Count') or agg.get('failure_count') or agg.get('Failures'))
            rps = self.parse_float(agg.get('Requests/s') or agg.get('requests/s') or agg.get('RPS'))
            fps = self.parse_float(agg.get('Failures/s') or agg.get('failures/s') or agg.get('Failures/s'))
            avg_rt = self.parse_float(agg.get('Average Response Time') or agg.get('avg_response_time') or agg.get('Average'))
            med_rt = self.parse_float(agg.get('Median Response Time') or agg.get('median_response_time') or agg.get('Median'))
            min_rt = self.parse_float(agg.get('Min Response Time') or agg.get('min_response_time') or agg.get('Min'))
            max_rt = self.parse_float(agg.get('Max Response Time') or agg.get('max_response_time') or agg.get('Max'))
            fail_rate = (fail_count / req_count) if req_count else 0.0
            summary = {
                'requests': req_count,
                'failures': fail_count,
                'fail_rate': fail_rate,
                'rps': rps,
                'failures_per_sec': fps,
                'avg_rt_ms': avg_rt,
                'median_rt_ms': med_rt,
                'min_rt_ms': min_rt,
                'max_rt_ms': max_rt,
            }

        series = []
        for r in history_rows:
            name = (r.get('Name') or '').strip().lower()
            typ = (r.get('Type') or '').strip().lower()
            if name and name not in {'aggregated', 'total'} and typ and typ not in {'aggregated', 'total'}:
                continue
            ts = self.parse_int(r.get('Timestamp') or r.get('timestamp'))
            uc = self.parse_int(r.get('User Count') or r.get('user_count'))
            rps = self.parse_float(r.get('Requests/s') or r.get('requests/s'))
            fps = self.parse_float(r.get('Failures/s') or r.get('failures/s'))
            avg_rt = self.parse_float(r.get('Average Response Time') or r.get('Average'))
            med_rt = self.parse_float(r.get('Median Response Time') or r.get('Median'))
            series.append({
                'ts': ts,
                'user_count': uc,
                'rps': rps,
                'failures_per_sec': fps,
                'avg_rt_ms': avg_rt,
                'median_rt_ms': med_rt,
            })

        return Response({
            'perf_record_id': record.id,
            'case_id': record.case_id,
            'csv_prefix': record.csv_prefix,
            'status': record.status,
            'summary': summary,
            'series': series,
            'files': {
                'stats': os.path.exists(stats_path),
                'history': os.path.exists(history_path),
            },
        })

    @action(detail=True, methods=['get'])
    def locust(self, request, pk=None):
        perf_record = self.get_object()
        case = perf_record.case
        env = (
            EnvConfig.objects.filter(project=case.project, is_default=True)
            .order_by('-created_at')
            .first()
        )
        base_url = env.base_url if env and env.base_url else None

        merged_vars = {}
        if env and isinstance(env.variables, dict):
            merged_vars.update(env.variables)
        if isinstance(case.variables, dict):
            merged_vars.update(case.variables)
        if base_url:
            merged_vars['base_url'] = base_url

        code = TestCaseViewSet().generate_locust_code(case, base_url=base_url, variables=merged_vars)
        filename = f"locust_perf_{perf_record.id}_{self.sanitize_filename(case.title, default='case')}.py"
        resp = HttpResponse(code, content_type='text/x-python; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

@api_view(['GET'])
def task_status(request, task_id):
    result = AsyncResult(task_id)
    return Response({
        'task_id': task_id,
        'status': result.status,
        'ready': result.ready(),
        'result': result.result if result.ready() else None
    })

def health_check(request):
    from django.http import JsonResponse
    return JsonResponse({'status': 'ok', 'service': 'AutoTest Backend v1.0'})
