"""Common queryset helpers to keep view logic concise."""

from django.db.models import Q


def apply_project_access_filter(qs, user, project_path="project"):
    """Limit queryset to projects the user owns or is an active member of."""
    if user.is_staff or user.is_superuser:
        return qs

    if project_path:
        owner_field = f"{project_path}__owner"
        member_user_field = f"{project_path}__members__user"
        member_active_field = f"{project_path}__members__is_active"
    else:
        owner_field = "owner"
        member_user_field = "members__user"
        member_active_field = "members__is_active"

    return qs.filter(
        Q(**{owner_field: user}) | Q(**{member_user_field: user, member_active_field: True})
    ).distinct()
