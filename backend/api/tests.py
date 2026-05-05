from unittest import TestCase
from unittest.mock import patch, MagicMock
import json
import os
import socket

from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import Project, ProjectMember, EnvConfig, TestCase as DbTestCase, TestSuite as DbTestSuite, PerfRecord
from .engine import TestEngine, validate_outbound_http_url
from .tasks import run_test_case_task, run_test_suite_task
from .health import health_check
from .views import PerfRecordViewSet, task_status, RegisterView, AdminUserListView
from .locust_codegen import generate_locust_code
from .utils import Notifier
from .crypto_utils import decrypt_json, encrypt_str, decrypt_str, merge_masked, ENC_PREFIX, MASK
from .task_tracker import bind_task_owner, get_task_owner
from .flaky_analysis import compute_flaky_analysis_from_statuses

class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.headers = headers if headers is not None else {}

    def json(self):
        return self._json_data


class TestEngineHttp(TestCase):
    def test_http_assertion_failure_makes_step_failed(self):
        engine = TestEngine(variables={'base_url': 'https://example.com'})
        step = {
            'type': 'http',
            'method': 'GET',
            'url': '{{base_url}}/ping',
            'headers': '{}',
            'body': '',
            'capture': '{}',
            'assertions': [{'source': 'status_code', 'operator': 'eq', 'expected': '201'}],
        }

        with patch('api.engine.requests.request', return_value=FakeResponse(status_code=200)) as _p:
            ok = engine.run_http(step)
        self.assertFalse(ok)

    def test_http_capture_accepts_object(self):
        engine = TestEngine()
        step = {
            'type': 'http',
            'method': 'GET',
            'url': 'https://example.com/any',
            'headers': {},
            'body': '',
            'capture': {'token': {'from': 'json', 'path': 'data.token'}},
            'assertions': [],
        }
        resp = FakeResponse(status_code=200, json_data={'data': {'token': 'abc'}})
        gai = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 443))]
        with (
            patch('api.engine.requests.request', return_value=resp),
            patch('api.engine.socket.getaddrinfo', return_value=gai),
        ):
            ok = engine.run_http(step)
        self.assertTrue(ok)
        self.assertEqual(engine.variables.get('token'), 'abc')

    def test_base_and_base_url_aliasing(self):
        engine1 = TestEngine(variables={'base_url': 'https://a.com'})
        self.assertEqual(engine1.variables.get('base'), 'https://a.com')
        self.assertEqual(engine1.variables.get('base_url'), 'https://a.com')

        engine2 = TestEngine(variables={'base': 'https://b.com'})
        self.assertEqual(engine2.variables.get('base'), 'https://b.com')
        self.assertEqual(engine2.variables.get('base_url'), 'https://b.com')

    def test_bracket_placeholder_is_supported(self):
        engine = TestEngine(variables={'base_url': 'https://example.com'})
        self.assertEqual(engine.render_string('[[base_url]]/uuid'), 'https://example.com/uuid')

    def test_validate_outbound_http_url_blocks_localhost(self):
        with self.assertRaises(ValueError):
            validate_outbound_http_url('http://localhost:8000')

    def test_validate_outbound_http_url_blocks_loopback_ip(self):
        with self.assertRaises(ValueError):
            validate_outbound_http_url('http://127.0.0.1:8000')

    def test_validate_outbound_http_url_blocks_private_ip(self):
        with self.assertRaises(ValueError):
            validate_outbound_http_url('http://10.0.0.1:80')

    def test_validate_outbound_http_url_allows_when_host_is_allowlisted(self):
        validate_outbound_http_url('https://example.com/api', allowed_hosts=['example.com'])

    def test_validate_outbound_http_url_rejects_non_http_scheme(self):
        with self.assertRaises(ValueError):
            validate_outbound_http_url('file:///etc/passwd')

    def test_validate_outbound_http_url_rejects_userinfo(self):
        with self.assertRaises(ValueError):
            validate_outbound_http_url('http://user:pass@example.com/')

    def test_db_query_rejects_multi_statement(self):
        engine = TestEngine(db_config={'sqlite_path': 'db.sqlite3'})
        res = engine.run_db_query('select 1; select 2')
        self.assertEqual(res, 'Error')

    def test_db_query_rejects_dangerous_keyword_attach(self):
        engine = TestEngine(db_config={'sqlite_path': 'db.sqlite3'})
        res = engine.run_db_query('select pragma')
        self.assertEqual(res, 'Error')

    def test_db_query_execute_mode_rejects_non_dml(self):
        engine = TestEngine(db_config={'sqlite_path': 'db.sqlite3'})
        res = engine.run_db_query('create table t(id int)', execute=True)
        self.assertEqual(res, 'Error')

    def test_db_query_rejects_absolute_sqlite_path(self):
        engine = TestEngine(db_config={'sqlite_path': r'C:\Windows\win.ini'})
        res = engine.run_db_query('select 1')
        self.assertEqual(res, 'Error')


class TestEngineUiBrowserSelection(TestCase):
    def _sleep_step(self, browser=None):
        step = {'type': 'ui', 'action': 'sleep', 'seconds': 0}
        if browser is not None:
            step['browser'] = browser
        return step

    def _clean_browser_env(self, **overrides):
        keys = [
            'TEST_BROWSER',
            'CHROME_BIN',
            'CHROMIUM_BIN',
            'CHROMEDRIVER',
            'EDGE_BIN',
            'MSEDGE_BIN',
            'EDGEDRIVER',
            'MSEDGEDRIVER',
        ]
        values = {key: '' for key in keys}
        values.update(overrides)
        return patch.dict(os.environ, values, clear=False)

    def test_run_ui_uses_chrome_first_by_default(self):
        engine = TestEngine()
        fake_driver = MagicMock()
        with (
            self._clean_browser_env(TEST_BROWSER='auto'),
            patch('api.engine.webdriver.ChromeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.EdgeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.Chrome', return_value=fake_driver) as chrome,
            patch('api.engine.webdriver.Edge') as edge,
        ):
            ok = engine.run_ui(self._sleep_step())

        self.assertTrue(ok)
        chrome.assert_called_once()
        edge.assert_not_called()
        self.assertIs(engine.driver, fake_driver)
        self.assertIn('Browser ready: chrome', engine.get_full_log())

    def test_run_ui_auto_falls_back_to_edge_when_chrome_fails(self):
        engine = TestEngine()
        fake_driver = MagicMock()
        with (
            self._clean_browser_env(TEST_BROWSER='auto'),
            patch('api.engine.webdriver.ChromeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.EdgeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.Chrome', side_effect=Exception('chrome missing')) as chrome,
            patch('api.engine.webdriver.Edge', return_value=fake_driver) as edge,
        ):
            ok = engine.run_ui(self._sleep_step())

        self.assertTrue(ok)
        chrome.assert_called_once()
        edge.assert_called_once()
        self.assertIs(engine.driver, fake_driver)
        log = engine.get_full_log()
        self.assertIn('chrome initialization failed: chrome missing', log)
        self.assertIn('Browser ready: edge', log)

    def test_run_ui_browser_name_edge_skips_chrome(self):
        engine = TestEngine()
        fake_driver = MagicMock()
        with (
            self._clean_browser_env(TEST_BROWSER='auto'),
            patch('api.engine.webdriver.ChromeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.EdgeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.Chrome') as chrome,
            patch('api.engine.webdriver.Edge', return_value=fake_driver) as edge,
        ):
            ok = engine.run_ui(self._sleep_step(browser={'name': 'edge'}))

        self.assertTrue(ok)
        chrome.assert_not_called()
        edge.assert_called_once()
        self.assertIs(engine.driver, fake_driver)

    def test_run_ui_returns_false_when_all_browsers_fail(self):
        engine = TestEngine()
        with (
            self._clean_browser_env(TEST_BROWSER='auto'),
            patch('api.engine.webdriver.ChromeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.EdgeOptions', return_value=MagicMock()),
            patch('api.engine.webdriver.Chrome', side_effect=Exception('chrome missing')),
            patch('api.engine.webdriver.Edge', side_effect=Exception('edge missing')),
        ):
            ok = engine.run_ui(self._sleep_step())

        self.assertFalse(ok)
        log = engine.get_full_log()
        self.assertIn('Unable to initialize Selenium browser', log)
        self.assertIn('chrome missing', log)
        self.assertIn('edge missing', log)


