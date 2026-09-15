"""Pagination styles (docs/CONVENTIONS.md §4.2)."""

from rest_framework.pagination import CursorPagination, PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """UI lists: `?page=` & `?page_size=` (max 500)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 500


class SyncCursorPagination(CursorPagination):
    """Offline sync and large exports: stable cursor over time-ordered UUIDv7 ids."""

    page_size = 500
    page_size_query_param = "limit"
    max_page_size = 1000
    ordering = "id"
