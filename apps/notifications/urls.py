from rest_framework.routers import SimpleRouter

from .views import NotificationViewSet

router = SimpleRouter()
router.register("", NotificationViewSet, basename="notifications")
urlpatterns = router.urls
