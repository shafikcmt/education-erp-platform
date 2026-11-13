"""Host classes of a view (Phase 3 plan §12): which kind of host may serve it.

Fail closed: a view without a ``host_classes`` attribute is **platform-only**, so it returns
the uniform 404 on tenant hosts. Tenant-capable views opt in explicitly.
"""

from typing import Final

PLATFORM: Final = "platform"
TENANT: Final = "tenant"

PLATFORM_ONLY: Final[frozenset[str]] = frozenset({PLATFORM})
TENANT_ONLY: Final[frozenset[str]] = frozenset({TENANT})
PLATFORM_AND_TENANT: Final[frozenset[str]] = frozenset({PLATFORM, TENANT})


def view_class(view_func: object) -> object:
    """The class behind a DRF/Django class-based view callable (or the callable itself)."""
    return getattr(view_func, "cls", None) or getattr(view_func, "view_class", None) or view_func


def host_classes_of(view_func: object) -> frozenset[str]:
    declared = getattr(view_class(view_func), "host_classes", PLATFORM_ONLY)
    return frozenset(declared)
