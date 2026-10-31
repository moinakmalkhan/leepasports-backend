from django.urls import path

from .. import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("login/google/", views.GoogleLoginView.as_view(), name="login-google"),
    path("refresh/", views.RefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("verify-email/resend/", views.ResendVerificationView.as_view(), name="verify-email-resend"),
    path("password/reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path("password/reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("password/change/", views.ChangePasswordView.as_view(), name="password-change"),
]
