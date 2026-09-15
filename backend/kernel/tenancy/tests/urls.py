"""Endpoints used only to exercise tenant resolution and the read-only guard."""

from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from kernel.tenancy.context import get_current_tenant_id


class WhoAmIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = getattr(request, "tenant", None)
        context_id = get_current_tenant_id()
        return Response(
            {
                "tenant_slug": tenant.slug if tenant else None,
                "context_tenant_id": str(context_id) if context_id else None,
            }
        )

    def post(self, request):
        return Response({"written": True})


urlpatterns = [path("whoami/", WhoAmIView.as_view())]
