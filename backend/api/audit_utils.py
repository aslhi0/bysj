"""将关键操作写入 Django admin LogEntry，供审计日志 API 查询。"""
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType


def audit_log(user, obj, action_flag, message):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return
        ct = ContentType.objects.get_for_model(obj.__class__)
        LogEntry.objects.log_action(
            user_id=user.id,
            content_type_id=ct.pk,
            object_id=obj.pk,
            object_repr=str(obj)[:200],
            action_flag=action_flag,
            change_message=str(message or '')[:2000],
        )
    except Exception:
        return
