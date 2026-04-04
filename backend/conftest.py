"""pytest 共享 fixtures（集成测试 / API 隔离场景）。"""
import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def strong_password():
    return 'UniSecurePass2026!'


@pytest.fixture
def user_a(db, strong_password):
    User = get_user_model()
    return User.objects.create_user(username='fixture_user_a', password=strong_password)


@pytest.fixture
def user_b(db, strong_password):
    User = get_user_model()
    return User.objects.create_user(username='fixture_user_b', password=strong_password)
