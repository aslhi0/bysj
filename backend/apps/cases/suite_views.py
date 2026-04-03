import re
from urllib.parse import quote

from django.http import HttpResponse
from django.utils.text import slugify
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.runs.models import TestRecord

from .locust_export import build_locust_script
from .models import SuiteRun, TestSuite
from .run_service import execute_case_record
from .serializers import SuiteRunSerializer, TestSuiteSerializer


class TestSuiteViewSet(viewsets.ModelViewSet):
    queryset = (
        TestSuite.objects.select_related('project')
        .prefetch_related('suite_cases__testcase')
        .all()
    )
    serializer_class = TestSuiteSerializer

    @action(detail=True, methods=['post'], url_path='run')
    def run(self, request, pk=None):
        suite = self.get_object()
        body = request.data if isinstance(request.data, dict) else {}
        extra = body.get('variables') or {}
        if not isinstance(extra, dict):
            extra = {}
        stop_on_failure = bool(body.get('stop_on_failure', False))

        suite_vars = suite.variables if isinstance(suite.variables, dict) else {}
        merged = {**suite_vars, **extra}

        results: list[dict] = []
        passed = failed = 0
        for sc in suite.suite_cases.select_related('testcase').order_by('order', 'id'):
            case = sc.testcase
            rec = execute_case_record(case, merged)
            ok = rec.status == TestRecord.Status.SUCCESS
            if ok:
                passed += 1
            else:
                failed += 1
            results.append(
                {
                    'case_id': case.id,
                    'case_title': case.title,
                    'record_id': rec.id,
                    'status': rec.status,
                    'elapsed_time': round(rec.elapsed_time, 4),
                }
            )
            if stop_on_failure and not ok:
                break

        summary = {
            'total': len(results),
            'passed': passed,
            'failed': failed,
        }
        suite_run = SuiteRun.objects.create(
            suite=suite,
            stop_on_failure=stop_on_failure,
            summary=summary,
            results=results,
        )

        return Response(
            {
                'suite_id': suite.id,
                'suite_run_id': suite_run.id,
                'summary': summary,
                'results': results,
            }
        )

    @action(detail=True, methods=['get'], url_path='runs')
    def list_runs(self, request, pk=None):
        suite = self.get_object()
        limit = request.query_params.get('limit', '50')
        try:
            n = max(1, min(int(limit), 200))
        except ValueError:
            n = 50
        qs = suite.suite_runs.order_by('-created_at')[:n]
        return Response(SuiteRunSerializer(qs, many=True).data)

    @action(detail=True, methods=['get'], url_path='export_locust')
    def export_locust(self, request, pk=None):
        suite = self.get_object()
        py = build_locust_script(suite)
        resp = HttpResponse(py, content_type='text/x-python; charset=utf-8')
        slug = slugify(suite.name) or 'suite'
        ascii_name = f'locust_{suite.id}_{slug}.py'
        display = re.sub(r'[/\\:*?"<>|\r\n]', '_', suite.name).strip() or 'suite'
        if len(display) > 120:
            display = display[:120]
        utf_name = f'locust_{suite.id}_{display}.py'
        star = quote(utf_name, safe='')
        resp['Content-Disposition'] = (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{star}'
        )
        return resp
