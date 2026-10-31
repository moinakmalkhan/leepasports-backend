from django.urls import path

from .views import CouponPreviewView

urlpatterns = [path("coupons/preview/", CouponPreviewView.as_view(), name="coupon-preview")]
