import json
from unittest.mock import MagicMock, patch

import pytest

from apps.cases import models as case_models
from apps.projects.models import Project


@pytest.fixture
def project(db):
    return Project.objects.create(name='Demo', description='')


@pytest.mark.django_db
def test_create_suite_with_ordered_cases(client, project):
    c1 = case_models.TestCase.objects.create(
        project=project, title='A', steps=[{'type': 'http', 'url': 'https://a.com'}]
    )
    c2 = case_models.TestCase.objects.create(
        project=project, title='B', steps=[{'type': 'http', 'url': 'https://b.com'}]
    )
    r = client.post(
        '/api/suites/',
        data=json.dumps(
            {
                'project': project.id,
                'name': '回归',
                'description': '',
                'variables': {},
                'ordered_case_ids': [c2.id, c1.id],
            }
        ),
        content_type='application/json',
    )
    assert r.status_code == 201
    sid = r.json()['id']
    detail = client.get(f'/api/suites/{sid}/')
    assert detail.status_code == 200
    summ = detail.json()['cases_summary']
    assert [x['id'] for x in summ] == [c2.id, c1.id]


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_suite_run_order_and_summary(mock_request, client, project):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{}'
    mock_resp.json = MagicMock(return_value={})
    mock_request.return_value = mock_resp

    c1 = case_models.TestCase.objects.create(
        project=project, title='A', steps=[{'type': 'http', 'url': 'https://x.com/1'}]
    )
    c2 = case_models.TestCase.objects.create(
        project=project, title='B', steps=[{'type': 'http', 'url': 'https://x.com/2'}]
    )
    suite = case_models.TestSuite.objects.create(project=project, name='S', variables={})
    case_models.SuiteCase.objects.create(suite=suite, testcase=c2, order=0)
    case_models.SuiteCase.objects.create(suite=suite, testcase=c1, order=1)

    r = client.post(f'/api/suites/{suite.id}/run/')
    assert r.status_code == 200
    data = r.json()
    assert data['summary'] == {'total': 2, 'passed': 2, 'failed': 0}
    assert [x['case_id'] for x in data['results']] == [c2.id, c1.id]
    assert mock_request.call_count == 2
    assert 'suite_run_id' in data
    hist = client.get(f'/api/suites/{suite.id}/runs/')
    assert hist.status_code == 200
    assert len(hist.json()) == 1
    assert hist.json()[0]['id'] == data['suite_run_id']


@pytest.mark.django_db
@patch('apps.runs.executors.requests.request')
def test_suite_stop_on_failure(mock_request, client, project):
    def side_effect(method, url, **kwargs):
        r = MagicMock()
        if 'bad' in url:
            r.status_code = 500
            r.text = 'err'
            r.json = MagicMock(side_effect=Exception('no json'))
        else:
            r.status_code = 200
            r.text = '{}'
            r.json = MagicMock(return_value={})
        return r

    mock_request.side_effect = side_effect

    c1 = case_models.TestCase.objects.create(
        project=project, title='ok', steps=[{'type': 'http', 'url': 'https://x.com/good'}]
    )
    c2 = case_models.TestCase.objects.create(
        project=project, title='bad', steps=[{'type': 'http', 'url': 'https://x.com/bad'}]
    )
    c3 = case_models.TestCase.objects.create(
        project=project, title='skip', steps=[{'type': 'http', 'url': 'https://x.com/3'}]
    )
    suite = case_models.TestSuite.objects.create(project=project, name='S')
    for order, tc in enumerate([c1, c2, c3]):
        case_models.SuiteCase.objects.create(suite=suite, testcase=tc, order=order)

    r = client.post(
        f'/api/suites/{suite.id}/run/',
        data=json.dumps({'stop_on_failure': True}),
        content_type='application/json',
    )
    data = r.json()
    assert len(data['results']) == 2
    assert data['summary']['failed'] == 1
    assert data['results'][1]['status'] == 'failed'


@pytest.mark.django_db
def test_export_locust_download(client, project):
    c = case_models.TestCase.objects.create(
        project=project,
        title='api_ping',
        variables={'base': 'https://x.com'},
        steps=[
            {'type': 'ui', 'action': 'sleep', 'seconds': 0.1},
            {
                'type': 'http',
                'method': 'GET',
                'url': '{{base}}/ping',
                'headers': {'X-T': '1'},
            },
        ],
    )
    suite = case_models.TestSuite.objects.create(project=project, name='perf-suite', variables={'k': 1})
    case_models.SuiteCase.objects.create(suite=suite, testcase=c, order=0)

    r = client.get(f'/api/suites/{suite.id}/export_locust/')
    assert r.status_code == 200
    cd = r.get('Content-Disposition') or ''
    assert 'attachment' in cd.lower()
    assert 'locust_' in cd and '.py' in cd
    assert 'filename*=' in cd.lower() or 'utf-8' in cd.lower()
    text = r.content.decode('utf-8')
    compile(text, '<locust>', 'exec')
    assert 'SuiteUser' in text
    assert '{{base}}/ping' in text or '_expand' in text
    assert "'k': 1" in text or '"k": 1' in text
