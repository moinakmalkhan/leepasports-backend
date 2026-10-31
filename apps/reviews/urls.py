from rest_framework.routers import SimpleRouter

from .views import ReviewViewSet

router = SimpleRouter()
router.register("", ReviewViewSet, basename="reviews")
urlpatterns = router.urls
