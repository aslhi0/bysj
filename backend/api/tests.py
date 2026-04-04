from unittest import TestCase
from unittest.mock import patch

from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import Project, EnvConfig, TestCase as DbTestCase, TestSuite as DbTestSuite, PerfRecord
from .engine import TestEngine
from .tasks import run_test_case_task, run_test_suite_task
from .views import PerfRecordViewSet
from .crypto_utils import decrypt_json, ENC_PREFIX, MASK

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
        with patch('api.engine.requests.request', return_value=resp) as _p:
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
        project = Project.objects.create(name='p1', owner=user)

        factory = APIRequestFactory()
        req = factory.post('/api/envs/', {}, format='json')
        force_authenticate(req, user=user)

        payload = {
            'project': project.id,
            'name': 'env',
            'base_url': 'https://example.com',
            'variables': {'token': 'abc', 'k': 'v'},
            'db_config': {'password': 'pw', 'sqlite_path': 'db.sqlite3'},
            'is_default': True,
        }
        create_req = factory.post('/api/envs/', payload, format='json')
        force_authenticate(create_req, user=user)
        resp = api_views.EnvConfigViewSet.as_view({'post': 'create'})(create_req)
        self.assertEqual(resp.status_code, 201)

        env_id = resp.data.get('id')
        env = EnvConfig.objects.get(id=env_id)
        self.assertTrue(str(env.variables.get('token', '')).startswith(ENC_PREFIX))
        self.assertTrue(str(env.db_config.get('password', '')).startswith(ENC_PREFIX))
        plain_vars = decrypt_json(env.variables)
        self.assertEqual(plain_vars.get('token'), 'abc')

        list_req = factory.get('/api/envs/')
        force_authenticate(list_req, user=user)
        list_resp = api_views.EnvConfigViewSet.as_view({'get': 'list'})(list_req)
        self.assertEqual(list_resp.status_code, 200)
        row = list_resp.data[0]
        self.assertEqual(row['variables']['token'], MASK)
        self.assertEqual(row['db_config']['password'], MASK)

    def test_case_version_is_created_on_create_and_update(self):
        from . import views as api_views
        from . import models as api_models
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='u5', password='p5')
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
