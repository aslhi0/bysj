import json
from unittest.mock import MagicMock, patch

import pytest

from apps.cases import models as case_models
from apps.projects.models import Project
from apps.runs import models as runs_models


@pytest.fixture
def project(db):
    return Project.objects.create(name='Demo', description='')


@pytest.mark.django_db
def test_list_cases_empty(client):
    r = client.get('/api/cases/')
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.django_db
def test_create_and_list_case(client, project):
    r = client.post(
        '/api/cases/',
        data={
            'project': project.id,
            'title': '登录校验',
            'steps': [
                {'type': 'http', 'method': 'GET', 'url': 'https://httpbin.org/get'},
                {'type': 'ui', 'action': 'click', 'selector': '#login'},
            ],
            'status': 'draft',
        },
        content_type='application/json',
    )
    assert r.status_code == 201
    rid = r.json()['id']

    r2 = client.get('/api/cases/')
    assert len(r2.json()) == 1
    assert r2.json()[0]['id'] == rid
    assert r2.json()[0]['project_name'] == 'Demo'
    assert len(r2.json()[0]['steps']) == 2


@pytest.mark.django_db
def test_create_case_rejects_non_list_steps(client, project):
    r = client.post(
        '/api/cases/',
        data={
            'project': project.id,
            'title': 'bad',
            'steps': {'type': 'http'},
            'status': 'draft',
        },
        content_type='application/json',
    )
    assert r.status_code == 400


def _mock_json_response(status_code, body_dict):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    raw = json.dumps(body_dict)
    mock_resp.text = raw
    mock_resp.json = MagicMock(return_value=json.loads(raw))
    return mock_resp


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_run_case_http_success(mock_request, client, project):
    mock_resp = _mock_json_response(200, {'ok': True})
    mock_request.return_value = mock_resp

    tc = case_models.TestCase.objects.create(
        project=project,
        title='API用例',
        steps=[{'type': 'http', 'method': 'GET', 'url': 'https://example.com/api'}],
        status='active',
    )
    r = client.post(f'/api/cases/{tc.id}/run/')
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'success'
    assert 'record_id' in data
    rec = runs_models.TestRecord.objects.get(pk=data['record_id'])
    assert rec.testcase_id == tc.id
    assert rec.status == runs_models.TestRecord.Status.SUCCESS


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_run_case_http_4xx(mock_request, client, project):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = 'not found'
    mock_resp.json = MagicMock(side_effect=json.JSONDecodeError('Expecting value', 'x', 0))
    mock_request.return_value = mock_resp

    tc = case_models.TestCase.objects.create(
        project=project,
        title='fail',
        steps=[{'type': 'http', 'method': 'GET', 'url': 'https://example.com/missing'}],
    )
    r = client.post(f'/api/cases/{tc.id}/run/')
    assert r.status_code == 200
    assert r.json()['status'] == 'failed'


@pytest.mark.django_db
def test_run_case_invalid_step_object_logs_failure(client, project):
    tc = case_models.TestCase.objects.create(
        project=project,
        title='bad steps',
        steps=['not-a-dict'],
    )
    r = client.post(f'/api/cases/{tc.id}/run/')
    assert r.status_code == 200
    assert r.json()['status'] == 'failed'
    rec = runs_models.TestRecord.objects.get(pk=r.json()['record_id'])
    assert '非法' in rec.result_log or '非 JSON 对象' in rec.result_log


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_run_expect_status_404_with_json_assert(mock_request, client, project):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = '{"error":"not_found"}'
    mock_resp.json = MagicMock(return_value={'error': 'not_found'})
    mock_request.return_value = mock_resp
    tc = case_models.TestCase.objects.create(
        project=project,
        title='404 ok',
        steps=[
            {
                'type': 'http',
                'method': 'GET',
                'url': 'https://example.com/missing',
                'assert': {
                    'status_code': 404,
                    'json_paths': [{'path': 'error', 'equals': 'not_found'}],
                },
            }
        ],
    )
    r = client.post(f'/api/cases/{tc.id}/run/')
    assert r.json()['status'] == 'success'


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_run_json_path_mismatch_fails(mock_request, client, project):
    mock_resp = _mock_json_response(200, {'code': 1})
    mock_request.return_value = mock_resp
    tc = case_models.TestCase.objects.create(
        project=project,
        title='assert fail',
        steps=[
            {
                'type': 'http',
                'method': 'GET',
                'url': 'https://example.com/x',
                'assert': {'json_paths': [{'path': 'code', 'equals': 0}]},
            }
        ],
    )
    r = client.post(f'/api/cases/{tc.id}/run/')
    assert r.json()['status'] == 'failed'
    assert '断言失败' in r.json()['result_log']


