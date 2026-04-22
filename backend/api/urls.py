from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from .health import health_check
from .views import (
    ProjectViewSet, TestCaseViewSet, TestSuiteViewSet,
    TestRecordViewSet, SuiteRunViewSet, EnvConfigViewSet,
    PerfRecordViewSet, AuditLogViewSet,
    task_status, RegisterView, ThrottledTokenObtainPairView, ThrottledTokenRefreshView, MeView, AdminUserListView,
)

router = DefaultRouter()
router.register(r'projects', ProjectViewSet)
router.register(r'envs', EnvConfigViewSet)
router.register(r'perf-records', PerfRecordViewSet)
router.register(r'cases', TestCaseViewSet)
router.register(r'suites', TestSuiteViewSet)
router.register(r'records', TestRecordViewSet)
router.register(r'suite-runs', SuiteRunViewSet)
router.register(r'audit-logs', AuditLogViewSet)

urlpatterns = [
    path('health/', health_check),
    # OpenAPI 3.0：schema + Swagger UI + Redoc，替换原 CoreAPI get_schema_view。
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('auth/register/', RegisterView.as_view()),
    path('auth/me/', MeView.as_view()),
    path('auth/users/', AdminUserListView.as_view()),
    path('auth/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('task-status/<str:task_id>/', task_status),
    path('', include(router.urls)),
]
