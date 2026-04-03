from rest_framework import serializers

from apps.projects.models import Project
from apps.runs.models import TestRecord

from .models import SuiteCase, SuiteRun, TestCase, TestSuite


class TestRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestRecord
        fields = ['id', 'status', 'elapsed_time', 'result_log', 'created_at']
        read_only_fields = fields


class TestCaseSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = TestCase
        fields = [
            'id',
            'project',
            'project_name',
            'title',
            'steps',
            'variables',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'project_name', 'created_at', 'updated_at']

    def validate_steps(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('steps 必须为 JSON 数组，便于执行引擎逐条解析。')
        return value

    def validate_variables(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('variables 必须为 JSON 对象（全局变量池）。')
        return value


class OpenAPIImportSerializer(serializers.Serializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    spec = serializers.JSONField(required=False, allow_null=True)
    spec_url = serializers.URLField(required=False, allow_blank=True, max_length=2048)
    spec_yaml = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)

    def validate(self, attrs):
        spec = attrs.get('spec')
        url = (attrs.get('spec_url') or '').strip()
        yml = attrs.get('spec_yaml')
        yml_stripped = (yml or '').strip() if isinstance(yml, str) else ''
        has_spec = spec is not None
        has_url = bool(url)
        has_yml = bool(yml_stripped)
        if has_spec + has_url + has_yml != 1:
            raise serializers.ValidationError(
                '请提供且仅提供一种来源：spec（JSON 对象）、spec_url、spec_yaml'
            )
        attrs['spec_url'] = url if has_url else None
        attrs['spec_yaml'] = yml_stripped if has_yml else None
        return attrs


class TestSuiteSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    ordered_case_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )
    cases_summary = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TestSuite
        fields = [
            'id',
            'project',
            'project_name',
            'name',
            'description',
            'variables',
            'ordered_case_ids',
            'cases_summary',
            'created_at',
        ]
        read_only_fields = ['id', 'project_name', 'cases_summary', 'created_at']

    def get_cases_summary(self, obj: TestSuite) -> list[dict]:
        return [
            {
                'id': sc.testcase_id,
                'title': sc.testcase.title,
                'order': sc.order,
            }
            for sc in obj.suite_cases.select_related('testcase').order_by('order', 'id')
        ]

    def validate_variables(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('variables 须为 JSON 对象')
        return value

    def create(self, validated_data):
        ids = validated_data.pop('ordered_case_ids', None)
        suite = TestSuite.objects.create(**validated_data)
        if ids is not None:
            self._replace_suite_cases(suite, ids)
        return suite

    def update(self, instance, validated_data):
        ids = validated_data.pop('ordered_case_ids', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if ids is not None:
            self._replace_suite_cases(instance, ids)
        return instance

    def _replace_suite_cases(self, suite: TestSuite, ids: list[int]) -> None:
        SuiteCase.objects.filter(suite=suite).delete()
        pid = suite.project_id
        for order, cid in enumerate(ids):
            try:
                tc = TestCase.objects.get(pk=cid, project_id=pid)
            except TestCase.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {'ordered_case_ids': f'用例 id={cid} 不存在或不属于该项目'}
                ) from exc
            SuiteCase.objects.create(suite=suite, testcase=tc, order=order)


class SuiteRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuiteRun
        fields = [
            'id',
            'suite',
            'created_at',
            'stop_on_failure',
            'summary',
            'results',
        ]
        read_only_fields = fields
