import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from apps.cases.openapi_import import build_operations, import_from_spec, load_spec_dict
from apps.projects.models import Project


@pytest.fixture
def project(db):
    return Project.objects.create(name='Demo', description='')


MIN_OPENAPI3 = {
    'openapi': '3.0.0',
    'info': {'title': 'T', 'version': '1'},
    'servers': [{'url': 'https://api.example.com/v1'}],
    'paths': {
        '/users/{userId}': {
            'get': {'summary': 'Get user', 'responses': {'200': {'description': 'ok'}}},
            'post': {
                'summary': 'Create',
                'requestBody': {
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {'name': {'type': 'string'}},
                            }
                        }
                    }
                },
                'responses': {'201': {'description': 'created'}},
            },
        }
    },
}

MIN_SWAGGER2 = {
    'swagger': '2.0',
    'info': {'title': 'S', 'version': '1'},
    'host': 'pet.example.com',
    'basePath': '/v2',
    'schemes': ['https'],
    'paths': {
        '/pets/{id}': {
            'get': {'operationId': 'getPet', 'responses': {'200': {'description': 'ok'}}}
        }
    },
}


def test_build_operations_oas3():
    ops = build_operations(MIN_OPENAPI3)
    assert len(ops) == 2
    get_u = next(o for o in ops if o['method'] == 'get')
    assert '{{userId}}' in get_u['step']['url']
    assert get_u['step']['url'].startswith('{{base_url}}')
    assert get_u['variables']['base_url'] == 'https://api.example.com/v1'
    post_u = next(o for o in ops if o['method'] == 'post')
    assert post_u['step'].get('body') == {'name': ''}


def test_build_operations_swagger2():
    ops = build_operations(MIN_SWAGGER2)
    assert len(ops) == 1
    assert ops[0]['step']['method'] == 'GET'
    assert '{{id}}' in ops[0]['step']['url']
    assert ops[0]['variables']['base_url'] == 'https://pet.example.com/v2'


@pytest.mark.django_db
def test_import_from_spec_creates_cases(db):
    project = Project.objects.create(name='P', description='')
    result = import_from_spec(MIN_OPENAPI3, project)
    assert result['count'] == 2
    assert len(result['created_ids']) == 2


@pytest.mark.django_db
def test_api_import_openapi_spec_body(client, project):
    r = client.post(
        '/api/cases/import-openapi/',
        data=json.dumps({'project': project.id, 'spec': MIN_OPENAPI3}),
        content_type='application/json',
    )
    assert r.status_code == 201
    body = r.json()
    assert body['count'] == 2


@pytest.mark.django_db
def test_api_import_openapi_validation_requires_single_source(client, project):
    r = client.post(
        '/api/cases/import-openapi/',
        data=json.dumps({'project': project.id, 'spec': MIN_OPENAPI3, 'spec_url': 'https://x.com/a.json'}),
        content_type='application/json',
    )
    assert r.status_code == 400


@pytest.mark.django_db
@patch('apps.cases.openapi_import.requests.get')
def test_api_import_from_url(mock_get, client, project):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(MIN_OPENAPI3)
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp
    r = client.post(
        '/api/cases/import-openapi/',
        data=json.dumps(
            {'project': project.id, 'spec_url': 'https://example.com/openapi.json'}
        ),
        content_type='application/json',
    )
    assert r.status_code == 201
    assert r.json()['count'] == 2


def test_load_spec_dict_from_yaml_string():
    yml = yaml.dump(MIN_SWAGGER2)
    spec = load_spec_dict(spec_yaml=yml)
    assert spec['swagger'] == '2.0'
