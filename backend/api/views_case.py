"""TestCase viewset and related actions."""
from datetime import timedelta
import json
import os
import re
import time
from urllib.parse import urlparse

import requests
import yaml
from django.contrib.admin.models import ADDITION, CHANGE, DELETION
from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .audit_utils import audit_log
from .crypto_utils import decrypt_json
from .engine import validate_outbound_http_url
from .locust_codegen import generate_locust_code
from .models import EnvConfig, PerfRecord, Project, TestCase, TestCaseVersion
from .query_utils import apply_project_access_filter
from .serializers import TestCaseSerializer, TestCaseVersionSerializer, TestRecordSerializer
from .task_tracker import bind_task_owner
from .tasks import run_perf_test_task, run_test_case_task
from .view_utils import apply_limit_from_request


class TestCaseViewSet(viewsets.ModelViewSet):
    queryset = TestCase.objects.select_related("project", "project__owner").all()
    serializer_class = TestCaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        qs = apply_project_access_filter(qs, user, "project")
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

    def _ensure_admin(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser):
            raise PermissionDenied("仅管理员可进行用例配置操作")

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).order_by("-updated_at")
        qs = apply_limit_from_request(qs, request)
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
        self._ensure_admin()
        case = serializer.save()
        self.create_version(case, self.request.user)
        audit_log(self.request.user, case, ADDITION, f"创建用例: {case.title}")

    def perform_update(self, serializer):
        self._ensure_admin()
        case = serializer.save()
        self.create_version(case, self.request.user)
        audit_log(self.request.user, case, CHANGE, f"更新用例: {case.title}")

    def perform_destroy(self, instance):
        self._ensure_admin()
        audit_log(self.request.user, instance, DELETION, f"删除用例: {instance.title}")
        instance.delete()

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        case = self.get_object()
        qs = TestCaseVersion.objects.filter(case=case).order_by("-version")
        return Response(TestCaseVersionSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def restore_version(self, request, pk=None):
        self._ensure_admin()
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

    @action(detail=True, methods=["post"])
    def run_perf(self, request, pk=None):
        case = self.get_object()
        users = request.data.get("users", 10)
        spawn_rate = request.data.get("spawn_rate", 1)
        duration = request.data.get("duration", "60s")
        env_id = request.data.get("env_id")
        env = EnvConfig.objects.filter(project=case.project, id=env_id).first() if env_id else None
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
        m = re.fullmatch(r"(\d+)\s*([smh]?)", duration_s)
        if not m:
            return Response({"detail": "duration 格式不合法（如 60s / 5m / 1h）"}, status=status.HTTP_400_BAD_REQUEST)
        n = int(m.group(1))
        unit = m.group(2) or "s"
        seconds = n * (3600 if unit == "h" else 60 if unit == "m" else 1)
        if seconds < 1 or seconds > 600:
            return Response({"detail": "duration 超出范围（1-600s）"}, status=status.HTTP_400_BAD_REQUEST)
        duration = f"{seconds}s"
        recent_cutoff = timezone.now() - timedelta(seconds=10)
        existing = (
            PerfRecord.objects.filter(
                case=case,
                users=users,
                spawn_rate=spawn_rate,
                duration=duration,
                status__in=["queued", "running"],
                created_at__gte=recent_cutoff,
            )
            .order_by("-id")
            .first()
        )
        if existing is not None:
            return Response(
                {
                    "message": "检测到重复提交，已复用最近一次压测任务",
                    "perf_record_id": existing.id,
                    "csv_prefix": existing.csv_prefix,
                    "deduplicated": True,
                }
            )
        perf_record = PerfRecord.objects.create(case=case, users=users, spawn_rate=spawn_rate, duration=duration, csv_prefix="", status="queued")
        locust_code = generate_locust_code(case, base_url=base_url, variables=merged_vars)
        perf_dir = os.path.join(str(getattr(settings, "MEDIA_ROOT", os.getcwd())), "perf", str(perf_record.id))
        os.makedirs(perf_dir, exist_ok=True)
        with open(os.path.join(perf_dir, f"perf_{perf_record.id}.py"), "w", encoding="utf-8") as f:
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
        self._ensure_admin()
        max_spec_chars = 1_500_000
        max_paths = 500
        max_cases_created = 1000
        project_id = request.data.get("project")
        spec = request.data.get("spec")
        spec_url = request.data.get("spec_url")
        spec_yaml = request.data.get("spec_yaml")
        on_conflict = str(request.data.get("on_conflict", "skip")).strip().lower() or "skip"
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
        if on_conflict not in {"skip", "overwrite"}:
            return Response({"detail": "on_conflict 仅支持 skip / overwrite"}, status=status.HTTP_400_BAD_REQUEST)
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
                if not allow_hosts:
                    return Response(
                        {"detail": "项目未配置可用环境 base_url，无法通过 spec_url 导入"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    validate_outbound_http_url(str(spec_url), allowed_hosts=allow_hosts)
                    resp = requests.get(str(spec_url), timeout=(5, 10), allow_redirects=False, headers={"Accept": "application/json"})
                    resp.raise_for_status()
                    body = resp.text or ""
                    if len(body) > max_spec_chars:
                        return Response({"detail": "远程 spec 体积过大"}, status=status.HTTP_400_BAD_REQUEST)
                    content_type = str(resp.headers.get("Content-Type", "")).lower()
                    spec = yaml.safe_load(body) if "yaml" in content_type or body.lstrip().startswith(("openapi:", "swagger:")) else resp.json()
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

        def _from_schema(schema_obj):
            if not isinstance(schema_obj, dict):
                return {}
            typ = schema_obj.get("type")
            if typ == "object":
                props = schema_obj.get("properties", {})
                if not isinstance(props, dict):
                    return {}
                result = {}
                for k, sub in props.items():
                    if isinstance(sub, dict):
                        if "example" in sub:
                            result[k] = sub.get("example")
                        elif "default" in sub:
                            result[k] = sub.get("default")
                        else:
                            st = sub.get("type")
                            if st == "integer":
                                result[k] = 0
                            elif st == "number":
                                result[k] = 0
                            elif st == "boolean":
                                result[k] = False
                            elif st == "array":
                                result[k] = []
                            elif st == "object":
                                result[k] = {}
                            else:
                                result[k] = ""
                    else:
                        result[k] = ""
                return result
            if typ == "array":
                return []
            return {}

        for path, methods in paths.items():
            if not isinstance(path, str) or not path.startswith("/") or len(path) > 500 or not isinstance(methods, dict):
                continue
            for method, info in methods.items():
                if str(method).lower() not in allowed_methods:
                    continue
                if not isinstance(info, dict):
                    info = {}
                title = f"{method.upper()} {path} - {str(info.get('summary', 'OpenAPI Import'))[:120]}"
                existing = TestCase.objects.filter(project=project, title=title).first()
                if existing and on_conflict == "skip":
                    continue

                params = info.get("parameters", [])
                query_params = {}
                header_map = {}
                if isinstance(params, list):
                    for p in params:
                        if not isinstance(p, dict):
                            continue
                        p_name = p.get("name")
                        p_in = str(p.get("in", "")).lower()
                        if not p_name:
                            continue
                        if p_in == "query":
                            query_params[p_name] = f"{{{{{p_name}}}}}"
                        elif p_in == "header":
                            header_map[p_name] = f"{{{{{p_name}}}}}"

                final_path = path
                if query_params:
                    final_path = f"{path}?{'&'.join([f'{k}={v}' for k, v in query_params.items()])}"

                req_body = info.get("requestBody", {})
                body = ""
                if isinstance(req_body, dict):
                    content = req_body.get("content", {})
                    if isinstance(content, dict):
                        json_content = content.get("application/json") or {}
                        if isinstance(json_content, dict):
                            if "example" in json_content:
                                body = json_content.get("example")
                            else:
                                examples = json_content.get("examples", {})
                                if isinstance(examples, dict) and examples:
                                    first = next(iter(examples.values()))
                                    if isinstance(first, dict) and "value" in first:
                                        body = first.get("value")
                            if body == "":
                                schema_obj = json_content.get("schema", {})
                                body = _from_schema(schema_obj)
                            if isinstance(body, (dict, list)):
                                header_map.setdefault("Content-Type", "application/json")

                new_steps = [{
                    "type": "http",
                    "method": method.upper(),
                    "url": f"{{{{base_url}}}}{final_path}",
                    "headers": header_map,
                    "body": body,
                    "capture": {},
                }]
                if existing and on_conflict == "overwrite":
                    existing.steps = new_steps
                    existing.status = "draft"
                    existing.save(update_fields=["steps", "status", "updated_at"])
                else:
                    TestCase.objects.create(
                        project=project,
                        title=title,
                        steps=new_steps,
                        status="draft",
                    )
                count += 1
                if count >= max_cases_created:
                    return Response({"count": count, "truncated": True})
        return Response({"count": count})
