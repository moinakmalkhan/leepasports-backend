from django.urls import path

from . import views

urlpatterns = [
    path("storefront/", views.StorefrontView.as_view(), name="storefront"),
    path("faq/", views.FAQView.as_view(), name="faq"),
    path("pages/<slug:slug>/", views.PageView.as_view(), name="page"),
]
