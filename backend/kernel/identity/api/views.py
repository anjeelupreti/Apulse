from typing import cast

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import User
from .serializers import MeSerializer


class MeView(APIView):
    """The signed-in user. Grows into `/me/context` (tenant, permissions, features) in Phase 2."""

    @extend_schema(operation_id="me_retrieve", responses=MeSerializer, tags=["identity"])
    def get(self, request: Request) -> Response:
        # IsAuthenticated is the default permission, so this is always a real user.
        return Response(MeSerializer(cast("User", request.user)).data)
