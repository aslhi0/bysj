from rest_framework import serializers
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from .models import Project, TestCase, TestSuite, TestRecord, SuiteRun, EnvConfig, PerfRecord

class CrontabScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrontabSchedule
        fields = '__all__'

class PeriodicTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = PeriodicTask
        fields = '__all__'

class EnvConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvConfig
        fields = '__all__'

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'

class TestCaseSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    class Meta:
        model = TestCase
        fields = '__all__'

class TestSuiteSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    cases_summary = serializers.SerializerMethodField()

    class Meta:
        model = TestSuite
        fields = '__all__'

    def get_cases_summary(self, obj):
        ids = obj.ordered_case_ids or []
        cases = TestCase.objects.filter(id__in=ids)
        case_map = {c.id: c.title for c in cases}
        return [{'id': cid, 'title': case_map.get(cid, 'Unknown')} for cid in ids]

class TestRecordSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source='case.title', read_only=True)
    class Meta:
        model = TestRecord
        fields = '__all__'

class SuiteRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuiteRun
        fields = '__all__'

class PerfRecordSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source='case.title', read_only=True)
    class Meta:
        model = PerfRecord
        fields = '__all__'