@pytest.mark.django_db
@patch('apps.runs.executors.WebDriverWait')
@patch('apps.runs.executors.webdriver.Chrome')
@patch('apps.runs.executors.requests.request')
def test_run_mixed_http_and_ui(mock_request, mock_chrome, mock_wait, client, project):
    mock_resp = _mock_json_response(200, {})
    mock_request.return_value = mock_resp
    drv = MagicMock()
    mock_chrome.return_value = drv
    el = MagicMock()
    wait_inst = MagicMock()
    wait_inst.until = MagicMock(return_value=el)
    mock_wait.return_value = wait_inst

    tc = case_models.TestCase.objects.create(
        project=project,
        title='mix',
        steps=[
            {'type': 'http', 'method': 'GET', 'url': 'https://example.com/ping'},
            {
                'type': 'ui',
                'action': 'open',
                'url': 'https://example.com/',
                'browser': {'headless': True},
            },
            {'type': 'ui', 'action': 'click', 'selector': 'button#go'},
        ],
    )
    r = client.post(f'/api/cases/{tc.id}/run/')
    assert r.status_code == 200
    assert r.json()['status'] == 'success'
    drv.get.assert_called_once_with('https://example.com/')
    el.click.assert_called_once()
    drv.quit.assert_called_once()


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_run_capture_fills_variable_for_next_step(mock_request, client, project):
    calls: list[str] = []

    def side_effect(method, url, **kwargs):
        calls.append(url)
        r = MagicMock()
        r.status_code = 200
        r.headers = {}
        if len(calls) == 1:
            r.text = '{"access_token":"tok_xyz"}'
            r.json = MagicMock(return_value={'access_token': 'tok_xyz'})
        else:
            r.text = '{}'
            r.json = MagicMock(return_value={})
        return r

    mock_request.side_effect = side_effect
    tc = case_models.TestCase.objects.create(
        project=project,
        title='chain',
        steps=[
            {
                'type': 'http',
                'method': 'GET',
                'url': 'https://api.example.com/auth',
                'capture': {'tok': {'from': 'json', 'path': 'access_token'}},
            },
            {
                'type': 'http',
                'method': 'GET',
                'url': 'https://api.example.com/res/{{tok}}',
            },
        ],
    )
    r = client.post(f'/api/cases/{tc.id}/run/')
    assert r.json()['status'] == 'success'
    assert len(calls) == 2
    assert calls[1] == 'https://api.example.com/res/tok_xyz'


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_run_runtime_variables_override_case_variables(mock_request, client, project):
    captured: dict[str, str] = {}

    def side_effect(method, url, **kwargs):
        captured['url'] = url
        r = MagicMock()
        r.status_code = 200
        r.text = '{}'
        r.json = MagicMock(return_value={})
        r.headers = {}
        return r

    mock_request.side_effect = side_effect
    tc = case_models.TestCase.objects.create(
        project=project,
        title='override',
        variables={'host': 'https://a.com'},
        steps=[{'type': 'http', 'method': 'GET', 'url': '{{host}}/ping'}],
    )
    r = client.post(
        f'/api/cases/{tc.id}/run/',
        data=json.dumps({'variables': {'host': 'https://b.com'}}),
        content_type='application/json',
    )
    assert r.status_code == 200
    assert r.json()['status'] == 'success'
    assert captured['url'] == 'https://b.com/ping'


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_list_case_records_after_runs(mock_request, client, project):
    mock_request.return_value = _mock_json_response(200, {})
    tc = case_models.TestCase.objects.create(
        project=project,
        title='hist',
        steps=[{'type': 'http', 'method': 'GET', 'url': 'https://example.com/x'}],
    )
    client.post(f'/api/cases/{tc.id}/run/')
    client.post(f'/api/cases/{tc.id}/run/')

    r = client.get(f'/api/cases/{tc.id}/records/')
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert {x['status'] for x in data} == {runs_models.TestRecord.Status.SUCCESS}
    assert all('result_log' in x and x['id'] for x in data)
    assert data[0]['created_at'] >= data[1]['created_at']
