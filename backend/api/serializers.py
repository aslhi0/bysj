from rest_framework import serializers
from django.contrib.admin.models import LogEntry
from .models import Project, ProjectMember, TestCase, TestSuite, TestRecord, SuiteRun, EnvConfig, PerfRecord, TestCaseVersion
from .crypto_utils import encrypt_json, decrypt_json, mask_json, merge_masked

def _validate_json_limits(value, *, max_depth=8, max_keys=200, max_list=500, max_str=20000, max_nodes=5000):
    nodes = 0

    def walk(v, depth):
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            raise serializers.ValidationError('JSON 内容过大')
        if depth > max_depth:
            raise serializers.ValidationError('JSON 嵌套过深')
        if v is None or isinstance(v, (bool, int, float)):
            return
        if isinstance(v, str):
            if len(v) > max_str:
                raise serializers.ValidationError('JSON 字符串过长')
            return
        if isinstance(v, list):
            if len(v) > max_list:
                raise serializers.ValidationError('JSON 数组过长')
            for it in v:
                walk(it, depth + 1)
            return
        if isinstance(v, dict):
            if len(v) > max_keys:
                raise serializers.ValidationError('JSON 键数量过多')
            for k, it in v.items():
                if not isinstance(k, str):
                    raise serializers.ValidationError('JSON 键必须为字符串')
                if len(k) > 100:
                    raise serializers.ValidationError('JSON 键名过长')
                walk(it, depth + 1)
            return
        raise serializers.ValidationError('JSON 类型不支持')

    walk(value, 1)

def _can_access_project(user, project):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return True
    if project.owner_id == user.id:
        return True
    return ProjectMember.objects.filter(project=project, user=user, is_active=True).exists()

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
    
    # 当前数据库断言仅支持项目根下的 SQLite 文件（见 engine.run_db_query）。
    # 显式枚举允许键，避免用户配置 host/port/user/password 等多 DB 字段后被静默忽略
    # ——那会带来"配置了却不生效"的 UI/实现错位。
    _DB_CONFIG_ALLOWED_KEYS = {'sqlite_path'}

    def validate_db_config(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('db_config 必须是 JSON 对象')
        _validate_json_limits(value, max_depth=6, max_keys=100, max_list=200, max_str=20000, max_nodes=2000)
        unsupported = [k for k in value.keys() if k not in self._DB_CONFIG_ALLOWED_KEYS]
        if unsupported:
            raise serializers.ValidationError(
                f'db_config 暂仅支持键 {sorted(self._DB_CONFIG_ALLOWED_KEYS)}，'
                f'以下键不受支持：{unsupported}'
            )
        sqlite_path = value.get('sqlite_path')
        if sqlite_path is not None and not isinstance(sqlite_path, str):
            raise serializers.ValidationError('sqlite_path 必须是字符串')
        return value
    
    def validate_variables(self, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            _validate_json_limits(value, max_depth=8, max_keys=200, max_list=500, max_str=50000, max_nodes=5000)
            return value
        raise serializers.ValidationError('variables 必须是 JSON 对象')
    
    def validate_project(self, value):
        req = self.context.get('request')
        user = getattr(req, 'user', None)
        if user and user.is_authenticated:
            if not _can_access_project(user, value):
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
        fields = [
            'id',
            'owner',
            'owner_username',
            'name',
            'description',
            'webhook_url',
            'created_at',
        ]
        read_only_fields = ['id', 'owner', 'owner_username', 'created_at']

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

    def to_representation(self, instance):
        # 读取时对敏感 key 做脱敏（与 EnvConfig 同策略）：只屏蔽 password/token/...
        # 非敏感 key 保持明文，保证现有用例 UI（如 url/method）的可读性与兼容历史数据。
        data = super().to_representation(instance)
        if isinstance(data.get('variables'), dict):
            data['variables'] = mask_json(data['variables'])
        return data

    def create(self, validated_data):
        if isinstance(validated_data.get('variables'), dict):
            validated_data['variables'] = encrypt_json(validated_data['variables'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if isinstance(validated_data.get('variables'), dict):
            # decrypt_json 对未加密值原样返回，天然兼容加密前写入的历史用例
            old_vars = decrypt_json(instance.variables or {}) if isinstance(instance.variables, dict) else {}
            merged = merge_masked(old_vars, validated_data['variables'])
            validated_data['variables'] = encrypt_json(merged)
        return super().update(instance, validated_data)
    
    def validate_project(self, value):
        req = self.context.get('request')
        user = getattr(req, 'user', None)
        if user and user.is_authenticated:
            if not _can_access_project(user, value):
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
            _validate_json_limits(value, max_depth=8, max_keys=200, max_list=500, max_str=50000, max_nodes=5000)
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
        if not ids:
            return []
        # 优先使用视图层预加载的 case_cache，避免列表接口的 N+1 查询
        case_cache = self.context.get('case_cache') or {}
        if not case_cache:
            cases = TestCase.objects.filter(id__in=ids).values('id', 'title')
            case_cache = {c['id']: c['title'] for c in cases}
        return [{'id': cid, 'title': case_cache.get(cid, 'Unknown')} for cid in ids]
    
    def validate_variables(self, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            _validate_json_limits(value, max_depth=8, max_keys=200, max_list=500, max_str=50000, max_nodes=5000)
            return value
        raise serializers.ValidationError('variables 必须是 JSON 对象')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if isinstance(data.get('variables'), dict):
            data['variables'] = mask_json(data['variables'])
        return data

    def create(self, validated_data):
        if isinstance(validated_data.get('variables'), dict):
            validated_data['variables'] = encrypt_json(validated_data['variables'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if isinstance(validated_data.get('variables'), dict):
            old_vars = decrypt_json(instance.variables or {}) if isinstance(instance.variables, dict) else {}
            merged = merge_masked(old_vars, validated_data['variables'])
            validated_data['variables'] = encrypt_json(merged)
        return super().update(instance, validated_data)

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
            if not _can_access_project(user, value):
                raise serializers.ValidationError('无权限访问该项目')
        return value


class ProjectMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ProjectMember
        fields = ['id', 'project', 'user', 'username', 'is_active', 'created_at']
        read_only_fields = ['id', 'username', 'created_at']

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
            'attempts',
            'attempt_logs',
            'created_at',
        ]
        read_only_fields = ['id', 'case_title', 'attempts', 'attempt_logs', 'created_at']

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

class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    content_type = serializers.SerializerMethodField()
    action = serializers.SerializerMethodField()

    class Meta:
        model = LogEntry
        fields = [
            'id',
            'action_time',
            'user',
            'username',
            'content_type',
            'object_id',
            'object_repr',
            'action_flag',
            'action',
            'change_message',
        ]
        read_only_fields = fields

    def get_content_type(self, obj):
        ct = getattr(obj, 'content_type', None)
        if not ct:
            return None
        try:
            return f'{ct.app_label}.{ct.model}'
        except Exception:
            return None

    def get_action(self, obj):
        m = {1: 'add', 2: 'change', 3: 'delete'}
        return m.get(getattr(obj, 'action_flag', None), 'unknown')
