from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("staff", views.StaffQuoteViewSet, basename="staff-quotes")
router.register("", views.QuoteViewSet, basename="quotes")

urlpatterns = router.urls
