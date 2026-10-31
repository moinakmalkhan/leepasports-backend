from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("products", views.ProductViewSet, basename="products")
router.register("fabrics", views.FabricViewSet, basename="fabrics")
router.register("size-groups", views.SizeGroupViewSet, basename="size-groups")

urlpatterns = [
    path("categories/", views.CategoryTreeView.as_view(), name="category-tree"),
    path("categories/<slug:slug>/", views.CategoryDetailView.as_view(), name="category-detail"),
    *router.urls,
]
