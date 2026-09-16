"""Query parameters every list endpoint understands.

Written once so that `?updated_since=` means the same thing on medicines as it does on invoices.
A sync client that has to learn each endpoint's dialect is a sync client that will get one of them
wrong.
"""

from typing import Any

from django.db.models import QuerySet
from django.utils.dateparse import parse_datetime
from rest_framework.filters import BaseFilterBackend
from rest_framework.request import Request
from rest_framework.views import APIView

from kernel.rbac.api.permissions import scoped_to_branches


class UpdatedSinceFilter(BaseFilterBackend):
    """`?updated_since=<ISO timestamp>` — what a delta sync asks for.

    Deliberately `>=` rather than `>`: a client that stores the newest timestamp it saw and sends
    it back will re-read a row or two, which is harmless, whereas `>` silently drops anything
    written in the same tick as the cursor.
    """

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet[Any],
        view: APIView,  # noqa: ARG002 — part of the filter-backend contract
    ) -> QuerySet[Any]:
        raw = request.query_params.get("updated_since")
        if not raw:
            return queryset
        moment = parse_datetime(raw)
        if moment is None:
            return queryset
        return queryset.filter(updated_at__gte=moment)

    def get_schema_operation_parameters(self, view: APIView) -> list[dict[str, Any]]:  # noqa: ARG002
        return [
            {
                "name": "updated_since",
                "required": False,
                "in": "query",
                "description": "Only rows changed at or after this ISO timestamp.",
                "schema": {"type": "string", "format": "date-time"},
            }
        ]


class BranchScopeFilter(BaseFilterBackend):
    """`?branch=<id>` — and, more importantly, the branches this user may see at all.

    The filter is applied whether or not the caller asked for it. A user whose role is scoped to
    one branch gets one branch's rows from every list, because leaving that to each view is how
    one view ends up forgetting.
    """

    #: A view sets this to the permission that governs its data.
    view_attribute = "branch_scope_permission"

    def filter_queryset(
        self, request: Request, queryset: QuerySet[Any], view: APIView
    ) -> QuerySet[Any]:
        field = getattr(view, "branch_field", "branch")
        permission = getattr(view, self.view_attribute, None)

        if permission:
            allowed = scoped_to_branches(request.user, permission)
            if allowed is not None:
                queryset = queryset.filter(**{f"{field}__in": allowed})

        asked = request.query_params.getlist("branch")
        if asked:
            queryset = queryset.filter(**{f"{field}__in": asked})
        return queryset

    def get_schema_operation_parameters(self, view: APIView) -> list[dict[str, Any]]:  # noqa: ARG002
        return [
            {
                "name": "branch",
                "required": False,
                "in": "query",
                "description": (
                    "Limit to these branches. Always narrowed by what the caller may see."
                ),
                "schema": {"type": "array", "items": {"type": "string", "format": "uuid"}},
            }
        ]


class DateRangeFilter(BaseFilterBackend):
    """`?date_from=` and `?date_to=`, against whatever date the view says it is about.

    Inclusive at both ends, because a person asking for Shrawan 1 to Shrawan 31 means to include
    both days, and an off-by-one here is a missing day in a VAT return.
    """

    def filter_queryset(
        self, request: Request, queryset: QuerySet[Any], view: APIView
    ) -> QuerySet[Any]:
        field = getattr(view, "date_field", None)
        if not field:
            return queryset
        start = request.query_params.get("date_from")
        end = request.query_params.get("date_to")
        if start:
            queryset = queryset.filter(**{f"{field}__gte": start})
        if end:
            queryset = queryset.filter(**{f"{field}__lte": end})
        return queryset

    def get_schema_operation_parameters(self, view: APIView) -> list[dict[str, Any]]:
        if not getattr(view, "date_field", None):
            return []
        return [
            {
                "name": name,
                "required": False,
                "in": "query",
                "description": description,
                "schema": {"type": "string", "format": "date"},
            }
            for name, description in (
                ("date_from", "Include from this date onwards (inclusive)."),
                ("date_to", "Include up to this date (inclusive)."),
            )
        ]