class TestIntegrationTasks(DjangoTestCase):
    def test_run_test_case_task_creates_record_and_renders_variables(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='u1', password='p1')
        project = Project.objects.create(name='p1', owner=user)
        env = EnvConfig.objects.create(
            project=project,
            name='env',
            base_url='https://httpbin.org',
            variables={},
            is_default=True,
        )
        case = DbTestCase.objects.create(
            project=project,
            title='case',
            status='active',
            steps=[
                {
                    'type': 'http',
                    'method': 'GET',
                    'url': '{{base_url}}/uuid',
                    'headers': {},
                    'body': '',
                    'capture': {'sys_uuid': {'from': 'json', 'path': 'uuid'}},
                    'assertions': [{'source': 'status_code', 'operator': 'eq', 'expected': '200'}],
                },
                {
                    'type': 'http',
                    'method': 'GET',
                    'url': '{{base_url}}/get?tag={{sys_uuid}}',
                    'headers': {},
                    'body': '',
                    'capture': {},
                    'assertions': [{'source': 'status_code', 'operator': 'eq', 'expected': '200'}],
                },
            ],
        )

        called_urls = []

        def fake_request(method, url, **kwargs):
            called_urls.append(url)
            if url.endswith('/uuid'):
                return FakeResponse(status_code=200, json_data={'uuid': 'u-1'})
            return FakeResponse(status_code=200, json_data={})

        with patch('api.engine.requests.request', side_effect=fake_request):
            result = run_test_case_task(case.id, env.id, {})

        self.assertEqual(result.get('status'), 'success')
        self.assertTrue(result.get('record_id'))
        self.assertEqual(len(called_urls), 2)
        self.assertIn('tag=u-1', called_urls[1])

    def test_run_test_case_task_retries_until_success(self):
        """重试策略：一次 run 聚合为单条 TestRecord，attempt_logs 保留每次尝试明细。"""
        from django.contrib.auth import get_user_model
        from .models import TestRecord as DbTestRecord

        user = get_user_model().objects.create_user(username='u1r', password='p1')
        project = Project.objects.create(name='p1r', owner=user)
        env = EnvConfig.objects.create(
            project=project,
            name='env',
            base_url='https://httpbin.org',
            variables={},
            is_default=True,
        )
        case = DbTestCase.objects.create(project=project, title='case', status='active', steps=[])

        fake_fail = {'engine': None, 'success': False, 'error_message': None, 'elapsed': 1.0}
        fake_ok = {'engine': None, 'success': True, 'error_message': None, 'elapsed': 1.1}

        with patch('api.tasks._invoke_engine_once', side_effect=[fake_fail, fake_ok]):
            result = run_test_case_task(case.id, env.id, {}, retry_times=2)

        self.assertEqual(result.get('status'), 'success')
        self.assertEqual(result.get('attempts'), 3)
        self.assertEqual(result.get('attempts_made'), 2)
        self.assertEqual(result.get('retries_used'), 1)

        # 数据库中应仅产生 1 条聚合记录，attempt_logs 反映两次尝试
        records = list(DbTestRecord.objects.filter(case=case))
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.status, 'success')
        self.assertEqual(rec.attempts, 2)
        self.assertEqual([a.get('status') for a in rec.attempt_logs], ['failed', 'success'])
        self.assertAlmostEqual(rec.elapsed_time, 2.1, places=3)

    def test_run_test_suite_task_propagates_variables_across_cases(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='u2', password='p2')
        project = Project.objects.create(name='p1', owner=user)
        env = EnvConfig.objects.create(
            project=project,
            name='env',
            base_url='https://httpbin.org',
            variables={},
            is_default=True,
        )

        case1 = DbTestCase.objects.create(
            project=project,
            title='c1',
            status='active',
            steps=[
                {
                    'type': 'http',
                    'method': 'GET',
                    'url': '{{base_url}}/uuid',
                    'headers': {},
                    'body': '',
                    'capture': {'sys_uuid': {'from': 'json', 'path': 'uuid'}},
                    'assertions': [{'source': 'status_code', 'operator': 'eq', 'expected': '200'}],
                },
            ],
        )
        case2 = DbTestCase.objects.create(
            project=project,
            title='c2',
            status='active',
            steps=[
                {
                    'type': 'http',
                    'method': 'GET',
                    'url': '{{base_url}}/get?tag={{sys_uuid}}',
                    'headers': {},
                    'body': '',
                    'capture': {},
                    'assertions': [{'source': 'status_code', 'operator': 'eq', 'expected': '200'}],
                },
            ],
        )
        suite = DbTestSuite.objects.create(
            project=project,
            name='s1',
            ordered_case_ids=[case1.id, case2.id],
        )

        called_urls = []

        def fake_request(method, url, **kwargs):
            called_urls.append(url)
            if url.endswith('/uuid'):
                return FakeResponse(status_code=200, json_data={'uuid': 'u-2'})
            return FakeResponse(status_code=200, json_data={})

        with patch('api.engine.requests.request', side_effect=fake_request):
            result = run_test_suite_task(suite.id, env.id, {}, stop_on_failure=False)

        self.assertTrue(result.get('suite_run_id'))
        self.assertEqual(result.get('summary', {}).get('total'), 2)
        self.assertEqual(len(called_urls), 2)
        self.assertIn('tag=u-2', called_urls[1])

    def test_perf_record_locust_endpoint_returns_script(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='u3', password='p3')
        project = Project.objects.create(name='p1', owner=user)
        EnvConfig.objects.create(
            project=project,
            name='env',
            base_url='https://httpbin.org',
            variables={},
            is_default=True,
        )
        case = DbTestCase.objects.create(
            project=project,
            title='case',
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '{{base_url}}/get', 'headers': {}, 'body': ''}],
        )
        perf = PerfRecord.objects.create(case=case, users=1, spawn_rate=1, duration='1s', status='running', csv_prefix='')

        factory = APIRequestFactory()
        req = factory.get(f'/api/perf-records/{perf.id}/locust/')
        force_authenticate(req, user=user)
        resp = PerfRecordViewSet.as_view({'get': 'locust'})(req, pk=str(perf.id))


        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8', 'ignore')
        self.assertIn('from locust import HttpUser', content)

    def test_envconfig_encrypts_and_masks_sensitive_fields(self):
        from . import views as api_views
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='u4', password='p4')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p1', owner=user)

        factory = APIRequestFactory()
        req = factory.post('/api/envs/', {}, format='json')
        force_authenticate(req, user=user)

        # db_config 仅支持 sqlite_path（安全沙箱），敏感字段的加密/脱敏验证聚焦于 variables
        payload = {
            'project': project.id,
            'name': 'env',
            'base_url': 'https://example.com',
            'variables': {'token': 'abc', 'k': 'v'},
            'db_config': {'sqlite_path': 'db.sqlite3'},
            'is_default': True,
        }
        create_req = factory.post('/api/envs/', payload, format='json')
        force_authenticate(create_req, user=user)
        resp = api_views.EnvConfigViewSet.as_view({'post': 'create'})(create_req)
        self.assertEqual(resp.status_code, 201)

        env_id = resp.data.get('id')
        env = EnvConfig.objects.get(id=env_id)
        self.assertTrue(str(env.variables.get('token', '')).startswith(ENC_PREFIX))
        plain_vars = decrypt_json(env.variables)
        self.assertEqual(plain_vars.get('token'), 'abc')

        list_req = factory.get('/api/envs/')
        force_authenticate(list_req, user=user)
        list_resp = api_views.EnvConfigViewSet.as_view({'get': 'list'})(list_req)
        self.assertEqual(list_resp.status_code, 200)
        row = list_resp.data[0]
        self.assertEqual(row['variables']['token'], MASK)
        # sqlite_path 非敏感键，保持明文
        self.assertEqual(row['db_config'].get('sqlite_path'), 'db.sqlite3')

        # db_config 中传入未支持键（如 host/password）应被 serializer 拒绝
        bad_payload = dict(payload)
        bad_payload['name'] = 'env-bad'
        bad_payload['db_config'] = {'host': '127.0.0.1', 'password': 'pw'}
        bad_req = factory.post('/api/envs/', bad_payload, format='json')
        force_authenticate(bad_req, user=user)
        bad_resp = api_views.EnvConfigViewSet.as_view({'post': 'create'})(bad_req)
        self.assertEqual(bad_resp.status_code, 400)

    def test_case_version_is_created_on_create_and_update(self):
        from . import views as api_views
        from . import models as api_models
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='u5', password='p5')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p1', owner=user)

        factory = APIRequestFactory()
        payload = {
            'project': project.id,
            'title': 'case',
            'steps': [{'type': 'http', 'method': 'GET', 'url': 'https://example.com', 'headers': {}, 'body': ''}],
            'variables': {},
            'tags': [],
            'setup_sql': '',
            'teardown_sql': '',
            'status': 'draft',
        }
        create_req = factory.post('/api/cases/', payload, format='json')
        force_authenticate(create_req, user=user)
        create_resp = api_views.TestCaseViewSet.as_view({'post': 'create'})(create_req)
        self.assertEqual(create_resp.status_code, 201)
        case_id = create_resp.data.get('id')
        self.assertEqual(api_models.TestCaseVersion.objects.filter(case_id=case_id).count(), 1)

        payload2 = dict(payload)
        payload2['title'] = 'case2'
        upd_req = factory.put(f'/api/cases/{case_id}/', payload2, format='json')
        force_authenticate(upd_req, user=user)
        upd_resp = api_views.TestCaseViewSet.as_view({'put': 'update'})(upd_req, pk=str(case_id))
        self.assertEqual(upd_resp.status_code, 200)
        self.assertEqual(api_models.TestCaseVersion.objects.filter(case_id=case_id).count(), 2)

    def test_project_visibility_includes_assigned_member_projects(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user1 = get_user_model().objects.create_user(username='u6', password='p6')
        user2 = get_user_model().objects.create_user(username='u7', password='p7')
        p1 = Project.objects.create(name='p1', owner=user1)
        ProjectMember.objects.create(project=p1, user=user2, is_active=True)

        factory = APIRequestFactory()
        req = factory.get('/api/projects/')
        force_authenticate(req, user=user2)
        resp = api_views.ProjectViewSet.as_view({'get': 'list'})(req)
        self.assertEqual(resp.status_code, 200)
        ids = [r.get('id') for r in resp.data]
        self.assertIn(p1.id, ids)

    def test_project_members_can_access_cases_but_unassigned_users_cannot(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        owner = get_user_model().objects.create_user(username='u6_owner', password='p6')
        member = get_user_model().objects.create_user(username='u6_member', password='p6')
        stranger = get_user_model().objects.create_user(username='u6_stranger', password='p6')
        project = Project.objects.create(name='p-member', owner=owner)
        ProjectMember.objects.create(project=project, user=member, is_active=True)
        case = DbTestCase.objects.create(project=project, title='c-member', status='draft', steps=[])

        factory = APIRequestFactory()

        list_req = factory.get('/api/cases/')
        force_authenticate(list_req, user=member)
        list_resp = api_views.TestCaseViewSet.as_view({'get': 'list'})(list_req)
        self.assertEqual(list_resp.status_code, 200)
        ids = [row.get('id') for row in list_resp.data]
        self.assertIn(case.id, ids)

        retrieve_req = factory.get(f'/api/cases/{case.id}/')
        force_authenticate(retrieve_req, user=stranger)
        retrieve_resp = api_views.TestCaseViewSet.as_view({'get': 'retrieve'})(retrieve_req, pk=str(case.id))
        self.assertEqual(retrieve_resp.status_code, 404)

    def test_admin_can_add_and_remove_project_member(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        admin = get_user_model().objects.create_user(username='u6_admin', password='p6')
        admin.is_staff = True
        admin.save(update_fields=['is_staff'])
        user = get_user_model().objects.create_user(username='u6_target', password='p6')
        project = Project.objects.create(name='p-admin-member', owner=admin)

        factory = APIRequestFactory()
        add_req = factory.post(f'/api/projects/{project.id}/add_member/', {'user_id': user.id}, format='json')
        force_authenticate(add_req, user=admin)
        add_resp = api_views.ProjectViewSet.as_view({'post': 'add_member'})(add_req, pk=str(project.id))
        self.assertEqual(add_resp.status_code, 200)
        self.assertTrue(ProjectMember.objects.filter(project=project, user=user, is_active=True).exists())

        remove_req = factory.post(f'/api/projects/{project.id}/remove_member/', {'user_id': user.id}, format='json')
        force_authenticate(remove_req, user=admin)
        remove_resp = api_views.ProjectViewSet.as_view({'post': 'remove_member'})(remove_req, pk=str(project.id))
        self.assertEqual(remove_resp.status_code, 200)
        self.assertFalse(ProjectMember.objects.filter(project=project, user=user).exists())

    def test_audit_log_is_created_on_project_create(self):
        from django.contrib.auth import get_user_model
        from django.contrib.admin.models import LogEntry
        from . import views as api_views

        user = get_user_model().objects.create_user(username='u8', password='p8')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        factory = APIRequestFactory()
        req = factory.post('/api/projects/', {'name': 'p', 'description': '', 'webhook_url': ''}, format='json')
        force_authenticate(req, user=user)
        resp = api_views.ProjectViewSet.as_view({'post': 'create'})(req)
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(LogEntry.objects.filter(user=user, object_id=str(resp.data.get('id'))).exists())

    def test_audit_logs_endpoint_admin_can_view_all(self):
        from django.contrib.auth import get_user_model
        from django.contrib.admin.models import LogEntry, ADDITION
        from django.contrib.contenttypes.models import ContentType
        from . import views as api_views

        user1 = get_user_model().objects.create_user(username='u9', password='p9')
        user2 = get_user_model().objects.create_user(username='u10', password='p10')
        user1.is_staff = True
        user1.save(update_fields=['is_staff'])

        ct = ContentType.objects.get_for_model(Project)
        LogEntry.objects.log_action(
            user_id=user1.id,
            content_type_id=ct.pk,
            object_id=1,
            object_repr='x',
            action_flag=ADDITION,
            change_message='m1',
        )
        LogEntry.objects.log_action(
            user_id=user2.id,
            content_type_id=ct.pk,
            object_id=2,
            object_repr='y',
            action_flag=ADDITION,
            change_message='m2',
        )

        factory = APIRequestFactory()
        req = factory.get('/api/audit-logs/')
        force_authenticate(req, user=user1)
        resp = api_views.AuditLogViewSet.as_view({'get': 'list'})(req)
        self.assertEqual(resp.status_code, 200)
        users = {r.get('user') for r in resp.data}
        self.assertIn(user1.id, users)
        self.assertIn(user2.id, users)

class TestEngineRenderAndStep(TestCase):
    def test_render_string_variable_placeholder(self):
        engine = TestEngine(variables={'base_url': 'http://api.example.com'})
        self.assertEqual(engine.render_string('{{base_url}}/users'), 'http://api.example.com/users')

    def test_render_string_non_string_unchanged(self):
        engine = TestEngine()
        self.assertEqual(engine.render_string(42), 42)

    def test_run_step_unknown_type_records_failure(self):
        engine = TestEngine()
        ok = engine.run_step({'type': 'unknown'})
        self.assertFalse(ok)
        self.assertTrue(any('未知步骤' in str(x) for x in engine.log))


class TestPublicAndAuthEndpoints(DjangoTestCase):
    def test_health_check_returns_ok(self):
        from django.test import RequestFactory
        rf = RequestFactory()
        resp = health_check(rf.get('/api/health/'))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode('utf-8'))
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('database'), 'ok')

    def test_task_status_returns_shape(self):
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user('tasku1', 'StrongPass2026!')
        rf = RequestFactory()
        req = rf.get('/api/task-status/x/')
        force_authenticate(req, user=user)
        with patch('api.views.get_task_owner', return_value=user.id), patch('api.views.AsyncResult') as AR:
            inst = MagicMock()
            inst.status = 'PENDING'
            inst.ready.return_value = False
            inst.result = None
            AR.return_value = inst
            resp = task_status(req, 'tid-1')
        self.assertEqual(resp.status_code, 200)
        body = resp.data
        self.assertEqual(body.get('task_id'), 'tid-1')
        self.assertEqual(body.get('status'), 'pending')
        self.assertEqual(body.get('task_state'), 'PENDING')

    def test_task_status_rejects_other_users_task(self):
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user('tasku2', 'StrongPass2026!')
        user = get_user_model().objects.create_user('tasku3', 'StrongPass2026!')
        rf = RequestFactory()
        req = rf.get('/api/task-status/x/')
        force_authenticate(req, user=user)
        with patch('api.views.get_task_owner', return_value=owner.id):
            resp = task_status(req, 'tid-2')
        self.assertEqual(resp.status_code, 403)

    def test_task_status_sanitizes_ready_result_payload(self):
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user('tasku4', 'StrongPass2026!')
        rf = RequestFactory()
        req = rf.get('/api/task-status/x/')
        force_authenticate(req, user=user)
        with patch('api.views.get_task_owner', return_value=user.id), patch('api.views.AsyncResult') as AR:
            inst = MagicMock()
            inst.status = 'SUCCESS'
            inst.ready.return_value = True
            inst.result = {
                'status': 'success',
                'record_id': 12,
                'elapsed_time': '0.12',
                'secret': 'should-not-leak',
                'debug_raw': {'foo': 'bar'},
            }
            AR.return_value = inst
            resp = task_status(req, 'tid-3')
        self.assertEqual(resp.status_code, 200)
        payload = resp.data.get('result') or {}
        self.assertEqual(payload.get('status'), 'success')
        self.assertEqual(payload.get('record_id'), 12)
        self.assertNotIn('secret', payload)
        self.assertNotIn('debug_raw', payload)

    def test_task_status_wraps_non_dict_ready_result(self):
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user('tasku5', 'StrongPass2026!')
        rf = RequestFactory()
        req = rf.get('/api/task-status/x/')
        force_authenticate(req, user=user)
        with patch('api.views.get_task_owner', return_value=user.id), patch('api.views.AsyncResult') as AR:
            inst = MagicMock()
            inst.status = 'FAILURE'
            inst.ready.return_value = True
            inst.result = RuntimeError('backend exploded')
            AR.return_value = inst
            resp = task_status(req, 'tid-4')
        self.assertEqual(resp.status_code, 200)
        payload = resp.data.get('result') or {}
        self.assertEqual(payload.get('status'), 'error')
        self.assertIn('backend exploded', payload.get('message', ''))

    def test_register_rejects_short_password(self):
        from django.test import RequestFactory
        rf = RequestFactory()
        req = rf.post('/api/auth/register/', {'username': 'newreg1', 'password': '123'}, format='json')
        resp = RegisterView.as_view()(req)
        self.assertEqual(resp.status_code, 400)

    def test_register_success_with_strong_password(self):
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model
        rf = RequestFactory()
        req = rf.post(
            '/api/auth/register/',
            {'username': 'newreg2', 'password': 'StrongPass2026!'},
            format='json',
        )
        resp = RegisterView.as_view()(req)
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(get_user_model().objects.filter(username='newreg2').exists())

    def test_register_rejects_duplicate_username(self):
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_user(username='dupu', password='StrongPass2026!')
        rf = RequestFactory()
        req = rf.post(
            '/api/auth/register/',
            {'username': 'dupu', 'password': 'OtherStrong9!'},
            format='json',
        )
        resp = RegisterView.as_view()(req)
        self.assertEqual(resp.status_code, 400)


class TestLocustCodegen(TestCase):
    def test_generate_locust_code_builds_http_tasks(self):
        case = type('C', (), {})()
        case.steps = [
            {
                'type': 'http',
                'method': 'GET',
                'url': '/ping',
                'headers': {},
                'body': '',
            },
        ]
        code = generate_locust_code(case, base_url='https://example.com', variables={})
        self.assertIn('from locust import HttpUser', code)
        self.assertTrue(
            'self.client.request("GET", "/ping"' in code
            or "self.client.request('GET', '/ping'" in code
        )
        self.assertIn('example.com', code)


class TestAuditUtils(DjangoTestCase):
    def test_audit_log_creates_log_entry(self):
        from django.contrib.auth import get_user_model
        from django.contrib.admin.models import LogEntry, ADDITION
        from .audit_utils import audit_log

        user = get_user_model().objects.create_user('aul', 'StrongPass2026!')
        project = Project.objects.create(name='ap', owner=user)
        audit_log(user, project, ADDITION, '测试审计')
        self.assertTrue(LogEntry.objects.filter(user=user, object_id=str(project.pk)).exists())


class TestCryptoUtils(TestCase):
    def test_encrypt_none_returns_none(self):
        self.assertIsNone(encrypt_str(None))

    def test_encrypt_non_string_coerces_to_str(self):
        c = encrypt_str(42)
        self.assertTrue(str(c).startswith(ENC_PREFIX))
        self.assertEqual(decrypt_str(c), '42')

    def test_encrypt_decrypt_roundtrip(self):
        c = encrypt_str('secret-value')
        self.assertTrue(str(c).startswith(ENC_PREFIX))
        self.assertEqual(decrypt_str(c), 'secret-value')

    def test_encrypt_idempotent_when_already_encrypted(self):
        c = encrypt_str('x')
        self.assertEqual(encrypt_str(c), c)

    def test_decrypt_plain_string_unchanged(self):
        self.assertEqual(decrypt_str('plain'), 'plain')

    def test_decrypt_invalid_token_returns_original(self):
        bad = f'{ENC_PREFIX}not-valid-fernet-bytes'
        self.assertEqual(decrypt_str(bad), bad)

    def test_merge_masked_preserves_old_secret_when_mask_sent(self):
        old = {'token': f'{ENC_PREFIX}xx', 'k': 'v'}
        new = {'token': MASK, 'k': 'v2'}
        out = merge_masked(old, new)
        self.assertEqual(out['token'], old['token'])
        self.assertEqual(out['k'], 'v2')

    def test_merge_masked_non_dict_old_returns_new(self):
        self.assertEqual(merge_masked('nope', {'x': 1}), {'x': 1})


class TestNotifierUtils(TestCase):
    def test_send_webhook_empty_url_is_noop(self):
        self.assertFalse(Notifier.send_webhook('', 't', 'm'))

    @patch('api.utils.requests.post')
    def test_send_webhook_dingtalk_branch(self, mock_post):
        mock_post.return_value.status_code = 200
        ok = Notifier.send_webhook('https://oapi.dingtalk.com/robot/send?access_token=x', 't', 'm')
        self.assertTrue(ok)
        args, kwargs = mock_post.call_args
        self.assertIn('application/json', kwargs.get('headers', {}).get('Content-Type', ''))

    @patch('api.utils.requests.post', side_effect=OSError('network'))
    def test_send_webhook_network_error_returns_false(self, _mock_post):
        ok = Notifier.send_webhook('https://example.com/hook', 't', 'm')
        self.assertFalse(ok)

    @patch('api.utils.requests.post')
    def test_send_webhook_wecom_branch(self, mock_post):
        mock_post.return_value.status_code = 200
        ok = Notifier.send_webhook('https://qyapi.weixin.qq.com/cgi-bin/webhook/send?k=1', 't', 'm')
        self.assertTrue(ok)


class TestViewSetIntegration(DjangoTestCase):
    def test_admin_user_list_requires_admin(self):
        from django.contrib.auth import get_user_model

        admin = get_user_model().objects.create_user('aul_admin', 'StrongPass2026!')
        admin.is_staff = True
        admin.save(update_fields=['is_staff'])
        normal = get_user_model().objects.create_user('aul_user', 'StrongPass2026!')

        factory = APIRequestFactory()
        req1 = factory.get('/api/auth/users/')
        force_authenticate(req1, user=admin)
        resp1 = AdminUserListView.as_view()(req1)
        self.assertEqual(resp1.status_code, 200)
        usernames = {row.get('username') for row in resp1.data}
        self.assertIn('aul_admin', usernames)
        self.assertIn('aul_user', usernames)

        req2 = factory.get('/api/auth/users/')
        force_authenticate(req2, user=normal)
        resp2 = AdminUserListView.as_view()(req2)
        self.assertEqual(resp2.status_code, 403)

    def test_cannot_retrieve_other_users_case(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        u1 = get_user_model().objects.create_user('iso1', 'StrongPass2026!')
        u2 = get_user_model().objects.create_user('iso2', 'StrongPass2026!')
        p = Project.objects.create(name='pp', owner=u1)
        c = DbTestCase.objects.create(project=p, title='c', status='draft', steps=[])

        factory = APIRequestFactory()
        req = factory.get(f'/api/cases/{c.id}/')
        force_authenticate(req, user=u2)
        resp = api_views.TestCaseViewSet.as_view({'get': 'retrieve'})(req, pk=str(c.id))
        self.assertEqual(resp.status_code, 404)

    def test_testrecord_report_returns_html(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('tr1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        rec = case.records.create(status='success', result_log='ok', step_results=[], elapsed_time=0.1)

        factory = APIRequestFactory()
        from . import views as api_views
        req = factory.get(f'/api/records/{rec.id}/report/')
        force_authenticate(req, user=user)
        resp = api_views.TestRecordViewSet.as_view({'get': 'report'})(req, pk=str(rec.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'<!doctype html>', resp.content.lower())

    def test_testrecord_report_json_format(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rj1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        rec = case.records.create(
            status='success',
            result_log='line1',
            step_results=[{'name': 'HTTP', 'status': 'success', 'elapsed': '0.1'}],
            elapsed_time=1.0,
        )
        factory = APIRequestFactory()
        req = factory.get(f'/api/records/{rec.id}/report/?format=json')
        force_authenticate(req, user=user)
        resp = api_views.TestRecordViewSet.as_view({'get': 'report'})(req, pk=str(rec.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('record_id'), rec.id)
        self.assertEqual(resp.data.get('result_log'), 'line1')
        self.assertEqual(len(resp.data.get('step_results') or []), 1)

    def test_suite_run_export_json(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('se1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        suite = DbTestSuite.objects.create(project=project, name='s', ordered_case_ids=[])
        run = suite.runs.create(summary={'passed': 1, 'failed': 0, 'total': 1}, stop_on_failure=False, results=[])

        factory = APIRequestFactory()
        req = factory.get(f'/api/suite-runs/{run.id}/export/?download=1')
        force_authenticate(req, user=user)
        resp = api_views.SuiteRunViewSet.as_view({'get': 'export'})(req, pk=str(run.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('suite_run_id'), run.id)
        self.assertIn('attachment', resp.get('Content-Disposition', ''))

    def test_testrecord_report_download_header(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user('tr2', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        rec = case.records.create(status='failed', result_log='', step_results=[], elapsed_time=0.0)

        factory = APIRequestFactory()
        req = factory.get(f'/api/records/{rec.id}/report/?download=1')
        force_authenticate(req, user=user)
        from . import views as api_views
        resp = api_views.TestRecordViewSet.as_view({'get': 'report'})(req, pk=str(rec.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp.get('Content-Disposition', ''))

    def test_testrecord_recent_lists_mine(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user('tr3', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=0.0)

        factory = APIRequestFactory()
        req = factory.get('/api/records/recent/')
        force_authenticate(req, user=user)
        from . import views as api_views
        resp = api_views.TestRecordViewSet.as_view({'get': 'recent'})(req)
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.data), 1)

    def test_perf_report_reads_csv(self):
        from django.contrib.auth import get_user_model
        from django.conf import settings

        user = get_user_model().objects.create_user('pf1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        perf = PerfRecord.objects.create(
            case=case, users=1, spawn_rate=1, duration='10s', status='done', csv_prefix='pfx'
        )
        base = os.path.join(str(settings.MEDIA_ROOT), 'perf', str(perf.id))
        os.makedirs(base, exist_ok=True)
        stats_path = os.path.join(base, 'pfx_stats.csv')
        with open(stats_path, 'w', encoding='utf-8', newline='') as f:
            f.write(
                'Name,Type,Request Count,Failure Count,Requests/s,Average Response Time,'
                'Median Response Time,Min Response Time,Max Response Time\n'
            )
            f.write('Aggregated,aggregated,100,5,10.5,120,100,50,300\n')

        factory = APIRequestFactory()
        req = factory.get(f'/api/perf-records/{perf.id}/report/')
        force_authenticate(req, user=user)
        from . import views as api_views
        resp = api_views.PerfRecordViewSet.as_view({'get': 'report'})(req, pk=str(perf.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('summary', {}).get('requests'), 100)

    def test_perf_report_404_when_no_csv(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user('pf2', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        perf = PerfRecord.objects.create(
            case=case, users=1, spawn_rate=1, duration='10s', status='done', csv_prefix='none'
        )

        factory = APIRequestFactory()
        req = factory.get(f'/api/perf-records/{perf.id}/report/')
        force_authenticate(req, user=user)
        from . import views as api_views
        resp = api_views.PerfRecordViewSet.as_view({'get': 'report'})(req, pk=str(perf.id))
        self.assertEqual(resp.status_code, 404)

    def test_case_versions_list(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views
        from . import models as api_models

        user = get_user_model().objects.create_user('cv1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        api_models.TestCaseVersion.objects.create(case=case, version=1, snapshot={'title': 'c'}, created_by=user)

        factory = APIRequestFactory()
        req = factory.get(f'/api/cases/{case.id}/versions/')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'get': 'versions'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_restore_version_updates_case(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views
        from . import models as api_models

        user = get_user_model().objects.create_user('rv1', 'StrongPass2026!')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='old', status='draft', steps=[])
        api_models.TestCaseVersion.objects.create(
            case=case,
            version=1,
            snapshot={'title': 'restored-title', 'steps': [], 'variables': {}, 'tags': [], 'setup_sql': '', 'teardown_sql': '', 'status': 'draft'},
            created_by=user,
        )

        factory = APIRequestFactory()
        req = factory.post(f'/api/cases/{case.id}/restore_version/', {'version': 1}, format='json')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'restore_version'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        case.refresh_from_db()
        self.assertEqual(case.title, 'restored-title')

    def test_project_list_respects_limit_query(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('pl1', 'StrongPass2026!')
        for i in range(3):
            Project.objects.create(name=f'p{i}', owner=user)

        factory = APIRequestFactory()
        req = factory.get('/api/projects/?limit=2')
        force_authenticate(req, user=user)
        resp = api_views.ProjectViewSet.as_view({'get': 'list'})(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_audit_logs_filter_add_action(self):
        from django.contrib.auth import get_user_model
        from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
        from django.contrib.contenttypes.models import ContentType
        from . import views as api_views

        user = get_user_model().objects.create_user('al1', 'StrongPass2026!')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        ct = ContentType.objects.get_for_model(Project)
        LogEntry.objects.log_action(
            user_id=user.id,
            content_type_id=ct.pk,
            object_id=99,
            object_repr='x',
            action_flag=CHANGE,
            change_message='chg',
        )
        LogEntry.objects.log_action(
            user_id=user.id,
            content_type_id=ct.pk,
            object_id=100,
            object_repr='y',
            action_flag=ADDITION,
            change_message='add',
        )

        factory = APIRequestFactory()
        req = factory.get('/api/audit-logs/?action=add')
        force_authenticate(req, user=user)
        resp = api_views.AuditLogViewSet.as_view({'get': 'list'})(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(all(r.get('action_flag') == ADDITION for r in resp.data))

    def test_suite_runs_action(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('sr1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        suite = DbTestSuite.objects.create(project=project, name='s', ordered_case_ids=[case.id])
        suite.runs.create(summary={}, stop_on_failure=False, results=[])

        factory = APIRequestFactory()
        req = factory.get(f'/api/suites/{suite.id}/runs/')
        force_authenticate(req, user=user)
        resp = api_views.TestSuiteViewSet.as_view({'get': 'runs'})(req, pk=str(suite.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_case_run_enqueues_celery_task(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rq1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        EnvConfig.objects.create(
            project=project, name='e', base_url='https://example.com', variables={}, is_default=True
        )
        case = DbTestCase.objects.create(project=project, title='c', status='active', steps=[])

        factory = APIRequestFactory()
        req = factory.post(f'/api/cases/{case.id}/run/', {}, format='json')
        force_authenticate(req, user=user)
        with patch('api.views_case.run_test_case_task') as m_task:
            m_task.delay.return_value = MagicMock(id='fake-task-id')
            resp = api_views.TestCaseViewSet.as_view({'post': 'run'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('task_id'), 'fake-task-id')
        m_task.delay.assert_called_once()
        called = m_task.delay.call_args
        self.assertEqual(called.args[0], case.id)
        self.assertEqual(called.args[2], {})
        self.assertEqual(called.args[3], 0)

    def test_case_run_accepts_retry_times(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rq2', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        env = EnvConfig.objects.create(
            project=project, name='e', base_url='https://example.com', variables={}, is_default=True
        )
        case = DbTestCase.objects.create(project=project, title='c', status='active', steps=[])

        factory = APIRequestFactory()
        req = factory.post(f'/api/cases/{case.id}/run/', {'retry_times': 2}, format='json')
        force_authenticate(req, user=user)
        with patch('api.views_case.run_test_case_task') as m_task:
            m_task.delay.return_value = MagicMock(id='fake-task-id')
            resp = api_views.TestCaseViewSet.as_view({'post': 'run'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('retry_times'), 2)
        m_task.delay.assert_called_once_with(case.id, env.id, {}, 2)

    def test_case_run_rejects_retry_times_out_of_range(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rq3', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        DbTestCase.objects.create(project=project, title='c', status='active', steps=[])
        case = DbTestCase.objects.filter(project=project).first()

        factory = APIRequestFactory()
        req = factory.post(f'/api/cases/{case.id}/run/', {'retry_times': 9}, format='json')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'run'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 400)

    def test_case_run_smart_enqueues_with_strategy(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rq4', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        env = EnvConfig.objects.create(
            project=project, name='e', base_url='https://example.com', variables={}, is_default=True
        )
        case = DbTestCase.objects.create(
            project=project,
            title='smart',
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '/ping'}],
        )
        # 制造波动样本
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=1.0)
        case.records.create(status='failed', result_log='', step_results=[], elapsed_time=1.1)
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=1.2)
        case.records.create(status='error', result_log='', step_results=[], elapsed_time=1.3)

        factory = APIRequestFactory()
        req = factory.post(
            f'/api/cases/{case.id}/run_smart/',
            {'target_success': 0.9, 'max_attempts': 4},
            format='json',
        )
        force_authenticate(req, user=user)
        with patch('api.views_case.run_test_case_task') as m_task:
            m_task.delay.return_value = MagicMock(id='smart-task-id')
            resp = api_views.TestCaseViewSet.as_view({'post': 'run_smart'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('task_id'), 'smart-task-id')
        self.assertIn('strategy', resp.data)
        self.assertIn('retry_times', resp.data)
        called = m_task.delay.call_args
        self.assertEqual(called.args[0], case.id)
        self.assertEqual(called.args[1], env.id)
        self.assertEqual(called.args[2], {})
        self.assertTrue(0 <= int(called.args[3]) <= 3)

    def test_run_perf_rejects_invalid_duration(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rp1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        EnvConfig.objects.create(
            project=project, name='e', base_url='https://example.com', variables={}, is_default=True
        )
        case = DbTestCase.objects.create(
            project=project,
            title='c',
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '/ping'}],
        )

        factory = APIRequestFactory()
        req = factory.post(
            f'/api/cases/{case.id}/run_perf/',
            {'users': 2, 'spawn_rate': 1, 'duration': 'not-a-duration'},
            format='json',
        )
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'run_perf'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 400)

    def test_run_perf_rejects_users_out_of_range(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rp2', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        EnvConfig.objects.create(
            project=project, name='e', base_url='https://example.com', variables={}, is_default=True
        )
        case = DbTestCase.objects.create(
            project=project,
            title='c',
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '/ping'}],
        )

        factory = APIRequestFactory()
        req = factory.post(
            f'/api/cases/{case.id}/run_perf/',
            {'users': 500, 'spawn_rate': 1, 'duration': '10s'},
            format='json',
        )
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'run_perf'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 400)

    def test_run_perf_rejects_ui_only_case(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('rp3', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        EnvConfig.objects.create(
            project=project, name='e', base_url='https://example.com', variables={}, is_default=True
        )
        case = DbTestCase.objects.create(
            project=project,
            title='ui-only',
            status='active',
            steps=[{'type': 'ui', 'action': 'open', 'url': 'https://example.com'}],
        )

        factory = APIRequestFactory()
        req = factory.post(
            f'/api/cases/{case.id}/run_perf/',
            {'users': 2, 'spawn_rate': 1, 'duration': '10s'},
            format='json',
        )
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'run_perf'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('HTTP', str(resp.data.get('detail', '')))

    def test_case_records_action(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('cr1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(project=project, title='c', status='draft', steps=[])
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=0.0)

        factory = APIRequestFactory()
        req = factory.get(f'/api/cases/{case.id}/records/')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'get': 'records'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_case_quality_insight_action(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('qi1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(
            project=project,
            title='quality',
            status='active',
            steps=[
                {'type': 'http', 'method': 'GET', 'url': '/ping', 'assertions': [{'source': 'status_code', 'operator': 'eq', 'expected': '200'}], 'capture': {'x': {'from': 'json', 'path': 'a'}}},
                {'type': 'ui', 'action': 'wait_visible', 'selector': '#x', 'by': 'css'},
            ],
            tags=['demo'],
            variables={'k': 'v'},
        )
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=1.2)
        case.records.create(status='failed', result_log='', step_results=[], elapsed_time=2.2)

        factory = APIRequestFactory()
        req = factory.get(f'/api/cases/{case.id}/quality_insight/')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'get': 'quality_insight'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('overall_score', resp.data)
        self.assertIn('dimensions', resp.data)
        self.assertIn('suggestions', resp.data)
        self.assertTrue(isinstance(resp.data.get('suggestions'), list))

    def test_case_flaky_insight_action(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('fi1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(
            project=project,
            title='flaky',
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '/ping'}],
        )
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=1.0)
        case.records.create(status='failed', result_log='', step_results=[], elapsed_time=1.5)
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=1.3)
        case.records.create(status='error', result_log='', step_results=[], elapsed_time=1.1)

        factory = APIRequestFactory()
        req = factory.get(f'/api/cases/{case.id}/flaky_insight/')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'get': 'flaky_insight'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('flaky_score', resp.data)
        self.assertIn('risk_level', resp.data)
        self.assertIn(resp.data.get('risk_level'), {'low', 'medium', 'high', 'unknown'})
        self.assertTrue(0 <= int(resp.data.get('flaky_score', 0)) <= 100)
        self.assertIn('suggested_attempts', resp.data)
        self.assertIn('projections', resp.data)
        self.assertTrue(isinstance(resp.data.get('projections'), list))
        self.assertIn('methodology', resp.data)
        self.assertIn('assumptions', resp.data['methodology'])

    def test_case_experiment_summary_action(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('es1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(
            project=project,
            title='exp',
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '/ping'}],
        )
        case.records.create(status='success', result_log='', step_results=[], elapsed_time=1.0)
        case.records.create(status='failed', result_log='', step_results=[], elapsed_time=1.2)

        factory = APIRequestFactory()
        req = factory.get(f'/api/cases/{case.id}/experiment_summary/')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'get': 'experiment_summary'})(req, pk=str(case.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('execution_stats', resp.data)
        self.assertIn('flaky_analysis', resp.data)
        self.assertIn('strategy_comparison', resp.data)
        self.assertEqual(resp.data['execution_stats']['sample_size'], 2)
        self.assertGreaterEqual(len(resp.data['strategy_comparison']), 5)

    def test_import_openapi_creates_cases(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('io1', 'StrongPass2026!')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p', owner=user)
        payload = {
            'project': project.id,
            'spec': {
                'openapi': '3.0.0',
                'paths': {
                    '/users': {
                        'get': {'summary': 'List users'},
                        'post': {'summary': 'Create user'},
                    },
                },
            },
        }
        factory = APIRequestFactory()
        req = factory.post('/api/cases/import-openapi/', payload, format='json')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'import_openapi'})(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('count'), 2)
        self.assertTrue(DbTestCase.objects.filter(project=project, title__icontains='GET /users').exists())

    def test_import_openapi_rejects_invalid_paths_shape(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('io2', 'StrongPass2026!')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p', owner=user)
        payload = {'project': project.id, 'spec': {'openapi': '3.0.0', 'paths': []}}
        factory = APIRequestFactory()
        req = factory.post('/api/cases/import-openapi/', payload, format='json')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'import_openapi'})(req)
        self.assertEqual(resp.status_code, 400)

    def test_import_openapi_rejects_oversized_yaml(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('io3', 'StrongPass2026!')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p', owner=user)
        payload = {'project': project.id, 'spec_yaml': 'a' * 1_500_001}
        factory = APIRequestFactory()
        req = factory.post('/api/cases/import-openapi/', payload, format='json')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'import_openapi'})(req)
        self.assertEqual(resp.status_code, 400)

    def test_import_openapi_conflict_skip_keeps_existing(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('io4', 'StrongPass2026!')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p', owner=user)
        title = 'GET /users - List users'
        existing = DbTestCase.objects.create(
            project=project,
            title=title,
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '{{base_url}}/old', 'headers': {}, 'body': ''}],
        )
        payload = {
            'project': project.id,
            'on_conflict': 'skip',
            'spec': {
                'openapi': '3.0.0',
                'paths': {'/users': {'get': {'summary': 'List users'}}},
            },
        }
        factory = APIRequestFactory()
        req = factory.post('/api/cases/import-openapi/', payload, format='json')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'import_openapi'})(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('count'), 0)
        existing.refresh_from_db()
        self.assertEqual(existing.steps[0].get('url'), '{{base_url}}/old')

    def test_import_openapi_conflict_overwrite_updates_existing(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('io5', 'StrongPass2026!')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        project = Project.objects.create(name='p', owner=user)
        title = 'GET /users - List users'
        existing = DbTestCase.objects.create(
            project=project,
            title=title,
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '{{base_url}}/old', 'headers': {}, 'body': ''}],
        )
        payload = {
            'project': project.id,
            'on_conflict': 'overwrite',
            'spec': {
                'openapi': '3.0.0',
                'paths': {'/users': {'get': {'summary': 'List users'}}},
            },
        }
        factory = APIRequestFactory()
        req = factory.post('/api/cases/import-openapi/', payload, format='json')
        force_authenticate(req, user=user)
        resp = api_views.TestCaseViewSet.as_view({'post': 'import_openapi'})(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('count'), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.status, 'draft')
        self.assertEqual(existing.steps[0].get('url'), '{{base_url}}/users')

    def test_suite_export_locust_returns_attachment(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('su1', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        case = DbTestCase.objects.create(
            project=project,
            title='c',
            status='active',
            steps=[{'type': 'http', 'method': 'GET', 'url': '/ping', 'headers': {}, 'body': ''}],
        )
        suite = DbTestSuite.objects.create(project=project, name='suite-a', ordered_case_ids=[case.id])

        factory = APIRequestFactory()
        req = factory.get(f'/api/suites/{suite.id}/export_locust/')
        force_authenticate(req, user=user)
        resp = api_views.TestSuiteViewSet.as_view({'get': 'export_locust'})(req, pk=str(suite.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp.get('Content-Disposition', ''))

    def test_suite_run_enqueues_task(self):
        from django.contrib.auth import get_user_model
        from . import views as api_views

        user = get_user_model().objects.create_user('su3', 'StrongPass2026!')
        project = Project.objects.create(name='p', owner=user)
        suite = DbTestSuite.objects.create(project=project, name='suite-c', ordered_case_ids=[])
        EnvConfig.objects.create(project=project, name='env', base_url='https://example.com', variables={}, is_default=True)

        factory = APIRequestFactory()
        req = factory.post(f'/api/suites/{suite.id}/run/', {}, format='json')
        force_authenticate(req, user=user)
        with patch('api.views_suite.run_test_suite_task') as m_task:
            m_task.delay.return_value = MagicMock(id='suite-task-1')
            resp = api_views.TestSuiteViewSet.as_view({'post': 'run'})(req, pk=str(suite.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('task_id'), 'suite-task-1')
        m_task.delay.assert_called_once()


class TestFlakyAnalysisPure(TestCase):
    def test_empty_statuses(self):
        r = compute_flaky_analysis_from_statuses([])
        self.assertEqual(r['sample_size'], 0)
        self.assertEqual(r['risk_level'], 'unknown')
        self.assertIn('methodology', r)

    def test_all_success_stable(self):
        r = compute_flaky_analysis_from_statuses(['success'] * 12)
        self.assertEqual(r['failure_rate'], 0.0)
        self.assertEqual(r['risk_level'], 'low')

    def test_all_failed_high_risk(self):
        r = compute_flaky_analysis_from_statuses(['failed'] * 12)
        self.assertEqual(r['failure_rate'], 1.0)
        self.assertEqual(r['risk_level'], 'high')

    def test_alternating_high_transition(self):
        r = compute_flaky_analysis_from_statuses(['success', 'failed'] * 6)
        self.assertGreater(r['transition_rate'], 0.85)

    def test_error_counts_as_failure(self):
        r = compute_flaky_analysis_from_statuses(['success', 'error'])
        self.assertEqual(r['sample_size'], 2)
        self.assertEqual(r['failure_rate'], 0.5)


class TestTaskTracker(DjangoTestCase):
    def test_bind_and_get_task_owner(self):
        bind_task_owner('tid-abc', 123)
        self.assertEqual(get_task_owner('tid-abc'), 123)

    def test_bind_task_owner_ignores_empty(self):
        bind_task_owner('', 1)
        bind_task_owner('tid-z', None)
        self.assertIsNone(get_task_owner(''))
        self.assertIsNone(get_task_owner('tid-z'))
