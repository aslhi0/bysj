from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProjectViewSet, TestCaseViewSet, TestSuiteViewSet, 
    TestRecordViewSet, SuiteRunViewSet, EnvConfigViewSet, 
    CrontabScheduleViewSet, PeriodicTaskViewSet, PerfRecordViewSet,
    health_check, task_status
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

urlpatterns = [
    path('health/', health_check),
    path('task-status/<str:task_id>/', task_status),
    path('', include(router.urls)),
]
