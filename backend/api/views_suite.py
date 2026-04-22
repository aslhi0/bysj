"""TestSuite viewset and related actions."""

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .audit_utils import audit_log
from .locust_codegen import generate_locust_code_for_suite
from .models import EnvConfig, TestSuite
from .query_utils import apply_project_access_filter
from .serializers import SuiteRunSerializer, TestSuiteSerializer
from .task_tracker import bind_task_owner
from .tasks import run_test_suite_task
from .view_utils import apply_limit_from_request


class TestSuiteViewSet(viewsets.ModelViewSet):
    queryset = TestSuite.objects.select_related("project", "project__owner").all()
    serializer_class = TestSuiteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        qs = apply_project_access_filter(qs, user, "project")
        project = self.request.query_params.get("project")
        q = self.request.query_params.get("q")
        if project:
            qs = qs.filter(project_id=project)
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def _ensure_admin(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser):
            raise PermissionDenied("仅管理员可进行套件配置操作")

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).order_by("-id")
        qs = apply_limit_from_request(qs, request)
        ordered_ids = []
        for suite in qs:
            ids = suite.ordered_case_ids or []
            if isinstance(ids, list):
                ordered_ids.extend([cid for cid in ids if isinstance(cid, int)])
        case_cache = {}
        if ordered_ids:
            from .models import TestCase

            case_cache = {
                c["id"]: c["title"] for c in TestCase.objects.filter(id__in=set(ordered_ids)).values("id", "title")
            }
        context = self.get_serializer_context()
        context["case_cache"] = case_cache
        serializer = self.get_serializer(qs, many=True, context=context)
        return Response(serializer.data)

    def perform_create(self, serializer):
        self._ensure_admin()
        obj = serializer.save()
        audit_log(self.request.user, obj, 1, f"创建套件: {obj.name}")

    def perform_update(self, serializer):
        self._ensure_admin()
        obj = serializer.save()
        audit_log(self.request.user, obj, 2, f"更新套件: {obj.name}")

    def perform_destroy(self, instance):
        self._ensure_admin()
        audit_log(self.request.user, instance, 3, f"删除套件: {instance.name}")
        instance.delete()

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
        from rest_framework import status as http_status

        suite = self.get_object()
        extra_vars = request.data.get("variables", {})
        env_id = request.data.get("env_id")
        stop_on_failure = request.data.get("stop_on_failure", False)
        retry_times = request.data.get("retry_times", 0)
        try:
            retry_times = int(retry_times)
        except Exception:
            retry_times = 0
        if retry_times < 0 or retry_times > 3:
            return Response({"detail": "retry_times 超出范围（0-3）"}, status=http_status.HTTP_400_BAD_REQUEST)
        if env_id:
            env_id = EnvConfig.objects.filter(project=suite.project, id=env_id).values_list("id", flat=True).first()
        if not env_id:
            env = EnvConfig.objects.filter(project=suite.project, is_default=True).order_by("-created_at").first()
            if env is not None:
                env_id = env.id
        task = run_test_suite_task.delay(suite.id, env_id, extra_vars, stop_on_failure, retry_times)
        bind_task_owner(task.id, request.user.id)
        return Response({
            "status": "pending",
            "task_id": task.id,
            "message": "测试套件任务已进入队列",
            "retry_times": retry_times,
            "max_attempts_per_case": retry_times + 1,
        })

    @action(detail=True, methods=["get"])
    def export_locust(self, request, pk=None):
        suite = self.get_object()
        env = EnvConfig.objects.filter(project=suite.project, is_default=True).order_by("-created_at").first()
        base_url = env.base_url if env and env.base_url else None
        code = generate_locust_code_for_suite(suite, base_url=base_url)
        filename = f"locust_suite_{suite.id}_{self.sanitize_filename(suite.name)}.py"
        resp = HttpResponse(code, content_type="text/x-python; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @action(detail=True, methods=["get"])
    def runs(self, request, pk=None):
        suite = self.get_object()
        runs = suite.runs.all().order_by("-created_at")[:50]
        serializer = SuiteRunSerializer(runs, many=True)
        return Response(serializer.data)
