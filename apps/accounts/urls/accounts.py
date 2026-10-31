from django.urls import path
from rest_framework.routers import SimpleRouter

from .. import views

router = SimpleRouter(trailing_slash=True)
router.register("company/members", views.CompanyMemberViewSet, basename="company-members")
router.register("company/addresses", views.AddressViewSet, basename="company-addresses")

company = views.CompanyViewSet.as_view({"get": "list", "post": "create", "patch": "update_company"})

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("company/", company, name="company"),
    path("company/switch/", views.CompanyViewSet.as_view({"post": "switch"}), name="company-switch"),
    path("invitations/<str:token>/", views.AcceptInvitationView.as_view(), name="invitation-accept"),
    *router.urls,
]
