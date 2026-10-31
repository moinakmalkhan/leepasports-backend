from rest_framework.routers import SimpleRouter

from .views import ConversationViewSet

router = SimpleRouter()
router.register("conversations", ConversationViewSet, basename="conversations")
urlpatterns = router.urls
