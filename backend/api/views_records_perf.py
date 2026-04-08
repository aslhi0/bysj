"""Read-only viewsets for records, suite runs and performance reports."""
import os

from django.conf import settings
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .crypto_utils import decrypt_json
from .locust_codegen import generate_locust_code
from .models import TestRecord, SuiteRun, PerfRecord, EnvConfig
from .query_utils import apply_project_access_filter
from .report_utils import (
    build_test_record_report_html,
    build_test_record_report_json_payload,
    sanitize_filename,
    read_csv_rows,
    parse_int,
    parse_float,
    pick_aggregated_row,
)
from .serializers import TestRecordSerializer, SuiteRunSerializer, PerfRecordSerializer
from .tasks import reconcile_stale_perf_records


class TestRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestRecord.objects.select_related("case", "case__project", "case__project__owner").all().order_by("-created_at")
    serializer_class = TestRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        return apply_project_access_filter(qs, user, "case__project").order_by("-created_at")

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        record = self.get_object()
        screenshot_url = None
        if record.screenshot:
            try:
                screenshot_url = request.build_absolute_uri(record.screenshot.url)
            except Exception:
                screenshot_url = record.screenshot.url

        fmt = (request.query_params.get("format") or "").strip().lower()
        if fmt == "json":
            payload = build_test_record_report_json_payload(record, screenshot_url)
            resp = Response(payload)
            if request.query_params.get("download") in {"1", "true", "yes"}:
                resp["Content-Disposition"] = f'attachment; filename="record_{record.id}.json"'
            return resp

        html_text = build_test_record_report_html(record, screenshot_url)
        resp = HttpResponse(html_text, content_type="text/html; charset=utf-8")
        if request.query_params.get("download") in {"1", "true", "yes"}:
            resp["Content-Disposition"] = f'attachment; filename="record_{record.id}.html"'
        return resp

    @action(detail=False, methods=["get"])
    def recent(self, request):
        records = self.get_queryset()[:10]
        serializer = self.get_serializer(records, many=True)
        return Response(serializer.data)


class SuiteRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SuiteRun.objects.select_related("suite", "suite__project", "suite__project__owner").all().order_by("-created_at")
    serializer_class = SuiteRunSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        return apply_project_access_filter(qs, user, "suite__project").order_by("-created_at")

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        run = self.get_object()
        suite = run.suite
        payload = {
            "suite_run_id": run.id,
            "suite_id": suite.id,
            "suite_name": suite.name,
            "project_id": suite.project_id,
            "project_name": suite.project.name,
            "stop_on_failure": run.stop_on_failure,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "summary": run.summary or {},
            "results": run.results or [],
        }
        resp = Response(payload)
        if request.query_params.get("download") in {"1", "true", "yes"}:
            resp["Content-Disposition"] = f'attachment; filename="suite_run_{run.id}.json"'
        return resp


class PerfRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PerfRecord.objects.select_related("case", "case__project", "case__project__owner").all().order_by("-created_at")
    serializer_class = PerfRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 自愈历史遗留的长时间 running/queued 记录，避免前端永久转圈。
        try:
            reconcile_stale_perf_records()
        except Exception:
            pass
        qs = super().get_queryset()
        user = self.request.user
        return apply_project_access_filter(qs, user, "case__project").order_by("-created_at")

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        record = self.get_object()
        if not record.csv_prefix:
            return Response({"detail": "该记录暂无 CSV 输出前缀"}, status=status.HTTP_404_NOT_FOUND)
        base_dir = os.path.join(str(getattr(settings, "MEDIA_ROOT", os.getcwd())), "perf", str(record.id))
        prefix = record.csv_prefix
        stats_path = os.path.join(base_dir, f"{prefix}_stats.csv")
        history_path = os.path.join(base_dir, f"{prefix}_stats_history.csv")

        stats_rows = read_csv_rows(stats_path)
        history_rows = read_csv_rows(history_path)
        agg = pick_aggregated_row(stats_rows)
        if not agg and not history_rows:
            return Response(
                {"detail": "未找到压测 CSV 文件，请确认压测是否已完成并生成 CSV"},
                status=status.HTTP_404_NOT_FOUND,
            )

        summary = {}
        if agg:
            req_count = parse_int(agg.get("Request Count") or agg.get("request_count") or agg.get("Requests"))
            fail_count = parse_int(agg.get("Failure Count") or agg.get("failure_count") or agg.get("Failures"))
            rps = parse_float(agg.get("Requests/s") or agg.get("requests/s") or agg.get("RPS"))
            fps = parse_float(agg.get("Failures/s") or agg.get("failures/s") or agg.get("Failures/s"))
            avg_rt = parse_float(agg.get("Average Response Time") or agg.get("avg_response_time") or agg.get("Average"))
            med_rt = parse_float(agg.get("Median Response Time") or agg.get("median_response_time") or agg.get("Median"))
            min_rt = parse_float(agg.get("Min Response Time") or agg.get("min_response_time") or agg.get("Min"))
            max_rt = parse_float(agg.get("Max Response Time") or agg.get("max_response_time") or agg.get("Max"))
            fail_rate = (fail_count / req_count) if req_count else 0.0
            summary = {
                "requests": req_count,
                "failures": fail_count,
                "fail_rate": fail_rate,
                "rps": rps,
                "failures_per_sec": fps,
                "avg_rt_ms": avg_rt,
                "median_rt_ms": med_rt,
                "min_rt_ms": min_rt,
                "max_rt_ms": max_rt,
            }

        series = []
        for r in history_rows:
            name = (r.get("Name") or "").strip().lower()
            typ = (r.get("Type") or "").strip().lower()
            if name and name not in {"aggregated", "total"} and typ and typ not in {"aggregated", "total"}:
                continue
            ts = parse_int(r.get("Timestamp") or r.get("timestamp"))
            uc = parse_int(r.get("User Count") or r.get("user_count"))
            rps = parse_float(r.get("Requests/s") or r.get("requests/s"))
            fps = parse_float(r.get("Failures/s") or r.get("failures/s"))
            avg_rt = parse_float(r.get("Average Response Time") or r.get("Average"))
            med_rt = parse_float(r.get("Median Response Time") or r.get("Median"))
            series.append(
                {
                    "ts": ts,
                    "user_count": uc,
                    "rps": rps,
                    "failures_per_sec": fps,
                    "avg_rt_ms": avg_rt,
                    "median_rt_ms": med_rt,
                }
            )

        return Response(
            {
                "perf_record_id": record.id,
                "case_id": record.case_id,
                "csv_prefix": record.csv_prefix,
                "status": record.status,
                "summary": summary,
                "series": series,
                "files": {
                    "stats": os.path.exists(stats_path),
                    "history": os.path.exists(history_path),
                },
            }
        )

    @action(detail=True, methods=["get"])
    def locust(self, request, pk=None):
        perf_record = self.get_object()
        case = perf_record.case
        env = EnvConfig.objects.filter(project=case.project, is_default=True).order_by("-created_at").first()
        base_url = env.base_url if env and env.base_url else None

        merged_vars = {}
        if env and isinstance(env.variables, dict):
            merged_vars.update(decrypt_json(env.variables))
        if isinstance(case.variables, dict):
            merged_vars.update(case.variables)
        if base_url:
            merged_vars["base_url"] = base_url

        code = generate_locust_code(case, base_url=base_url, variables=merged_vars)
        filename = f"locust_perf_{perf_record.id}_{sanitize_filename(case.title, default='case')}.py"
        resp = HttpResponse(code, content_type="text/x-python; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
