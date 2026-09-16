"""Endpoints used only to exercise the DRF permission classes."""

from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from kernel.rbac.api.permissions import HasPermission, RequirePermission, RequireTenant


class ManageBranchesView(APIView):
    permission_classes = [RequireTenant, HasPermission]
    required_permissions = ("tenancy.branch.manage",)

    def get(self, request):
        return Response({"ok": True})


class InlinePermissionView(APIView):
    permission_classes = [RequirePermission("rbac.role.manage")]

    def get(self, request):
        return Response({"ok": True})


class TenantOnlyView(APIView):
    permission_classes = [RequireTenant]

    def get(self, request):
        return Response({"ok": True})


urlpatterns = [
    path("manage-branches/", ManageBranchesView.as_view()),
    path("inline/", InlinePermissionView.as_view()),
    path("tenant-only/", TenantOnlyView.as_view()),
]
