"""Standard pagination classes (docs/API_STANDARDS.md §5)."""

from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardPageNumberPagination(PageNumberPagination):
    """Page-number pagination for admin tables that need page jumps."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class StandardCursorPagination(CursorPagination):
    """Cursor pagination for large or append-heavy lists (attendance, audit, payments)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"
