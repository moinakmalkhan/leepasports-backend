from django.urls import path

from .views import PriceQuoteView

urlpatterns = [path("quote/", PriceQuoteView.as_view(), name="price-quote")]
