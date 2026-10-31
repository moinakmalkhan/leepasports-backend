from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("saved-lists", views.SavedListViewSet, basename="saved-lists")

urlpatterns = [
    path("", views.CartView.as_view(), name="cart"),
    path("items/<uuid:uid>/", views.CartItemView.as_view(), name="cart-item"),
    path("quick-order/", views.QuickOrderView.as_view(), name="cart-quick-order"),
    *router.urls,
]
