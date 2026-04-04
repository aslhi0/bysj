from rest_framework import serializers
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from .models import Project, TestCase, TestSuite, TestRecord, SuiteRun, EnvConfig, PerfRecord, TestCaseVersion
from .crypto_utils import encrypt_json, decrypt_json, mask_json, merge_masked

class CrontabScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrontabSchedule
        fields = [
            'id',
            'minute',
            'hour',
            'day_of_week',
            'day_of_month',
            'month_of_year',
            'timezone',
        ]

class PeriodicTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = PeriodicTask
        fields = [
            'id',
            'name',
            'task',
            'crontab',
            'enabled',
            'args',
            'kwargs',
            'description',
            'last_run_at',
            'total_run_count',
            'date_changed',
        ]
        read_only_fields = [
            'task',
            'args',
            'kwargs',
            'description',
            'last_run_at',
            'total_run_count',
            'date_changed',
        ]

class EnvConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvConfig
        fields = [
            'id',
            'project',
            'name',
            'base_url',
            'db_config',
            'variables',
            'is_default',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate_db_config(self, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        raise serializers.ValidationError('db_config 必须是 JSON 对象')
    
    def validate_variables(self, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        raise serializers.ValidationError('variables 必须是 JSON 对象')
    
    def validate_project(self, value):
        req = self.context.get('request')
        user = getattr(req, 'user', None)
        if user and user.is_authenticated:
            if value.owner_id != user.id:
                raise serializers.ValidationError('无权限访问该项目')
        return value
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if isinstance(data.get('variables'), dict):
            data['variables'] = mask_json(data['variables'])
        if isinstance(data.get('db_config'), dict):
            data['db_config'] = mask_json(data['db_config'])
        return data
    
    def create(self, validated_data):
        if isinstance(validated_data.get('variables'), dict):
            validated_data['variables'] = encrypt_json(validated_data['variables'])
        if isinstance(validated_data.get('db_config'), dict):
            validated_data['db_config'] = encrypt_json(validated_data['db_config'])
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        if isinstance(validated_data.get('variables'), dict):
            old_vars = decrypt_json(instance.variables or {}) if isinstance(instance.variables, dict) else {}
            merged = merge_masked(old_vars, validated_data['variables'])
            validated_data['variables'] = encrypt_json(merged)
        if isinstance(validated_data.get('db_config'), dict):
            old_db = decrypt_json(instance.db_config or {}) if isinstance(instance.db_config, dict) else {}
            merged = merge_masked(old_db, validated_data['db_config'])
            validated_data['db_config'] = encrypt_json(merged)
        return super().update(instance, validated_data)

class ProjectSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['owner', 'created_at']

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
            'tags',
            'setup_sql',
            'teardown_sql',
            'status',
            'updated_at',
            'created_at',
        ]
        read_only_fields = ['id', 'project_name', 'updated_at', 'created_at']
    
    def validate_project(self, value):
        req = self.context.get('request')
        user = getattr(req, 'user', None)
        if user and user.is_authenticated:
            if value.owner_id != user.id:
                raise serializers.ValidationError('无权限访问该项目')
        return value
    
    def validate_steps(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('steps 必须是数组')
        if len(value) > 200:
            raise serializers.ValidationError('steps 过多（上限 200）')
        allowed_http = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'}
        allowed_ui = {'open', 'click', 'input', 'wait_visible', 'sleep'}
        allowed_by = {'css', 'css_selector', 'xpath', 'id', 'name', 'class', 'class_name', 'tag', 'tag_name', 'link_text', 'partial_link_text'}
        for i, step in enumerate(value):
            if not isinstance(step, dict):
                raise serializers.ValidationError(f'第 {i + 1} 个 step 必须是对象')
            t = step.get('type')
            if t not in {'http', 'ui'}:
                raise serializers.ValidationError(f'第 {i + 1} 个 step.type 必须是 http 或 ui')
            if t == 'http':
                m = str(step.get('method', 'GET')).upper().strip() or 'GET'
                if m not in allowed_http:
                    raise serializers.ValidationError(f'第 {i + 1} 个 HTTP method 不合法')
                url = step.get('url')
                if not isinstance(url, str) or not url.strip():
                    raise serializers.ValidationError(f'第 {i + 1} 个 HTTP url 不能为空')
                ass = step.get('assertions', [])
                if ass is None:
                    ass = []
                if not isinstance(ass, list):
                    raise serializers.ValidationError(f'第 {i + 1} 个 assertions 必须是数组')
            else:
                action = step.get('action')
                if action not in allowed_ui:
                    raise serializers.ValidationError(f'第 {i + 1} 个 UI action 不合法')
                by = step.get('by')
                if by is not None and str(by).strip().lower() not in allowed_by:
                    raise serializers.ValidationError(f'第 {i + 1} 个 UI by 不合法')
                if action == 'open':
                    url = step.get('url')
                    if not isinstance(url, str) or not url.strip():
                        raise serializers.ValidationError(f'第 {i + 1} 个 UI url 不能为空')
                if action in {'click', 'input', 'wait_visible'}:
                    sel = step.get('selector')
                    if not isinstance(sel, str) or not sel.strip():
                        raise serializers.ValidationError(f'第 {i + 1} 个 UI selector 不能为空')
        return value
    
    def validate_variables(self, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        raise serializers.ValidationError('variables 必须是 JSON 对象')

class TestSuiteSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    cases_summary = serializers.SerializerMethodField()

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

    def get_cases_summary(self, obj):
        ids = obj.ordered_case_ids or []
        cases = TestCase.objects.filter(id__in=ids)
        case_map = {c.id: c.title for c in cases}
        return [{'id': cid, 'title': case_map.get(cid, 'Unknown')} for cid in ids]
    
    def validate_variables(self, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        raise serializers.ValidationError('variables 必须是 JSON 对象')
    
    def validate_ordered_case_ids(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('ordered_case_ids 必须是数组')
        if len(value) > 500:
            raise serializers.ValidationError('ordered_case_ids 过多（上限 500）')
        for i, v in enumerate(value):
            if not isinstance(v, int):
                raise serializers.ValidationError(f'ordered_case_ids 第 {i + 1} 项必须是整数')
        return value
    
    def validate_project(self, value):
        req = self.context.get('request')
        user = getattr(req, 'user', None)
        if user and user.is_authenticated:
            if value.owner_id != user.id:
                raise serializers.ValidationError('无权限访问该项目')
        return value

class TestRecordSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source='case.title', read_only=True)
    class Meta:
        model = TestRecord
        fields = [
            'id',
            'case',
            'case_title',
            'status',
            'result_log',
            'step_results',
            'screenshot',
            'elapsed_time',
            'created_at',
        ]
        read_only_fields = ['id', 'case_title', 'created_at']

class SuiteRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuiteRun
        fields = [
            'id',
            'suite',
            'summary',
            'stop_on_failure',
            'results',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

class PerfRecordSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source='case.title', read_only=True)
    class Meta:
        model = PerfRecord
        fields = [
            'id',
            'case',
            'case_title',
            'users',
            'spawn_rate',
            'duration',
            'status',
            'csv_prefix',
            'created_at',
        ]
        read_only_fields = ['id', 'case_title', 'csv_prefix', 'created_at']

class TestCaseVersionSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    class Meta:
        model = TestCaseVersion
        fields = [
            'id',
            'case',
            'version',
            'snapshot',
            'created_by',
            'created_by_username',
            'created_at',
        ]
        read_only_fields = ['id', 'created_by_username', 'created_at']
