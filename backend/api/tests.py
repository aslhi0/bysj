from unittest import TestCase
from unittest.mock import patch

from .engine import TestEngine

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
