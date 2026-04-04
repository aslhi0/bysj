"""演示 pytest 共享 fixture（与 api/tests.py 中 Django TestCase 风格互补）。"""
import pytest


@pytest.mark.django_db
def test_user_fixture_creates_isolated_user(user_a, user_b):
    assert user_a.id != user_b.id
    assert user_a.username == 'fixture_user_a'
