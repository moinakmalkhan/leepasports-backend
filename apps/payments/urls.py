from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("bank-accounts", views.BankAccountView, basename="bank-accounts")
router.register("staff", views.StaffPaymentViewSet, basename="staff-payments")

urlpatterns = [
    path("methods/", views.PaymentMethodsView.as_view(), name="payment-methods"),
    path("orders/<uuid:uid>/", views.OrderPaymentView.as_view(), name="order-payments"),
    *router.urls,
]
