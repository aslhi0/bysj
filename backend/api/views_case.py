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
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .audit_utils import audit_log
from .crypto_utils import decrypt_json
from .engine import validate_outbound_http_url
from .flaky_analysis import (
    build_execution_stats_for_case,
    build_strategy_comparison,
    compute_flaky_analysis_for_case,
)
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

    def _resolve_env_id(self, case, env_id):
        if env_id:
            env_id = EnvConfig.objects.filter(project=case.project, id=env_id).values_list("id", flat=True).first()
        if not env_id:
            env = EnvConfig.objects.filter(project=case.project, is_default=True).order_by("-created_at").first()
            if env is not None:
                env_id = env.id
        return env_id

    def _compute_flaky_analysis(self, case, *, target_success=0.95, max_attempts=3):
        return compute_flaky_analysis_for_case(case, target_success=target_success, max_attempts=max_attempts)

    def perform_create(self, serializer):
        self._ensure_admin()
        with transaction.atomic():
            case = serializer.save()
            self.create_version(case, self.request.user)
        audit_log(self.request.user, case, ADDITION, f"创建用例: {case.title}")

    def perform_update(self, serializer):
        self._ensure_admin()
        with transaction.atomic():
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
        with transaction.atomic():
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
        retry_times = request.data.get("retry_times", 0)
        try:
            retry_times = int(retry_times)
        except Exception:
            retry_times = 0
        if retry_times < 0 or retry_times > 3:
            return Response({"detail": "retry_times 超出范围（0-3）"}, status=status.HTTP_400_BAD_REQUEST)
        env_id = self._resolve_env_id(case, request.data.get("env_id"))

        task = run_test_case_task.delay(case.id, env_id, extra_vars, retry_times)
        bind_task_owner(task.id, request.user.id)
        return Response(
            {
                "status": "pending",
                "task_id": task.id,
                "message": "测试任务已进入队列",
                "retry_times": retry_times,
                "max_attempts": retry_times + 1,
            }
        )

    @action(detail=True, methods=["post"])
    def run_smart(self, request, pk=None):
        """自适应执行策略：按 Flaky 分析给出的建议重试次数入队执行。"""
        case = self.get_object()
        extra_vars = request.data.get("variables", {})
        env_id = self._resolve_env_id(case, request.data.get("env_id"))

        try:
            target_success = float(request.data.get("target_success", 0.95))
        except Exception:
            target_success = 0.95
        target_success = max(0.80, min(target_success, 0.99))

        try:
            max_attempts = int(request.data.get("max_attempts", 3))
        except Exception:
            max_attempts = 3
        max_attempts = max(1, min(max_attempts, 4))

        strategy = self._compute_flaky_analysis(
            case,
            target_success=target_success,
            max_attempts=max_attempts,
        )
        retry_times = int(strategy.get("suggested_retries", 0))
        retry_times = max(0, min(retry_times, 3))

        task = run_test_case_task.delay(case.id, env_id, extra_vars, retry_times)
        bind_task_owner(task.id, request.user.id)
        return Response(
            {
                "status": "pending",
                "task_id": task.id,
                "message": "自适应执行任务已进入队列",
                "retry_times": retry_times,
                "max_attempts": retry_times + 1,
                "strategy": strategy,
            }
        )

    @action(detail=True, methods=["post"])
    def run_perf(self, request, pk=None):
        case = self.get_object()
        steps = case.steps if isinstance(case.steps, list) else []
        has_http_step = any(isinstance(step, dict) and step.get("type") == "http" for step in steps)
        if not has_http_step:
            return Response(
                {"detail": "压测仅支持包含 HTTP 步骤的用例；当前用例为 UI 流程，无法生成有效 RPS。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
            merged_vars.update(decrypt_json(case.variables))
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

    @action(detail=True, methods=["get"])
    def quality_insight(self, request, pk=None):
        """Explainable quality score for demo/reporting in UI."""
        case = self.get_object()
        steps = case.steps if isinstance(case.steps, list) else []

        http_steps = [s for s in steps if isinstance(s, dict) and s.get("type") == "http"]
        ui_steps = [s for s in steps if isinstance(s, dict) and s.get("type") == "ui"]
        total_steps = len(steps)

        http_count = len(http_steps)
        ui_count = len(ui_steps)
        mixed_bonus = 10 if http_count and ui_count else 0

        http_with_assert = sum(1 for s in http_steps if isinstance(s.get("assertions"), list) and s.get("assertions"))
        http_with_capture = sum(1 for s in http_steps if isinstance(s.get("capture"), dict) and s.get("capture"))
        ui_wait_steps = sum(1 for s in ui_steps if s.get("action") == "wait_visible")

        assert_ratio = (http_with_assert / http_count) if http_count else 1.0
        capture_ratio = (http_with_capture / http_count) if http_count else 1.0
        ui_wait_ratio = (ui_wait_steps / ui_count) if ui_count else 1.0

        design_score = int(
            max(
                0,
                min(
                    100,
                    40 * assert_ratio + 30 * capture_ratio + 20 * ui_wait_ratio + mixed_bonus,
                ),
            )
        )

        recent_records = list(case.records.all().order_by("-created_at")[:20])
        rec_total = len(recent_records)
        rec_success = sum(1 for r in recent_records if r.status == "success")
        rec_fail = sum(1 for r in recent_records if r.status in {"failed", "error"})
        success_rate = (rec_success / rec_total) if rec_total else 0.0
        avg_elapsed = (sum(float(r.elapsed_time or 0.0) for r in recent_records) / rec_total) if rec_total else 0.0
        elapsed_penalty = 0
        if avg_elapsed > 10:
            elapsed_penalty = min(20, int(avg_elapsed - 10))
        reliability_score = int(max(0, min(100, 100 * success_rate - elapsed_penalty)))

        recent_perf = list(case.perf_records.all().order_by("-created_at")[:10])
        perf_total = len(recent_perf)
        perf_good = sum(1 for p in recent_perf if p.status == "finished")
        perf_bad = sum(1 for p in recent_perf if p.status in {"error", "timeout"})
        perf_rate = (perf_good / perf_total) if perf_total else 0.0
        has_tags = 1 if isinstance(case.tags, list) and case.tags else 0
        has_vars = 1 if isinstance(case.variables, dict) and case.variables else 0
        operability_score = int(
            max(
                0,
                min(
                    100,
                    30 * has_tags + 20 * has_vars + 20 * perf_rate + 30 * (1 if total_steps > 0 else 0),
                ),
            )
        )

        overall = int(round(0.45 * design_score + 0.40 * reliability_score + 0.15 * operability_score))
        if overall >= 85:
            level = "A"
            level_label = "优秀"
        elif overall >= 70:
            level = "B"
            level_label = "良好"
        elif overall >= 55:
            level = "C"
            level_label = "可改进"
        else:
            level = "D"
            level_label = "高风险"

        suggestions = []
        if http_count and assert_ratio < 0.7:
            suggestions.append("HTTP 步骤断言覆盖较低，建议补充状态码/JSON/Schema 断言。")
        if http_count and capture_ratio < 0.3:
            suggestions.append("建议增加变量提取(capture)用于链路校验，提高业务真实性。")
        if ui_count and ui_wait_ratio < 0.3:
            suggestions.append("UI 步骤缺少 wait_visible，建议增加显式等待提升稳定性。")
        if rec_total < 3:
            suggestions.append("执行样本不足，建议至少运行 3~5 次后再评估稳定性。")
        if rec_total >= 3 and success_rate < 0.8:
            suggestions.append("近期成功率偏低，建议排查环境波动和断言过严的问题。")
        if perf_total == 0 and http_count:
            suggestions.append("尚无压测基线，建议对关键 HTTP 用例进行一次性能测试。")
        if not suggestions:
            suggestions.append("该用例设计较完整，可继续扩大样本规模形成基线数据。")

        return Response(
            {
                "case_id": case.id,
                "case_title": case.title,
                "overall_score": overall,
                "level": level,
                "level_label": level_label,
                "dimensions": {
                    "design_score": design_score,
                    "reliability_score": reliability_score,
                    "operability_score": operability_score,
                },
                "metrics": {
                    "steps_total": total_steps,
                    "http_steps": http_count,
                    "ui_steps": ui_count,
                    "assertion_coverage": round(assert_ratio, 4),
                    "capture_coverage": round(capture_ratio, 4),
                    "ui_wait_coverage": round(ui_wait_ratio, 4),
                    "recent_run_total": rec_total,
                    "recent_run_success": rec_success,
                    "recent_run_failed": rec_fail,
                    "recent_success_rate": round(success_rate, 4),
                    "recent_avg_elapsed": round(avg_elapsed, 4),
                    "recent_perf_total": perf_total,
                    "recent_perf_finished": perf_good,
                    "recent_perf_bad": perf_bad,
                },
                "suggestions": suggestions,
            }
        )

    @action(detail=True, methods=["get"])
    def flaky_insight(self, request, pk=None):
        """Flaky 分析：Wilson 上界、状态切换率与 EWMA 趋势融合为风险分与重试建议。"""
        case = self.get_object()
        try:
            target_success = float(request.query_params.get("target_success", 0.95))
        except Exception:
            target_success = 0.95
        target_success = max(0.80, min(target_success, 0.99))
        try:
            max_attempts = int(request.query_params.get("max_attempts", 3))
        except Exception:
            max_attempts = 3
        max_attempts = max(1, min(max_attempts, 4))

        data = self._compute_flaky_analysis(
            case,
            target_success=target_success,
            max_attempts=max_attempts,
        )
        return Response(
            {
                "case_id": case.id,
                "case_title": case.title,
                **data,
            }
        )

    @action(detail=True, methods=["get"])
    def experiment_summary(self, request, pk=None):
        """实验对比摘要：执行统计、Flaky 分析、固定重试 vs run_smart 策略行（便于论文制表）。"""
        case = self.get_object()
        try:
            target_success = float(request.query_params.get("target_success", 0.95))
        except Exception:
            target_success = 0.95
        target_success = max(0.80, min(target_success, 0.99))
        try:
            max_attempts = int(request.query_params.get("max_attempts", 3))
        except Exception:
            max_attempts = 3
        max_attempts = max(1, min(max_attempts, 4))

        flaky = self._compute_flaky_analysis(case, target_success=target_success, max_attempts=max_attempts)
        execution_stats = build_execution_stats_for_case(case)
        strategy_comparison = build_strategy_comparison(flaky)

        return Response(
            {
                "case_id": case.id,
                "case_title": case.title,
                "execution_stats": execution_stats,
                "flaky_analysis": flaky,
                "strategy_comparison": strategy_comparison,
                "notes": {
                    "fixed_rows": "retry_times 0~3 对应 POST /cases/{id}/run/ 的手动重试上限；投影基于 Wilson 失败率上界与独立尝试假设。",
                    "adaptive_row": "与 POST /cases/{id}/run_smart/ 使用的建议一致；请在相同 target_success/max_attempts 下对比。",
                },
            }
        )

    def _validate_openapi_params(self, request, max_spec_chars):
        """验证 OpenAPI 导入参数"""
        project_id = request.data.get("project")
        spec = request.data.get("spec")
        spec_url = request.data.get("spec_url")
        spec_yaml = request.data.get("spec_yaml")
        on_conflict = str(request.data.get("on_conflict", "skip")).strip().lower() or "skip"

        if not project_id:
            return None, Response({"detail": "缺少项目 ID"}, status=status.HTTP_400_BAD_REQUEST)
        if spec is None and not spec_url and not spec_yaml:
            return None, Response({"detail": "缺少 spec / spec_url / spec_yaml"}, status=status.HTTP_400_BAD_REQUEST)

        project = Project.objects.filter(id=project_id, owner=request.user).first()
        if project is None:
            return None, Response({"detail": "项目不存在或无权限"}, status=status.HTTP_404_NOT_FOUND)

        if spec_url is not None and not isinstance(spec_url, str):
            return None, Response({"detail": "spec_url 必须是字符串"}, status=status.HTTP_400_BAD_REQUEST)
        if spec_yaml is not None and not isinstance(spec_yaml, str):
            return None, Response({"detail": "spec_yaml 必须是字符串"}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(spec_url, str) and len(spec_url) > 2000:
            return None, Response({"detail": "spec_url 过长"}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(spec_yaml, str) and len(spec_yaml) > max_spec_chars:
            return None, Response({"detail": "spec_yaml 体积过大"}, status=status.HTTP_400_BAD_REQUEST)
        if on_conflict not in {"skip", "overwrite"}:
            return None, Response({"detail": "on_conflict 仅支持 skip / overwrite"}, status=status.HTTP_400_BAD_REQUEST)

        return {
            "project": project,
            "spec": spec,
            "spec_url": spec_url,
            "spec_yaml": spec_yaml,
            "on_conflict": on_conflict,
        }, None

    def _fetch_openapi_spec(self, spec, spec_url, spec_yaml, project, max_spec_chars):
        """获取并解析 OpenAPI 规范"""
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
                    return None, Response(
                        {"detail": "项目未配置可用环境 base_url，无法通过 spec_url 导入"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    validate_outbound_http_url(str(spec_url), allowed_hosts=allow_hosts)
                    resp = requests.get(str(spec_url), timeout=(5, 10), allow_redirects=False, headers={"Accept": "application/json"})
                    resp.raise_for_status()
                    body = resp.text or ""
                    if len(body) > max_spec_chars:
                        return None, Response({"detail": "远程 spec 体积过大"}, status=status.HTTP_400_BAD_REQUEST)
                    content_type = str(resp.headers.get("Content-Type", "")).lower()
                    spec = yaml.safe_load(body) if "yaml" in content_type or body.lstrip().startswith(("openapi:", "swagger:")) else resp.json()
                except Exception as e:
                    return None, Response({"detail": f"拉取或解析 spec_url 失败: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            elif spec_yaml:
                try:
                    spec = yaml.safe_load(spec_yaml)
                except Exception as e:
                    return None, Response({"detail": f"解析 spec_yaml 失败: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(spec, str):
            if len(spec) > max_spec_chars:
                return None, Response({"detail": "spec 体积过大"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                spec = json.loads(spec)
            except Exception as e:
                return None, Response({"detail": f"spec 不是合法 JSON: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(spec, dict):
            return None, Response({"detail": "spec 必须是 JSON 对象"}, status=status.HTTP_400_BAD_REQUEST)

        return spec, None

    def _build_schema_helpers(self, spec):
        """构建 OpenAPI schema 解析辅助函数"""
        def _resolve_ref(ref):
            if not isinstance(ref, str) or not ref.startswith("#/"):
                return {}
            node = spec
            for p in ref[2:].split("/"):
                if not isinstance(node, dict):
                    return {}
                node = node.get(p)
            return node if isinstance(node, dict) else {}

        def _from_schema(schema_obj, depth=0, seen_refs=None):
            """Build a request body skeleton from OpenAPI schema recursively."""
            if not isinstance(schema_obj, dict):
                return {}
            if depth > 8:
                return {}
            seen_refs = seen_refs or set()

            if "example" in schema_obj:
                return schema_obj.get("example")
            if "default" in schema_obj:
                return schema_obj.get("default")
            enum_vals = schema_obj.get("enum")
            if isinstance(enum_vals, list) and enum_vals:
                return enum_vals[0]

            ref = schema_obj.get("$ref")
            if isinstance(ref, str):
                if ref in seen_refs:
                    return {}
                target = _resolve_ref(ref)
                return _from_schema(target, depth + 1, seen_refs | {ref})

            for key in ("oneOf", "anyOf"):
                variants = schema_obj.get(key)
                if isinstance(variants, list) and variants:
                    candidate = variants[0] if isinstance(variants[0], dict) else {}
                    return _from_schema(candidate, depth + 1, seen_refs)
            all_of = schema_obj.get("allOf")
            if isinstance(all_of, list) and all_of:
                merged = {}
                for part in all_of:
                    v = _from_schema(part if isinstance(part, dict) else {}, depth + 1, seen_refs)
                    if isinstance(v, dict):
                        merged.update(v)
                if merged:
                    return merged

            typ = schema_obj.get("type")
            fmt = str(schema_obj.get("format", "")).lower()
            if typ == "object" or (typ is None and isinstance(schema_obj.get("properties"), dict)):
                props = schema_obj.get("properties", {})
                if not isinstance(props, dict):
                    return {}
                result = {}
                for k, sub in props.items():
                    if isinstance(sub, dict):
                        result[k] = _from_schema(sub, depth + 1, seen_refs)
                    else:
                        result[k] = ""
                return result
            if typ == "array":
                items = schema_obj.get("items")
                if isinstance(items, dict):
                    return [_from_schema(items, depth + 1, seen_refs)]
                return []
            if typ == "integer":
                return 0
            if typ == "number":
                return 0
            if typ == "boolean":
                return False
            if typ == "string":
                if fmt in {"date-time"}:
                    return "2026-01-01T00:00:00Z"
                if fmt in {"date"}:
                    return "2026-01-01"
                if fmt in {"email"}:
                    return "demo@example.com"
                if fmt in {"uuid"}:
                    return "00000000-0000-0000-0000-000000000000"
                return ""
            return {}

        return _from_schema

    def _create_test_case_from_openapi(self, path, method, info, project, on_conflict, _from_schema):
        """从 OpenAPI 路径创建测试用例"""
        title = f"{method.upper()} {path} - {str(info.get('summary', 'OpenAPI Import'))[:120]}"
        existing = TestCase.objects.filter(project=project, title=title).first()
        if existing and on_conflict == "skip":
            return False

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
        return True

    @action(detail=False, methods=["post"], url_path="import-openapi")
    def import_openapi(self, request):
        self._ensure_admin()
        max_spec_chars = 1_500_000
        max_paths = 500
        max_cases_created = 1000

        # 验证参数
        params, error_response = self._validate_openapi_params(request, max_spec_chars)
        if error_response:
            return error_response

        # 获取并解析 spec
        spec, error_response = self._fetch_openapi_spec(
            params["spec"], params["spec_url"], params["spec_yaml"],
            params["project"], max_spec_chars
        )
        if error_response:
            return error_response

        # 验证 paths
        paths = spec.get("paths", {})
        if not isinstance(paths, dict):
            return Response({"detail": "spec.paths 必须是对象"}, status=status.HTTP_400_BAD_REQUEST)
        if len(paths) > max_paths:
            return Response({"detail": f"paths 数量过多，最多允许 {max_paths} 条"}, status=status.HTTP_400_BAD_REQUEST)

        # 构建 schema 解析器
        _from_schema = self._build_schema_helpers(spec)

        # 遍历并创建用例（原子事务：中途失败则整体回滚，避免部分脏数据污染项目）
        count = 0
        truncated = False
        allowed_methods = {"get", "post", "put", "delete", "patch", "head", "options"}

        with transaction.atomic():
            for path, methods in paths.items():
                if not isinstance(path, str) or not path.startswith("/") or len(path) > 500 or not isinstance(methods, dict):
                    continue
                for method, info in methods.items():
                    if str(method).lower() not in allowed_methods:
                        continue
                    if not isinstance(info, dict):
                        info = {}

                    created = self._create_test_case_from_openapi(
                        path, method, info, params["project"],
                        params["on_conflict"], _from_schema
                    )
                    if created:
                        count += 1
                        if count >= max_cases_created:
                            truncated = True
                            break
                if truncated:
                    break

        if count > 0:
            suffix = '（已截断）' if truncated else ''
            audit_log(
                request.user,
                params["project"],
                ADDITION,
                f'OpenAPI 批量导入用例 {count} 条{suffix}，on_conflict={params["on_conflict"]}',
            )

        return Response({"count": count, "truncated": truncated})
