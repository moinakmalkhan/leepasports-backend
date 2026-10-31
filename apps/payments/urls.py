from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("bank-accounts", views.BankAccountView, basename="bank-accounts")
router.register("staff", views.StaffPaymentViewSet, basename="staff-payments")
router.register("", views.PaymentViewSet, basename="payments")

urlpatterns = router.urls
