from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("products", views.ProductViewSet, basename="products")
router.register("collections", views.CollectionViewSet, basename="collections")
router.register("size-groups", views.SizeGroupViewSet, basename="size-groups")

urlpatterns = [
    path("categories/", views.CategoryTreeView.as_view(), name="category-tree"),
    path("categories/<slug:slug>/", views.CategoryDetailView.as_view(), name="category-detail"),
    path("stock-alerts/", views.StockAlertView.as_view(), name="stock-alerts"),
    *router.urls,
]
