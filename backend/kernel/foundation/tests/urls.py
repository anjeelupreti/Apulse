"""Throwaway endpoints used only to exercise the error envelope."""

from django.http import Http404
from django.urls import path
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.errors import DomainError, codes


class _Line(serializers.Serializer):
    qty = serializers.IntegerField(min_value=1)


class _Payload(serializers.Serializer):
    name = serializers.CharField(max_length=5)
    lines = _Line(many=True)


class _OpenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class DomainErrorView(_OpenView):
    def get(self, request):
        raise DomainError(codes.VERSION_CONFLICT, details=[{"field": "version", "code": "stale"}])


class ValidationView(_OpenView):
    def post(self, request):
        serializer = _Payload(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class NotFoundView(_OpenView):
    def get(self, request):
        raise Http404


class CrashView(_OpenView):
    def get(self, request):
        raise RuntimeError("boom")


urlpatterns = [
    path("domain-error/", DomainErrorView.as_view()),
    path("validation/", ValidationView.as_view()),
    path("not-found/", NotFoundView.as_view()),
    path("crash/", CrashView.as_view()),
]
