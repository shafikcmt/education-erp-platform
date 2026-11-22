"""Billing services (Phase 4 M2; ADR-051, ADR-054).

* **Catalogue (P17):** plans, plan modules, add-ons and prices; ``billing.plan.manage`` or
  ``billing.price.manage`` (step-up), checked uncached by ``platform_scope``. Prices are never
  edited: adding a price for the same plan or add-on, currency and interval deactivates the
  previous one. No price is ever created by code paths other than an explicit owner action.
* **Subscriptions (P18):** a tenant's plan, trial and add-ons; ``billing.subscription.manage``
  (step-up) and a reason of 10-200 characters. The change is written to the platform log and,
  in a targeted tenant transaction, to the tenant's log. Entitlements are recomputed from M3.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record
from apps.billing.models import AddOn, Plan, PlanModule, Price, Subscription, SubscriptionItem
from apps.core.tenancy import tenant_atomic
from apps.core.tenancy.platform import platform_scope
from apps.module_registry.models import Module
from apps.tenancy.models import Tenant
from apps.tenancy.rules import LIMIT_KEYS, TenantStatus

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

PLAN_MANAGE = "billing.plan.manage"
PRICE_MANAGE = "billing.price.manage"
SUBSCRIPTION_MANAGE = "billing.subscription.manage"
_REASON_MIN, _REASON_MAX = 10, 200


def _reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if not _REASON_MIN <= len(cleaned) <= _REASON_MAX:
        raise ValidationError({"reason": "Explain the reason in 10 to 200 characters."})
    return cleaned


def _limits(value: dict[str, Any]) -> dict[str, int]:
    limits: dict[str, int] = {}
    for key, raw in (value or {}).items():
        if key not in LIMIT_KEYS and key not in getattr(settings, "STUDIO_QUOTA_DEFAULTS", {}):
            raise ValidationError({"limits": f"Unknown limit {key!r}."})
        if not isinstance(raw, int) or isinstance(raw, bool) or not 1 <= raw <= 10_000:
            raise ValidationError({"limits": f"{key} must be a whole number from 1 to 10000."})
        limits[key] = raw
    return limits


def _trial_days(value: Any) -> int | None:
    """Trial length is data (ADR-054 Q2): empty, or 1 to 365 days."""
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 365:
        raise ValidationError({"trial_days": "Choose 1 to 365 days, or leave it empty."})
    return value


def _modules(codes: list[str]) -> list[Module]:
    found = {m.code: m for m in Module.objects.filter(code__in=codes, deprecated_at__isnull=True)}
    unknown = sorted(set(codes) - set(found))
    if unknown:
        raise ValidationError({"modules": f"Unknown modules: {', '.join(unknown)}."})
    platform = sorted(c for c, m in found.items() if m.category == Module.Category.PLATFORM)
    if platform:
        raise ValidationError(
            {"modules": f"Platform modules are always on: {', '.join(platform)}."}
        )
    return list(found.values())


# --------------------------------------------------------------------------- P17 catalogue
def create_plan(
    *,
    actor: User,
    code: str,
    name: str,
    limits: dict[str, Any] | None = None,
    modules: list[str] | None = None,
    is_public: bool = False,
    trial_days: int | None = None,
    request: HttpRequest | None = None,
) -> Plan:
    trial_days = _trial_days(trial_days)
    with platform_scope(
        operation="P17", actor=actor, reason=f"create plan {code}", permission=PLAN_MANAGE
    ):
        wanted = _modules(modules or [])
        try:
            with transaction.atomic():
                plan = Plan.objects.create(
                    code=code,
                    name=name,
                    limits=_limits(limits or {}),
                    is_public=is_public,
                    trial_days=trial_days,
                )
                PlanModule.objects.bulk_create([PlanModule(plan=plan, module=m) for m in wanted])
        except IntegrityError:
            raise ValidationError(
                {"code": "A plan with this code exists or the code is invalid."}
            ) from None
        record(
            "billing.plan.created",
            actor=actor,
            request=request,
            target_type="billing.plan",
            target_id=plan.pk,
            metadata={"plan_code": code},
        )
    return plan


def update_plan(
    *,
    actor: User,
    plan: Plan,
    changes: dict[str, Any],
    modules: list[str] | None = None,
    request: HttpRequest | None = None,
) -> Plan:
    with (
        platform_scope(
            operation="P17", actor=actor, reason=f"update plan {plan.code}", permission=PLAN_MANAGE
        ),
        transaction.atomic(),
    ):
        plan = Plan.objects.select_for_update().get(pk=plan.pk)
        fields = []
        for key, value in changes.items():
            if key not in {"name", "name_i18n", "is_public", "limits", "archived", "trial_days"}:
                raise ValidationError({key: "This field can't be changed."})
            if key == "limits":
                value = _limits(value)
            if key == "trial_days":
                value = _trial_days(value)
            if key == "archived":
                key, value = "archived_at", (timezone.now() if value else None)
            if getattr(plan, key) != value:
                setattr(plan, key, value)
                fields.append(key)
        if fields:
            plan.save(update_fields=[*fields, "updated_at"])
            record(
                "billing.plan.updated",
                actor=actor,
                request=request,
                target_type="billing.plan",
                target_id=plan.pk,
                metadata={"plan_code": plan.code, "fields": ",".join(sorted(fields))},
            )
        if modules is not None:
            wanted = {m.code: m for m in _modules(modules)}
            current: set[str] = {
                str(c) for c in plan.plan_modules.values_list("module__code", flat=True)
            }
            added, removed = sorted(set(wanted) - current), sorted(current - set(wanted))
            PlanModule.objects.filter(plan=plan, module__code__in=removed).delete()
            PlanModule.objects.bulk_create([PlanModule(plan=plan, module=wanted[c]) for c in added])
            if added or removed:
                record(
                    "billing.plan.modules_changed",
                    actor=actor,
                    request=request,
                    target_type="billing.plan",
                    target_id=plan.pk,
                    metadata={"plan_code": plan.code, "added": added, "removed": removed},
                )
    return plan


def create_addon(
    *, actor: User, code: str, name: str, module: str | None, request: HttpRequest | None = None
) -> AddOn:
    with platform_scope(
        operation="P17", actor=actor, reason=f"create add-on {code}", permission=PLAN_MANAGE
    ):
        target = None
        if module is not None:
            target = Module.objects.filter(code=module, deprecated_at__isnull=True).first()
            if target is None or not target.sellable:
                raise ValidationError({"module": "Only a sellable module can be an add-on."})
        try:
            with transaction.atomic():
                addon = AddOn.objects.create(code=code, name=name, module=target)
        except IntegrityError:
            raise ValidationError(
                {"code": "An add-on with this code exists or the code is invalid."}
            ) from None
        record(
            "billing.addon.created",
            actor=actor,
            request=request,
            target_type="billing.addon",
            target_id=addon.pk,
            metadata={"addon_code": code, "module_code": module or ""},
        )
    return addon


def add_price(
    *,
    actor: User,
    currency: str,
    interval: str,
    amount: str | Decimal,
    plan: Plan | None = None,
    addon: AddOn | None = None,
    request: HttpRequest | None = None,
) -> Price:
    """A new active price (the owner's data); the previous active one for the same target,
    currency and interval is deactivated, never edited."""
    if (plan is None) == (addon is None):
        raise ValidationError({"target": "Give exactly one of plan or add-on."})
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValidationError({"amount": "Enter a decimal amount."}) from None
    if value < 0:
        raise ValidationError({"amount": "Must not be negative."})
    target = f"plan:{plan.code}" if plan else f"addon:{addon.code}"  # type: ignore[union-attr]
    with platform_scope(
        operation="P17", actor=actor, reason=f"price {target}", permission=PRICE_MANAGE
    ):
        try:
            with transaction.atomic():
                Price.objects.filter(
                    plan=plan, addon=addon, currency=currency, interval=interval, active=True
                ).update(active=False, updated_at=timezone.now())
                price = Price.objects.create(
                    plan=plan, addon=addon, currency=currency, interval=interval, amount=value
                )
        except IntegrityError:
            raise ValidationError({"price": "Invalid currency or interval."}) from None
        record(
            "billing.price.added",
            actor=actor,
            request=request,
            target_type="billing.price",
            target_id=price.pk,
            metadata={
                "target": target,
                "currency": currency,
                "interval": interval,
                "amount": str(value),
            },
        )
    return price


def deactivate_price(*, actor: User, price: Price, request: HttpRequest | None = None) -> Price:
    target = f"plan:{price.plan.code}" if price.plan else f"addon:{price.addon.code}"  # type: ignore[union-attr]
    with platform_scope(
        operation="P17", actor=actor, reason=f"price {target}", permission=PRICE_MANAGE
    ):
        if price.active:
            Price.objects.filter(pk=price.pk).update(active=False, updated_at=timezone.now())
            price.active = False
            record(
                "billing.price.deactivated",
                actor=actor,
                request=request,
                target_type="billing.price",
                target_id=price.pk,
                metadata={"target": target, "currency": price.currency, "interval": price.interval},
            )
    return price


# --------------------------------------------------------------------------- P18 subscriptions
def _tenant(tenant_id: uuid.UUID) -> Tenant:
    tenant = Tenant.objects.filter(pk=tenant_id).exclude(status=TenantStatus.DELETED).first()
    if tenant is None:
        raise ValidationError({"tenant": "Unknown tenant."})
    return tenant


def _both_logs(
    action: str,
    tenant: Tenant,
    *,
    actor: User,
    request: HttpRequest | None,
    metadata: dict[str, Any],
) -> None:
    data = {**metadata, "tenant_id": str(tenant.pk)}
    record(
        action,
        actor=actor,
        request=request,
        target_type="tenant",
        target_id=tenant.pk,
        metadata=data,
    )
    with tenant_atomic(tenant.as_context()):
        record(
            action,
            actor=actor,
            request=request,
            target_type="tenant",
            target_id=tenant.pk,
            metadata=data,
        )
        after_subscription_change(tenant.pk)


def after_subscription_change(tenant_id: uuid.UUID) -> None:
    """Inside the tenant transaction of every P18 change: recompute the entitlement snapshot
    (ADR-052)."""
    from apps.module_registry.entitlements import recompute

    recompute(tenant_id)


def assign_plan(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    plan_code: str,
    reason: str,
    request: HttpRequest | None = None,
) -> Subscription:
    cleaned = _reason(reason)
    with platform_scope(
        operation="P18", actor=actor, reason=cleaned, permission=SUBSCRIPTION_MANAGE
    ):
        tenant = _tenant(tenant_id)
        plan = Plan.objects.filter(code=plan_code, archived_at__isnull=True).first()
        if plan is None:
            raise ValidationError({"plan": "Unknown plan."})
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().filter(tenant=tenant).first()
            old = sub.plan.code if sub else ""
            if sub is None:
                sub = Subscription.objects.create(
                    tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE
                )
            else:
                sub.plan = plan
                if sub.status in {Subscription.Status.TRIALING, Subscription.Status.EXPIRED}:
                    sub.status = Subscription.Status.ACTIVE
                    sub.trial_ends_at = None
                sub.save(update_fields=["plan", "status", "trial_ends_at", "updated_at"])
        _both_logs(
            "billing.subscription.plan_changed",
            tenant,
            actor=actor,
            request=request,
            metadata={"old": old, "new": plan.code, "reason": cleaned},
        )
    return sub


def start_trial(
    *,
    actor: User | None,
    tenant_id: uuid.UUID,
    plan_code: str,
    days: int,
    reason: str,
    request: HttpRequest | None = None,
    scope_open: bool = False,
) -> Subscription:
    """Put a tenant on ``plan_code`` in ``trialing`` for ``days``. ``scope_open``: called
    inside an already open P4 provisioning scope (no nested scope)."""
    cleaned = _reason(reason)
    if not isinstance(days, int) or not 1 <= days <= 365:
        raise ValidationError({"days": "Choose 1 to 365 days."})

    def run() -> Subscription:
        tenant = _tenant(tenant_id)
        plan = Plan.objects.filter(code=plan_code, archived_at__isnull=True).first()
        if plan is None:
            raise ValidationError({"plan": "Unknown plan."})
        ends = timezone.now() + timedelta(days=days)
        with transaction.atomic():
            sub, _ = Subscription.objects.select_for_update().get_or_create(
                tenant=tenant, defaults={"plan": plan}
            )
            sub.plan, sub.status, sub.trial_ends_at = plan, Subscription.Status.TRIALING, ends
            sub.save(update_fields=["plan", "status", "trial_ends_at", "updated_at"])
        assert actor is not None  # noqa: S101 - every caller passes a user
        _both_logs(
            "billing.subscription.trial_set",
            tenant,
            actor=actor,
            request=request,
            metadata={"days": days, "reason": cleaned},
        )
        return sub

    if scope_open:
        return run()
    with platform_scope(
        operation="P18", actor=actor, reason=cleaned, permission=SUBSCRIPTION_MANAGE
    ):
        return run()


def add_addon(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    addon_code: str,
    reason: str,
    valid_until: Any = None,
    request: HttpRequest | None = None,
) -> SubscriptionItem:
    cleaned = _reason(reason)
    with platform_scope(
        operation="P18", actor=actor, reason=cleaned, permission=SUBSCRIPTION_MANAGE
    ):
        tenant = _tenant(tenant_id)
        addon = AddOn.objects.filter(code=addon_code, archived_at__isnull=True).first()
        if addon is None:
            raise ValidationError({"addon": "Unknown add-on."})
        sub = Subscription.objects.filter(tenant=tenant).first()
        if sub is None:
            raise ValidationError({"tenant": "The tenant has no subscription yet."})
        try:
            with transaction.atomic():
                item = SubscriptionItem.objects.create(
                    tenant=tenant,
                    subscription=sub,
                    addon=addon,
                    valid_from=timezone.now(),
                    valid_until=valid_until,
                )
        except IntegrityError:
            raise ValidationError({"addon": "This add-on is already active."}) from None
        _both_logs(
            "billing.subscription.addon_added",
            tenant,
            actor=actor,
            request=request,
            metadata={"addon_code": addon_code, "reason": cleaned},
        )
    return item


def remove_addon(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    addon_code: str,
    reason: str,
    request: HttpRequest | None = None,
) -> int:
    cleaned = _reason(reason)
    with platform_scope(
        operation="P18", actor=actor, reason=cleaned, permission=SUBSCRIPTION_MANAGE
    ):
        tenant = _tenant(tenant_id)
        ended = SubscriptionItem.objects.filter(
            tenant=tenant, addon__code=addon_code, ended_at__isnull=True
        ).update(ended_at=timezone.now(), updated_at=timezone.now())
        if ended:
            _both_logs(
                "billing.subscription.addon_removed",
                tenant,
                actor=actor,
                request=request,
                metadata={"addon_code": addon_code, "reason": cleaned},
            )
    return ended
