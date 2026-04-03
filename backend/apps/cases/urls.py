from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import TestCaseViewSet

router = SimpleRouter()
router.register('', TestCaseViewSet, basename='case')

urlpatterns = [
    path('', include(router.urls)),
]
