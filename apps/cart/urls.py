from django.urls import path

from . import views

urlpatterns = [
    path("", views.CartView.as_view(), name="cart"),
    path("items/<uuid:uid>/", views.CartItemView.as_view(), name="cart-item"),
    path("coupon/", views.CartCouponView.as_view(), name="cart-coupon"),
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
]
