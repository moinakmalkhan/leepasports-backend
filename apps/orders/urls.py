from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("staff", views.StaffOrderViewSet, basename="staff-orders")
router.register("returns", views.ReturnViewSet, basename="returns")
router.register("", views.OrderViewSet, basename="orders")

urlpatterns = [
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("shipping-quote/", views.ShippingQuoteView.as_view(), name="shipping-quote"),
    path("track/", views.PublicOrderTrackingView.as_view(), name="order-track"),
    *router.urls,
]
