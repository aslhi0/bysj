import yaml
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import TestCase
from .openapi_import import import_from_spec, load_spec_dict
from .run_service import execute_case_record
from .serializers import OpenAPIImportSerializer, TestCaseSerializer, TestRecordSerializer


class TestCaseViewSet(viewsets.ModelViewSet):
    queryset = TestCase.objects.select_related('project').all()
    serializer_class = TestCaseSerializer

    @action(detail=True, methods=['post'], url_path='run')
    def run(self, request, pk=None):
        case = self.get_object()
        extra = {}
        if isinstance(request.data, dict):
            raw = request.data.get('variables')
            if isinstance(raw, dict):
                extra = raw
        record = execute_case_record(case, extra)

        return Response(
            {
                'record_id': record.id,
                'status': record.status,
                'elapsed_time': round(record.elapsed_time, 4),
                'result_log': record.result_log,
            }
        )

    @action(detail=True, methods=['get'], url_path='records')
    def list_records(self, request, pk=None):
        case = self.get_object()
        raw = request.query_params.get('limit', '50')
        try:
            n = max(1, min(int(raw), 100))
        except ValueError:
            n = 50
        qs = case.records.order_by('-created_at')[:n]
        return Response(TestRecordSerializer(qs, many=True).data)

    @action(detail=False, methods=['post'], url_path='import-openapi')
    def import_openapi(self, request):
        ser = OpenAPIImportSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            spec = load_spec_dict(
                spec=data.get('spec'),
                spec_url=data.get('spec_url'),
                spec_yaml=data.get('spec_yaml'),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except yaml.YAMLError as exc:
            return Response({'detail': f'YAML 解析失败: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        result = import_from_spec(spec, data['project'])
        return Response(result, status=status.HTTP_201_CREATED)
