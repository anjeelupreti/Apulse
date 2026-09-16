from typing import Any, cast

from django.contrib.auth import logout as django_logout
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from kernel.rbac import resolver
from kernel.tenancy.models import Branch, Tenant, TenantMembership
from shared.errors import DomainError, codes

from .. import services
from ..models import TwoFactorDevice, User
from .serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    MeContextSerializer,
    MeSerializer,
    PasswordConfirmSerializer,
    RecoveryCodesSerializer,
    TwoFactorChallengeSerializer,
    TwoFactorConfirmSerializer,
    TwoFactorSetupSerializer,
)


def _validated(serializer_class: type, request: Request) -> dict[str, Any]:
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def _current_user(request: Request) -> User:
    return cast("User", request.user)


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the CSRF cookie so a browser client can perform its first unsafe request."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="auth_csrf", responses={200: None}, tags=["auth"])
    def get(self, request: Request) -> Response:  # noqa: ARG002 (DRF handler signature)
        return Response({"detail": "ok"})


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        operation_id="auth_login",
        request=LoginSerializer,
        responses=LoginResponseSerializer,
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        data = _validated(LoginSerializer, request)
        result = services.authenticate_credentials(
            request._request, identifier=data["identifier"], password=data["password"]
        )
        return Response(
            {
                "requires_two_factor": result.requires_two_factor,
                "challenge_token": result.challenge_token,
                "user": None if result.requires_two_factor else MeSerializer(result.user).data,
            }
        )


class TwoFactorLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        operation_id="auth_login_two_factor",
        request=TwoFactorChallengeSerializer,
        responses=LoginResponseSerializer,
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        data = _validated(TwoFactorChallengeSerializer, request)
        result = services.complete_two_factor(
            request._request, challenge_token=data["challenge_token"], code=data["code"]
        )
        return Response(
            {
                "requires_two_factor": False,
                "challenge_token": None,
                "user": MeSerializer(result.user).data,
            }
        )


class LogoutView(APIView):
    @extend_schema(operation_id="auth_logout", request=None, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        django_logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """The signed-in user."""

    @extend_schema(operation_id="me_retrieve", responses=MeSerializer, tags=["identity"])
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(_current_user(request)).data)


class MeContextView(APIView):
    """User, current tenant, memberships and accessible branches, in one call."""

    @extend_schema(operation_id="me_context", responses=MeContextSerializer, tags=["identity"])
    def get(self, request: Request) -> Response:
        user = _current_user(request)
        tenant = getattr(request, "tenant", None)
        # Branch.objects is scoped to the active tenant by the tenant context.
        branches = Branch.objects.filter(is_active=True) if isinstance(tenant, Tenant) else []
        memberships = TenantMembership.objects.filter(
            user=user, status=TenantMembership.Status.ACTIVE
        ).select_related("tenant")
        payload = {
            "user": user,
            "tenant": tenant if isinstance(tenant, Tenant) else None,
            "memberships": memberships,
            "branches": branches,
            "permissions": sorted(resolver.permissions_for(user)),
            # Filled in by the entitlement resolver (M2.5).
            "features": [],
            "server_time": timezone.now(),
        }
        return Response(MeContextSerializer(payload).data)


class TwoFactorSetupView(APIView):
    @extend_schema(
        operation_id="auth_two_factor_setup",
        request=None,
        responses=TwoFactorSetupSerializer,
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        device, uri = services.start_two_factor_setup(_current_user(request))
        return Response({"secret": device.secret, "provisioning_uri": uri})


class TwoFactorConfirmView(APIView):
    @extend_schema(
        operation_id="auth_two_factor_confirm",
        request=TwoFactorConfirmSerializer,
        responses=RecoveryCodesSerializer,
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        data = _validated(TwoFactorConfirmSerializer, request)
        codes_issued = services.confirm_two_factor(_current_user(request), code=data["code"])
        return Response({"recovery_codes": codes_issued})


class TwoFactorDisableView(APIView):
    """Turning off a second factor weakens the account, so the password is required again."""

    @extend_schema(
        operation_id="auth_two_factor_disable",
        request=PasswordConfirmSerializer,
        responses={204: None},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        user = _current_user(request)
        _require_password(user, _validated(PasswordConfirmSerializer, request)["password"])
        services.disable_two_factor(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecoveryCodesView(APIView):
    @extend_schema(
        operation_id="auth_recovery_codes_regenerate",
        request=PasswordConfirmSerializer,
        responses=RecoveryCodesSerializer,
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        user = _current_user(request)
        _require_password(user, _validated(PasswordConfirmSerializer, request)["password"])
        if not TwoFactorDevice.objects.filter(user=user, confirmed_at__isnull=False).exists():
            from .. import errors

            raise DomainError(errors.AUTH_TWO_FACTOR_NOT_SET_UP)
        return Response({"recovery_codes": services.regenerate_recovery_codes(user)})


def _require_password(user: User, password: str) -> None:
    if not user.check_password(password):
        raise DomainError(codes.AUTH_FAILED)
