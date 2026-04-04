"""Track celery task ownership for task-status authorization."""
from django.core.cache import cache

TASK_OWNER_KEY_PREFIX = "task_owner:"
TASK_OWNER_TTL_SECONDS = 24 * 60 * 60


def bind_task_owner(task_id, user_id):
    if not task_id or not user_id:
        return
    cache.set(f"{TASK_OWNER_KEY_PREFIX}{task_id}", int(user_id), TASK_OWNER_TTL_SECONDS)


def get_task_owner(task_id):
    if not task_id:
        return None
    return cache.get(f"{TASK_OWNER_KEY_PREFIX}{task_id}")
