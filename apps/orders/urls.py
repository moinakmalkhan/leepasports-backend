from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("shipping-methods", views.ShippingMethodListView, basename="shipping-methods")
router.register("staff", views.StaffOrderViewSet, basename="staff-orders")
router.register("", views.OrderViewSet, basename="orders")

urlpatterns = [path("track/", views.PublicOrderTrackingView.as_view(), name="order-track"), *router.urls]
