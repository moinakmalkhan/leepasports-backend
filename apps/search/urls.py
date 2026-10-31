from django.urls import path

from . import views

urlpatterns = [
    path("", views.SearchView.as_view(), name="search"),
    path("suggest/", views.SuggestView.as_view(), name="search-suggest"),
    path("trending/", views.TrendingView.as_view(), name="search-trending"),
    path("recommendations/", views.RecommendationsView.as_view(), name="recommendations"),
    path("recently-viewed/", views.RecentlyViewedView.as_view(), name="recently-viewed"),
]
