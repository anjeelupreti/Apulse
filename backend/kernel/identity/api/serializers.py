from typing import Any

from rest_framework import serializers

from kernel.tenancy.models import Branch, Tenant, TenantMembership

from ..models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "email", "phone", "full_name", "full_name_ne", "preferred_language")
        read_only_fields = fields


# Kept for the existing /me/ endpoint.
MeSerializer = UserSerializer


class TenantSummarySerializer(serializers.ModelSerializer[Tenant]):
    is_read_only = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tenant
        fields = ("id", "slug", "name", "name_ne", "status", "is_read_only", "default_language")
        read_only_fields = fields


class BranchSummarySerializer(serializers.ModelSerializer[Branch]):
    class Meta:
        model = Branch
        fields = ("id", "code", "name", "name_ne", "is_warehouse")
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer[TenantMembership]):
    tenant = TenantSummarySerializer(read_only=True)

    class Meta:
        model = TenantMembership
        fields = ("id", "tenant", "status")
        read_only_fields = fields


class MeContextSerializer(serializers.Serializer[Any]):
    """Everything the frontend needs to render the shell for the signed-in user."""

    user = UserSerializer(read_only=True)
    tenant = TenantSummarySerializer(read_only=True, allow_null=True)
    memberships = MembershipSerializer(many=True, read_only=True)
    branches = BranchSummarySerializer(many=True, read_only=True)
    permissions = serializers.ListField(child=serializers.CharField(), read_only=True)
    #: Features that are on for this account.
    features = serializers.ListField(child=serializers.CharField(), read_only=True)
    #: Ceilings, so the client can warn before the server refuses ("3 of 5 branches used").
    limits = serializers.DictField(read_only=True)
    server_time = serializers.DateTimeField(read_only=True)


class LoginSerializer(serializers.Serializer[Any]):
    identifier = serializers.CharField(
        max_length=254, help_text="Email address or phone number.", trim_whitespace=True
    )
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class LoginResponseSerializer(serializers.Serializer[Any]):
    requires_two_factor = serializers.BooleanField(read_only=True)
    challenge_token = serializers.CharField(read_only=True, allow_null=True)
    user = UserSerializer(read_only=True, allow_null=True)


class TwoFactorChallengeSerializer(serializers.Serializer[Any]):
    challenge_token = serializers.CharField()
    code = serializers.CharField(
        max_length=20, help_text="Authenticator code, or one recovery code."
    )


class TwoFactorSetupSerializer(serializers.Serializer[Any]):
    secret = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(
        read_only=True, help_text="Render as a QR code for the authenticator app."
    )


class TwoFactorConfirmSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=10)


class RecoveryCodesSerializer(serializers.Serializer[Any]):
    recovery_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


class PasswordConfirmSerializer(serializers.Serializer[Any]):
    """Re-authentication for actions that weaken account security."""

    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
