from django.urls import path

from .views import (
    CsrfView,
    LoginView,
    LogoutView,
    MeContextView,
    MeView,
    RecoveryCodesView,
    TwoFactorConfirmView,
    TwoFactorDisableView,
    TwoFactorLoginView,
    TwoFactorSetupView,
)

app_name = "identity"

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/login/two-factor/", TwoFactorLoginView.as_view(), name="login-two-factor"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/two-factor/setup/", TwoFactorSetupView.as_view(), name="two-factor-setup"),
    path("auth/two-factor/confirm/", TwoFactorConfirmView.as_view(), name="two-factor-confirm"),
    path("auth/two-factor/disable/", TwoFactorDisableView.as_view(), name="two-factor-disable"),
    path("auth/recovery-codes/", RecoveryCodesView.as_view(), name="recovery-codes"),
    path("me/", MeView.as_view(), name="me"),
    path("me/context/", MeContextView.as_view(), name="me-context"),
]
