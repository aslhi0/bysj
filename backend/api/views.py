import json

from celery.result import AsyncResult
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .audit_utils import audit_log
from .models import EnvConfig, Project
from .serializers import (
    AuditLogSerializer,
    CrontabScheduleSerializer,
    EnvConfigSerializer,
    PeriodicTaskSerializer,
    ProjectSerializer,
)
from .task_tracker import get_task_owner
from .views_cases_suites import TestCaseViewSet, TestSuiteViewSet
from .views_records_perf import PerfRecordViewSet, SuiteRunViewSet, TestRecordViewSet


class EnvConfigViewSet(viewsets.ModelViewSet):
    queryset = EnvConfig.objects.select_related("project", "project__owner").all()
    serializer_class = EnvConfigSerializer
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
        audit_log(self.request.user, obj, ADDITION, f"创建环境: {obj.name}")

    def perform_update(self, serializer):
        obj = serializer.save()
        audit_log(self.request.user, obj, CHANGE, f"更新环境: {obj.name}")

    def perform_destroy(self, instance):
        audit_log(self.request.user, instance, DELETION, f"删除环境: {instance.name}")
        instance.delete()


class CrontabScheduleViewSet(viewsets.ModelViewSet):
    queryset = CrontabSchedule.objects.all()
    serializer_class = CrontabScheduleSerializer
    permission_classes = [IsAuthenticated]


class PeriodicTaskViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = PeriodicTask.objects.all()
    serializer_class = PeriodicTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        oid = getattr(self.request.user, "id", None)
        if oid:
            qs = qs.filter(Q(description__contains=f'"owner_id": {oid}') | Q(description__contains=f'"owner_id":{oid}'))
        return qs

    def get_object(self):
        obj = super().get_object()
        oid = getattr(self.request.user, "id", None)
        if not oid:
            raise PermissionDenied("未登录")
        try:
            d = json.loads(obj.description or "{}")
        except Exception:
            d = {}
        owner_id = d.get("owner_id") if isinstance(d, dict) else None
        if owner_id != oid:
            raise PermissionDenied("无权限访问该定时任务")
        return obj

    def perform_update(self, serializer):
        obj = serializer.save()
        audit_log(self.request.user, obj, CHANGE, f"更新定时任务: {obj.name}")

    def perform_destroy(self, instance):
        audit_log(self.request.user, instance, DELETION, f"删除定时任务: {instance.name}")
        instance.delete()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LogEntry.objects.select_related("user", "content_type").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().filter(user=self.request.user).order_by("-action_time")
        action = self.request.query_params.get("action")
        model = self.request.query_params.get("model")
        q = self.request.query_params.get("q")
        if action in {"add", "change", "delete"}:
            m = {"add": ADDITION, "change": CHANGE, "delete": DELETION}
            qs = qs.filter(action_flag=m[action])
        if model:
            parts = str(model).split(".", 1)
            if len(parts) == 2:
                qs = qs.filter(content_type__app_label=parts[0], content_type__model=parts[1])
        if q:
            qs = qs.filter(Q(object_repr__icontains=q) | Q(change_message__icontains=q))
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
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


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related("owner").all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().filter(owner=self.request.user)
        q = self.request.query_params.get("q")
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
        obj = serializer.save(owner=self.request.user)
        audit_log(self.request.user, obj, ADDITION, f"创建项目: {obj.name}")

    def perform_update(self, serializer):
        obj = serializer.save()
        audit_log(self.request.user, obj, CHANGE, f"更新项目: {obj.name}")

    def perform_destroy(self, instance):
        audit_log(self.request.user, instance, DELETION, f"删除项目: {instance.name}")
        instance.delete()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def task_status(request, task_id):
    owner_id = get_task_owner(task_id)
    if owner_id is None:
        return Response({"detail": "任务不存在或已过期"}, status=status.HTTP_404_NOT_FOUND)
    if int(owner_id) != int(request.user.id):
        return Response({"detail": "无权限查看该任务"}, status=status.HTTP_403_FORBIDDEN)
    result = AsyncResult(task_id)
    return Response(
        {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "result": result.result if result.ready() else None,
        }
    )


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not username or not password:
            return Response({"detail": "缺少 username 或 password"}, status=status.HTTP_400_BAD_REQUEST)
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            return Response({"detail": "用户名已存在"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(password, user=User(username=username))
        except ValidationError as e:
            return Response({"detail": list(getattr(e, "messages", []) or ["密码不符合安全要求"])}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.create_user(username=username, password=password)
        return Response({"id": user.id, "username": user.username}, status=status.HTTP_201_CREATED)
