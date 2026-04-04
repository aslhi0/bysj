from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.schemas import get_schema_view
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    ProjectViewSet, TestCaseViewSet, TestSuiteViewSet, 
    TestRecordViewSet, SuiteRunViewSet, EnvConfigViewSet, 
    CrontabScheduleViewSet, PeriodicTaskViewSet, PerfRecordViewSet,
    health_check, task_status, register
)

router = DefaultRouter()
router.register(r'projects', ProjectViewSet)
router.register(r'envs', EnvConfigViewSet)
router.register(r'crontabs', CrontabScheduleViewSet)
router.register(r'schedules', PeriodicTaskViewSet)
router.register(r'perf-records', PerfRecordViewSet)
router.register(r'cases', TestCaseViewSet)
router.register(r'suites', TestSuiteViewSet)
router.register(r'records', TestRecordViewSet)
router.register(r'suite-runs', SuiteRunViewSet)

schema_view = get_schema_view(title='AutoTest API', version='1.0.0', permission_classes=[AllowAny])

urlpatterns = [
    path('health/', health_check),
    path('schema/', schema_view),
    path('auth/register/', register),
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('task-status/<str:task_id>/', task_status),
    path('', include(router.urls)),
]
