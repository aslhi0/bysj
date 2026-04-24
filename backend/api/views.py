"""Public aggregate exports for API viewsets and auth/task endpoints."""
from celery.result import AsyncResult
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .task_tracker import get_task_owner
from .views_case import TestCaseViewSet
from .views_core import (
    AuditLogViewSet,
    EnvConfigViewSet,
    ProjectViewSet,
)
from .views_records_perf import PerfRecordViewSet, SuiteRunViewSet, TestRecordViewSet
from .views_suite import TestSuiteViewSet


def _sanitize_task_result(result_payload):
    if not isinstance(result_payload, dict):
        return {"status": "error", "message": str(result_payload)[:500]}
    allowed_keys = {
        "status",
        "record_id",
        "suite_run_id",
        "perf_record_id",
        "elapsed_time",
        "summary",
        "message",
        "attempts",
        "attempts_made",
        "retries_used",
    }
    sanitized = {k: v for k, v in result_payload.items() if k in allowed_keys}
    if "status" not in sanitized:
        sanitized["status"] = "error"
    if "message" in sanitized and sanitized["message"] is not None:
        sanitized["message"] = str(sanitized["message"])[:500]
    return sanitized


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def task_status(request, task_id):
    from django.conf import settings

    owner_id = get_task_owner(task_id)
    eager_mode = bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)) or bool(
        getattr(settings, "CELERY_ALWAYS_EAGER", False)
    )
    if owner_id is None:
        # eager 模式（本地 DEBUG / 测试）下任务是同步执行的，某些 cache backend（LocMem）
        # 在 web 请求与 celery 任务不在同一进程上下文时会丢失写入；放宽 owner 强校验，
        # 同时仅在任务 ready 的前提下返回结果，避免成为枚举任务 id 的侧信道。
        if not eager_mode:
            return Response({"detail": "任务不存在或已过期"}, status=status.HTTP_404_NOT_FOUND)
    else:
        if int(owner_id) != int(request.user.id):
            return Response({"detail": "无权限查看该任务"}, status=status.HTTP_403_FORBIDDEN)

    result = AsyncResult(task_id)
    ready = result.ready()
    if owner_id is None and not ready:
        # eager 模式但无 owner 且未完成：大概率是 id 不存在，按 404 返回
        return Response({"detail": "任务不存在或已过期"}, status=status.HTTP_404_NOT_FOUND)
    sanitized_result = _sanitize_task_result(result.result) if ready else None
    if ready and isinstance(sanitized_result, dict):
        biz_status = str(sanitized_result.get("status") or "error").lower()
    else:
        state = str(result.status or "").upper()
        if state in {"PENDING", "RECEIVED", "STARTED", "RETRY"}:
            biz_status = "pending"
        else:
            biz_status = state.lower() or "pending"
    return Response(
        {
            "task_id": task_id,
            "status": biz_status,
            "task_state": result.status,
            "ready": ready,
            "result": sanitized_result,
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


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "is_staff": bool(user.is_staff),
                "is_superuser": bool(user.is_superuser),
            }
        )


class AdminUserListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        User = get_user_model()
        q = (request.query_params.get("q") or "").strip()
        qs = User.objects.all().order_by("id")
        if q:
            qs = qs.filter(username__icontains=q)
        data = [
            {
                "id": u.id,
                "username": u.username,
                "is_staff": bool(u.is_staff),
                "is_superuser": bool(u.is_superuser),
            }
            for u in qs[:500]
        ]
        return Response(data)
