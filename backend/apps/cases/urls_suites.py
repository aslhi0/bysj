from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .suite_views import TestSuiteViewSet

router = SimpleRouter()
router.register('', TestSuiteViewSet, basename='suite')

urlpatterns = [
    path('', include(router.urls)),
]
