"""Case/Suite write viewsets extracted from api.views."""
import json
import os
import time
from urllib.parse import urlparse

import requests
import yaml
from django.contrib.admin.models import ADDITION, CHANGE, DELETION
from django.conf import settings
from django.http import HttpResponse
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .audit_utils import audit_log
from .crypto_utils import decrypt_json
from .engine import TestEngine, validate_outbound_http_url
from .locust_codegen import generate_locust_code
from .models import EnvConfig, PerfRecord, Project, TestCase, TestCaseVersion, TestSuite
from .serializers import (
    PeriodicTaskSerializer,
    SuiteRunSerializer,
    TestCaseSerializer,
    TestCaseVersionSerializer,
    TestRecordSerializer,
    TestSuiteSerializer,
)
from .task_tracker import bind_task_owner
from .tasks import run_perf_test_task, run_test_case_task, run_test_suite_task


class TestCaseViewSet(viewsets.ModelViewSet):
    queryset = TestCase.objects.select_related("project", "project__owner").all()
    serializer_class = TestCaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().filter(project__owner=self.request.user)
        project = self.request.query_params.get("project")
        status_q = self.request.query_params.get("status")
        q = self.request.query_params.get("q")
        if project:
            qs = qs.filter(project_id=project)
        if status_q:
            qs = qs.filter(status=status_q)
        if q:
            qs = qs.filter(title__icontains=q)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).order_by("-updated_at")
        limit = request.query_params.get("limit")
        if limit:
            try:
                n = int(limit)
                if n > 0:
                    qs = qs[: min(n, 500)]
            except Exception:
                pass
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def build_case_snapshot(self, case):
        return {
            "project": case.project_id,
            "title": case.title,
            "steps": case.steps,
            "variables": case.variables,
            "tags": case.tags,
            "setup_sql": case.setup_sql,
            "teardown_sql": case.teardown_sql,
            "status": case.status,
            "updated_at": str(case.updated_at),
        }

    def create_version(self, case, user):
        last = TestCaseVersion.objects.filter(case=case).order_by("-version").values_list("version", flat=True).first()
        next_v = (last or 0) + 1
        TestCaseVersion.objects.create(case=case, version=next_v, snapshot=self.build_case_snapshot(case), created_by=user)

    def perform_create(self, serializer):
        case = serializer.save()
        self.create_version(case, self.request.user)
        audit_log(self.request.user, case, ADDITION, f"创建用例: {case.title}")

    def perform_update(self, serializer):
        case = serializer.save()
        self.create_version(case, self.request.user)
        audit_log(self.request.user, case, CHANGE, f"更新用例: {case.title}")

    def perform_destroy(self, instance):
        audit_log(self.request.user, instance, DELETION, f"删除用例: {instance.title}")
        instance.delete()

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        case = self.get_object()
        qs = TestCaseVersion.objects.filter(case=case).order_by("-version")
        return Response(TestCaseVersionSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def restore_version(self, request, pk=None):
        case = self.get_object()
        version = request.data.get("version")
        vid = request.data.get("version_id")
        q = TestCaseVersion.objects.filter(case=case)
        if vid:
            q = q.filter(id=vid)
        elif version:
            q = q.filter(version=version)
        else:
            return Response({"detail": "缺少 version 或 version_id"}, status=status.HTTP_400_BAD_REQUEST)
        tv = q.first()
        if tv is None:
            return Response({"detail": "版本不存在"}, status=status.HTTP_404_NOT_FOUND)
        snap = tv.snapshot if isinstance(tv.snapshot, dict) else {}
        for f in ["title", "steps", "variables", "tags", "setup_sql", "teardown_sql", "status"]:
            if f in snap:
                setattr(case, f, snap.get(f))
        case.save()
        self.create_version(case, request.user)
        audit_log(request.user, case, CHANGE, f"回滚用例版本: {case.title}")
        return Response({"detail": "已回滚并生成新版本"})

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        case = self.get_object()
        extra_vars = request.data.get("variables", {})
        env_id = request.data.get("env_id")
        if env_id:
            env_id = EnvConfig.objects.filter(project=case.project, id=env_id).values_list("id", flat=True).first()
        if not env_id:
            env = EnvConfig.objects.filter(project=case.project, is_default=True).order_by("-created_at").first()
            if env is not None:
                env_id = env.id

        task = run_test_case_task.delay(case.id, env_id, extra_vars)
        bind_task_owner(task.id, request.user.id)

        return Response({"status": "pending", "task_id": task.id, "message": "测试任务已进入队列"})

    def get_or_create_crontab(self, request):
        crontab_id = request.data.get("crontab_id")
        if crontab_id:
            try:
                return CrontabSchedule.objects.get(id=crontab_id)
            except CrontabSchedule.DoesNotExist:
                return None

        minute = request.data.get("minute", "*")
        hour = request.data.get("hour", "*")
        day_of_week = request.data.get("day_of_week", "*")
        day_of_month = request.data.get("day_of_month", "*")
        month_of_year = request.data.get("month_of_year", "*")
        timezone = request.data.get("timezone") or getattr(settings, "TIME_ZONE", "Asia/Shanghai")

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
            kwargs="{}",
            enabled=bool(enabled),
            description=description,
        )
        return pt

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        case = self.get_object()
        env_id = request.data.get("env_id")
        if env_id:
            env_id = EnvConfig.objects.filter(project=case.project, id=env_id).values_list("id", flat=True).first()
        if not env_id:
            env = EnvConfig.objects.filter(project=case.project, is_default=True).order_by("-created_at").first()
            if env is not None:
                env_id = env.id

        extra_vars = request.data.get("variables", {}) or {}
        enabled = request.data.get("enabled", True)
        crontab = self.get_or_create_crontab(request)
        if crontab is None:
            return Response({"detail": "Cron 周期不存在"}, status=status.HTTP_400_BAD_REQUEST)

        name = request.data.get("name") or f"case#{case.id} {case.title} @ {int(time.time())}"
        description = json.dumps({"type": "case", "case_id": case.id, "owner_id": request.user.id}, ensure_ascii=False)
        pt = self.create_periodic_task(
            name=name,
            task="api.tasks.run_test_case_task",
            crontab=crontab,
            args=[case.id, env_id, extra_vars],
            enabled=enabled,
            description=description,
        )
        audit_log(request.user, pt, ADDITION, f"创建用例定时任务: case#{case.id}")
        return Response(PeriodicTaskSerializer(pt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def schedules(self, request, pk=None):
        case = self.get_object()
        qs = PeriodicTask.objects.filter(task="api.tasks.run_test_case_task").order_by("-id")[:500]
        items = []
        for pt in qs:
            try:
                d = json.loads(pt.description or "{}")
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            if d.get("type") != "case":
                continue
            if d.get("case_id") != case.id:
                continue
            if d.get("owner_id") != request.user.id:
                continue
            items.append(pt)
        return Response(PeriodicTaskSerializer(items, many=True).data)

    @action(detail=True, methods=["post"])
    def run_perf(self, request, pk=None):
        case = self.get_object()
        users = request.data.get("users", 10)
        spawn_rate = request.data.get("spawn_rate", 1)
        duration = request.data.get("duration", "60s")
        env_id = request.data.get("env_id")

        env = None
        if env_id:
            env = EnvConfig.objects.filter(project=case.project, id=env_id).first()
        if env is None:
            env = EnvConfig.objects.filter(project=case.project, is_default=True).order_by("-created_at").first()
        base_url = env.base_url if env and env.base_url else None
        merged_vars = {}
        if env and isinstance(env.variables, dict):
            merged_vars.update(decrypt_json(env.variables))
        if isinstance(case.variables, dict):
            merged_vars.update(case.variables)
        if base_url:
            merged_vars["base_url"] = base_url

        try:
            users = int(users)
        except Exception:
            users = 10
        try:
            spawn_rate = int(spawn_rate)
        except Exception:
            spawn_rate = 1
        if users < 1 or users > 200:
            return Response({"detail": "users 超出范围（1-200）"}, status=status.HTTP_400_BAD_REQUEST)
        if spawn_rate < 1 or spawn_rate > 50:
            return Response({"detail": "spawn_rate 超出范围（1-50）"}, status=status.HTTP_400_BAD_REQUEST)
        duration_s = str(duration).strip().lower()
        m = None
        try:
            import re as _re

            m = _re.fullmatch(r"(\d+)\s*([smh]?)", duration_s)
        except Exception:
            m = None
        if not m:
            return Response({"detail": "duration 格式不合法（如 60s / 5m / 1h）"}, status=status.HTTP_400_BAD_REQUEST)
        n = int(m.group(1))
        unit = m.group(2) or "s"
        seconds = n * (3600 if unit == "h" else 60 if unit == "m" else 1)
        if seconds < 1 or seconds > 600:
            return Response({"detail": "duration 超出范围（1-600s）"}, status=status.HTTP_400_BAD_REQUEST)
        duration = f"{seconds}s"

        perf_record = PerfRecord.objects.create(case=case, users=users, spawn_rate=spawn_rate, duration=duration, csv_prefix="", status="running")

        locust_code = generate_locust_code(case, base_url=base_url, variables=merged_vars)
        locust_file = f"perf_{perf_record.id}.py"
        perf_dir = os.path.join(str(getattr(settings, "MEDIA_ROOT", os.getcwd())), "perf", str(perf_record.id))
        os.makedirs(perf_dir, exist_ok=True)
        locust_path = os.path.join(perf_dir, locust_file)
        with open(locust_path, "w", encoding="utf-8") as f:
            f.write(locust_code)

        csv_prefix = f"perf_{case.id}_{perf_record.id}_{int(time.time())}"
        perf_record.csv_prefix = csv_prefix
        perf_record.save(update_fields=["csv_prefix"])

        task = run_perf_test_task.delay(perf_record.id)
        bind_task_owner(task.id, request.user.id)

        return Response({"message": "性能测试已进入后台队列", "perf_record_id": perf_record.id, "csv_prefix": csv_prefix})

    @action(detail=True, methods=["get"])
    def records(self, request, pk=None):
        case = self.get_object()
        records = case.records.all().order_by("-created_at")[:50]
        serializer = TestRecordSerializer(records, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="import-openapi")
    def import_openapi(self, request):
        max_spec_chars = 1_500_000
        max_paths = 500
        max_cases_created = 1000
        project_id = request.data.get("project")
        spec = request.data.get("spec")
        spec_url = request.data.get("spec_url")
        spec_yaml = request.data.get("spec_yaml")
        if not project_id:
            return Response({"detail": "缺少项目 ID"}, status=status.HTTP_400_BAD_REQUEST)
        if spec is None and not spec_url and not spec_yaml:
            return Response({"detail": "缺少 spec / spec_url / spec_yaml"}, status=status.HTTP_400_BAD_REQUEST)

        project = Project.objects.filter(id=project_id, owner=request.user).first()
        if project is None:
            return Response({"detail": "项目不存在或无权限"}, status=status.HTTP_404_NOT_FOUND)

        if spec_url is not None and not isinstance(spec_url, str):
            return Response({"detail": "spec_url 必须是字符串"}, status=status.HTTP_400_BAD_REQUEST)
        if spec_yaml is not None and not isinstance(spec_yaml, str):
            return Response({"detail": "spec_yaml 必须是字符串"}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(spec_url, str) and len(spec_url) > 2000:
            return Response({"detail": "spec_url 过长"}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(spec_yaml, str) and len(spec_yaml) > max_spec_chars:
            return Response({"detail": "spec_yaml 体积过大"}, status=status.HTTP_400_BAD_REQUEST)

        if spec is None:
            if spec_url:
                allow_hosts = []
                for u in EnvConfig.objects.filter(project=project).values_list("base_url", flat=True):
                    if not u:
                        continue
                    try:
                        h = urlparse(str(u)).hostname
                    except Exception:
                        h = None
                    if h:
                        allow_hosts.append(h)
                try:
                    validate_outbound_http_url(str(spec_url), allowed_hosts=allow_hosts or None)
                    resp = requests.get(str(spec_url), timeout=(5, 10), allow_redirects=False, headers={"Accept": "application/json"})
                    resp.raise_for_status()
                    body = resp.text or ""
                    if len(body) > max_spec_chars:
                        return Response({"detail": "远程 spec 体积过大"}, status=status.HTTP_400_BAD_REQUEST)
                    content_type = str(resp.headers.get("Content-Type", "")).lower()
                    if "yaml" in content_type or body.lstrip().startswith(("openapi:", "swagger:")):
                        spec = yaml.safe_load(body)
                    else:
                        spec = resp.json()
                except Exception as e:
                    return Response({"detail": f"拉取或解析 spec_url 失败: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            elif spec_yaml:
                try:
                    spec = yaml.safe_load(spec_yaml)
                except Exception as e:
                    return Response({"detail": f"解析 spec_yaml 失败: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(spec, str):
            if len(spec) > max_spec_chars:
                return Response({"detail": "spec 体积过大"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                spec = json.loads(spec)
            except Exception as e:
                return Response({"detail": f"spec 不是合法 JSON: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(spec, dict):
            return Response({"detail": "spec 必须是 JSON 对象"}, status=status.HTTP_400_BAD_REQUEST)
        paths = spec.get("paths", {})
        if not isinstance(paths, dict):
            return Response({"detail": "spec.paths 必须是对象"}, status=status.HTTP_400_BAD_REQUEST)
        if len(paths) > max_paths:
            return Response({"detail": f"paths 数量过多，最多允许 {max_paths} 条"}, status=status.HTTP_400_BAD_REQUEST)

        count = 0
        allowed_methods = {"get", "post", "put", "delete", "patch", "head", "options"}
        for path, methods in paths.items():
            if not isinstance(path, str) or not path.startswith("/") or len(path) > 500:
                continue
            if not isinstance(methods, dict):
                continue
            for method, info in methods.items():
                if str(method).lower() not in allowed_methods:
                    continue
                if not isinstance(info, dict):
                    info = {}
                title = f"{method.upper()} {path} - {str(info.get('summary', 'OpenAPI Import'))[:120]}"
                if TestCase.objects.filter(project=project, title=title).exists():
                    continue
                TestCase.objects.create(
                    project=project,
                    title=title,
                    steps=[{"type": "http", "method": method.upper(), "url": f"{{{{base_url}}}}{path}", "headers": "{}", "body": "", "capture": "{}"}],
                    status="draft",
                )
                count += 1
                if count >= max_cases_created:
                    return Response({"count": count, "truncated": True})
        return Response({"count": count})


class TestSuiteViewSet(viewsets.ModelViewSet):
    queryset = TestSuite.objects.select_related("project", "project__owner").all()
    serializer_class = TestSuiteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().filter(project__owner=self.request.user)
        project = self.request.query_params.get("project")
        q = self.request.query_params.get("q")
        if project:
            qs = qs.filter(project_id=project)
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).order_by("-id")
        limit = request.query_params.get("limit")
        if limit:
            try:
                n = int(limit)
                if n > 0:
                    qs = qs[: min(n, 500)]
            except Exception:
                pass
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        obj = serializer.save()
        audit_log(self.request.user, obj, ADDITION, f"创建套件: {obj.name}")

    def perform_update(self, serializer):
        obj = serializer.save()
        audit_log(self.request.user, obj, CHANGE, f"更新套件: {obj.name}")

    def perform_destroy(self, instance):
        audit_log(self.request.user, instance, DELETION, f"删除套件: {instance.name}")
        instance.delete()

    def build_suite_locust_code(self, suite, base_url=None):
        engine = TestEngine(variables={"base_url": base_url, "base": base_url} if base_url else {})
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
                if step.get("type") != "http":
                    continue
                method = str(step.get("method", "GET")).upper().strip() or "GET"
                if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}:
                    continue
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
                tasks.append(f"        self.client.request({json.dumps(method)}, {json.dumps(target)})")

        if not tasks:
            tasks = ["        pass"]

        host = base_url or inferred_host or "http://127.0.0.1"
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

    def sanitize_filename(self, value, default="suite"):
        s = "" if value is None else str(value)
        if not s.strip():
            return default
        for ch in ["\\", "/", ":", "*", "?", '"', "<", ">", "|", "\r", "\n"]:
            s = s.replace(ch, "_")
        s = s.strip()
        return s or default

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        suite = self.get_object()
        extra_vars = request.data.get("variables", {})
        env_id = request.data.get("env_id")
        stop_on_failure = request.data.get("stop_on_failure", False)
        if env_id:
            env_id = EnvConfig.objects.filter(project=suite.project, id=env_id).values_list("id", flat=True).first()
        if not env_id:
            env = EnvConfig.objects.filter(project=suite.project, is_default=True).order_by("-created_at").first()
            if env is not None:
                env_id = env.id

        task = run_test_suite_task.delay(suite.id, env_id, extra_vars, stop_on_failure)
        bind_task_owner(task.id, request.user.id)

        return Response({"status": "pending", "task_id": task.id, "message": "测试套件任务已进入队列"})

    @action(detail=True, methods=["get"])
    def export_locust(self, request, pk=None):
        suite = self.get_object()
        env = EnvConfig.objects.filter(project=suite.project, is_default=True).order_by("-created_at").first()
        base_url = env.base_url if env and env.base_url else None

        code = self.build_suite_locust_code(suite, base_url=base_url)
        filename = f"locust_suite_{suite.id}_{self.sanitize_filename(suite.name)}.py"

        resp = HttpResponse(code, content_type="text/x-python; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        suite = self.get_object()
        env_id = request.data.get("env_id")
        if env_id:
            env_id = EnvConfig.objects.filter(project=suite.project, id=env_id).values_list("id", flat=True).first()
        if not env_id:
            env = EnvConfig.objects.filter(project=suite.project, is_default=True).order_by("-created_at").first()
            if env is not None:
                env_id = env.id

        extra_vars = request.data.get("variables", {}) or {}
        stop_on_failure = bool(request.data.get("stop_on_failure", False))
        enabled = request.data.get("enabled", True)

        minute = request.data.get("minute", "*")
        hour = request.data.get("hour", "*")
        day_of_week = request.data.get("day_of_week", "*")
        day_of_month = request.data.get("day_of_month", "*")
        month_of_year = request.data.get("month_of_year", "*")
        timezone = request.data.get("timezone") or getattr(settings, "TIME_ZONE", "Asia/Shanghai")
        crontab_id = request.data.get("crontab_id")
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

        name = request.data.get("name") or f"suite#{suite.id} {suite.name} @ {int(time.time())}"
        description = json.dumps({"type": "suite", "suite_id": suite.id, "owner_id": request.user.id}, ensure_ascii=False)
        pt = PeriodicTask.objects.create(
            name=name,
            task="api.tasks.run_test_suite_task",
            crontab=crontab,
            args=json.dumps([suite.id, env_id, extra_vars, stop_on_failure], ensure_ascii=False),
            kwargs="{}",
            enabled=bool(enabled),
            description=description,
        )
        audit_log(request.user, pt, ADDITION, f"创建套件定时任务: suite#{suite.id}")
        return Response(PeriodicTaskSerializer(pt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def schedules(self, request, pk=None):
        suite = self.get_object()
        qs = PeriodicTask.objects.filter(task="api.tasks.run_test_suite_task").order_by("-id")[:500]
        items = []
        for pt in qs:
            try:
                d = json.loads(pt.description or "{}")
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            if d.get("type") != "suite":
                continue
            if d.get("suite_id") != suite.id:
                continue
            if d.get("owner_id") != request.user.id:
                continue
            items.append(pt)
        return Response(PeriodicTaskSerializer(items, many=True).data)

    @action(detail=True, methods=["get"])
    def runs(self, request, pk=None):
        suite = self.get_object()
        runs = suite.runs.all().order_by("-created_at")[:50]
        serializer = SuiteRunSerializer(runs, many=True)
        return Response(serializer.data)
