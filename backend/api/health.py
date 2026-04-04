"""健康检查：用于负载均衡与 Docker healthcheck。"""
from django.db import connection
from django.http import JsonResponse


def health_check(request):
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        db_ok = False

    if db_ok:
        payload = {
            'status': 'ok',
            'service': 'AutoTest Backend v1.0',
            'database': 'ok',
        }
        return JsonResponse(payload, status=200)

    return JsonResponse(
        {
            'status': 'degraded',
            'service': 'AutoTest Backend v1.0',
            'database': 'error',
        },
        status=503,
    )
