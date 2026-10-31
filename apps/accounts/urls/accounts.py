from django.urls import path
from rest_framework.routers import SimpleRouter

from .. import views

router = SimpleRouter(trailing_slash=True)
router.register("addresses", views.AddressViewSet, basename="addresses")

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("provinces/", views.ProvincesView.as_view(), name="provinces"),
    path("newsletter/", views.NewsletterView.as_view(), name="newsletter"),
    *router.urls,
]
