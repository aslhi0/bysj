"""Shared helpers for DRF viewsets."""


def apply_limit_from_request(qs, request, *, max_limit=500):
    """Apply optional `?limit=` slice with defensive parsing."""
    limit = request.query_params.get("limit")
    if not limit:
        return qs

    try:
        n = int(limit)
    except Exception:
        return qs

    if n <= 0:
        return qs
    return qs[: min(n, max_limit)]
