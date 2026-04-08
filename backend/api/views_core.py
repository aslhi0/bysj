"""Core management viewsets: project/env/audit."""

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .audit_utils import audit_log
from .models import EnvConfig, Project, ProjectMember
from .query_utils import apply_project_access_filter
from .serializers import (
    AuditLogSerializer,
    EnvConfigSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
)
from .view_utils import apply_limit_from_request


class EnvConfigViewSet(viewsets.ModelViewSet):
    queryset = EnvConfig.objects.select_related("project", "project__owner").all()
    serializer_class = EnvConfigSerializer
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

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).order_by("-id")
        qs = apply_limit_from_request(qs, request)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def _ensure_admin(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser):
            raise PermissionDenied("仅管理员可进行环境配置操作")

    def perform_create(self, serializer):
        self._ensure_admin()
        obj = serializer.save()
        audit_log(self.request.user, obj, ADDITION, f"创建环境: {obj.name}")

    def perform_update(self, serializer):
        self._ensure_admin()
        obj = serializer.save()
        audit_log(self.request.user, obj, CHANGE, f"更新环境: {obj.name}")

    def perform_destroy(self, instance):
        self._ensure_admin()
        audit_log(self.request.user, instance, DELETION, f"删除环境: {instance.name}")
        instance.delete()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LogEntry.objects.select_related("user", "content_type").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().order_by("-action_time")
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(user=user)
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
        qs = apply_limit_from_request(qs, request)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related("owner").all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        qs = apply_project_access_filter(qs, user, "")
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def _ensure_admin(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser):
            raise PermissionDenied("仅管理员可进行项目配置操作")

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).order_by("-id")
        qs = apply_limit_from_request(qs, request)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        self._ensure_admin()
        owner = self.request.user
        owner_id = self.request.data.get("owner")
        if owner_id:
            User = get_user_model()
            target = User.objects.filter(id=owner_id).first()
            if target is None:
                raise ValidationError("owner 不存在")
            owner = target
        obj = serializer.save(owner=owner)
        audit_log(self.request.user, obj, ADDITION, f"创建项目: {obj.name}")

    def perform_update(self, serializer):
        self._ensure_admin()
        obj = serializer.save()
        audit_log(self.request.user, obj, CHANGE, f"更新项目: {obj.name}")

    def perform_destroy(self, instance):
        self._ensure_admin()
        audit_log(self.request.user, instance, DELETION, f"删除项目: {instance.name}")
        instance.delete()

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        self._ensure_admin()
        project = self.get_object()
        qs = ProjectMember.objects.filter(project=project).select_related("user").order_by("-id")
        return Response(ProjectMemberSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        self._ensure_admin()
        project = self.get_object()
        user_id = request.data.get("user_id")
        if not user_id:
            raise ValidationError("缺少 user_id")
        User = get_user_model()
        user = User.objects.filter(id=user_id).first()
        if user is None:
            raise ValidationError("user 不存在")
        pm, _ = ProjectMember.objects.update_or_create(
            project=project,
            user=user,
            defaults={"is_active": True},
        )
        return Response(ProjectMemberSerializer(pm).data)

    @action(detail=True, methods=["post"])
    def remove_member(self, request, pk=None):
        self._ensure_admin()
        project = self.get_object()
        user_id = request.data.get("user_id")
        if not user_id:
            raise ValidationError("缺少 user_id")
        ProjectMember.objects.filter(project=project, user_id=user_id).delete()
        return Response({"detail": "成员已移除"})
