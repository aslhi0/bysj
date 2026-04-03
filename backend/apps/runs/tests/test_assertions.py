import json

import pytest
import requests

from apps.runs.assertions import AssertionErrorDetail, get_by_path, run_http_assertions


def test_get_by_path_dict_and_list():
    data = {'a': {'b': 1}, 'items': [{'id': 9}]}
    assert get_by_path(data, 'a.b') == 1
    assert get_by_path(data, 'items.0.id') == 9


def test_run_status_code_and_elapsed():
    r = requests.Response()
    r.status_code = 200
    r._content = b'{}'
    r.encoding = 'utf-8'
    run_http_assertions(r, 0.1, {'status_code': 200, 'max_elapsed_seconds': 1})
    with pytest.raises(AssertionErrorDetail, match='状态码'):
        run_http_assertions(r, 0.1, {'status_code': 404})


def test_json_paths_equals():
    r = requests.Response()
    r.status_code = 200
    r._content = json.dumps({'code': 0, 'data': {'name': 'ok'}}).encode()
    r.encoding = 'utf-8'
    run_http_assertions(
        r,
        0.01,
        {'json_paths': [{'path': 'code', 'equals': 0}, {'path': 'data.name', 'equals': 'ok'}]},
    )


def test_json_schema():
    pytest.importorskip('jsonschema')
    r = requests.Response()
    r.status_code = 200
    r._content = json.dumps({'id': 1, 'name': 'x'}).encode()
    r.encoding = 'utf-8'
    run_http_assertions(
        r,
        0.01,
        {
            'json_schema': {
                'type': 'object',
                'required': ['id', 'name'],
                'properties': {'id': {'type': 'integer'}, 'name': {'type': 'string'}},
            }
        },
    )
