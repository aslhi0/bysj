from apps.runs.variables import expand_strings, substitute_placeholders


def test_substitute_placeholders():
    ctx = {'a': 1, 'b': 'hi'}
    out = substitute_placeholders('{{a}}-{{b}}', ctx, lambda k: 'X')
    assert out == '1-hi'
    out2 = substitute_placeholders('{{missing}}', ctx, lambda k: '')
    assert out2 == ''


def test_expand_nested():
    ctx = {'x': 'ok'}

    def repl(s: str) -> str:
        return substitute_placeholders(s, ctx, lambda k: '')

    data = {'u': '{{x}}', 'n': [1, '{{x}}']}
    assert expand_strings(data, repl) == {'u': 'ok', 'n': [1, 'ok']}
