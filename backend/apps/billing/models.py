"""SaaS billing data (Phase 4 M2; ADR-051, ADR-054; `SUBSCRIPTION_AND_BILLING.md`).

* ``Plan``, ``PlanModule``, ``AddOn`` and ``Price`` are **platform registry** tables (no tenant
  data; registry allow-list). They are written only inside catalogued platform operations
  (P17) by holders of the billing permissions.
* ``Subscription`` (one per tenant) and ``SubscriptionItem`` are per-tenant registry rows with
  **self-scoped, tenant-read-only RLS**: a tenant context sees only its own rows and can never
  write; the platform (no context) writes through P18.
* **No prices are seeded.** Amounts are owner data, entered through the platform (ADR-024 is
  still Proposed); money is ``NUMERIC(18,2)`` plus an ISO-4217 currency. A price row is never
  edited: it is deactivated and replaced, so history stays intact.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class Plan(BaseModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=False)
    # max_institutions / max_campuses (ADR-010) and later limits; the tenant override wins.
    limits = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_plan"
        ordering = ("code",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[a-z][a-z0-9_]{1,39}$"),
                name="billing_plan_code_valid",
            )
        ]

    def __str__(self) -> str:
        return self.code


class PlanModule(BaseModel):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="plan_modules")
    module = models.ForeignKey(
        "module_registry.Module", on_delete=models.PROTECT, to_field="code", related_name="+"
    )

    class Meta:
        db_table = "billing_planmodule"
        constraints = [
            models.UniqueConstraint(fields=["plan", "module"], name="billing_planmodule_unique")
        ]


class AddOn(BaseModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    # A module add-on enables one sellable module; usage packs (SMS, storage) come later.
    module = models.ForeignKey(
        "module_registry.Module",
        on_delete=models.PROTECT,
        to_field="code",
        related_name="+",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_addon"
        ordering = ("code",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[a-z][a-z0-9_]{1,39}$"),
                name="billing_addon_code_valid",
            )
        ]

    def __str__(self) -> str:
        return self.code


class Price(BaseModel):
    class Interval(models.TextChoices):
        MONTH = "month", "Monthly"
        YEAR = "year", "Yearly"
        ONE_TIME = "one_time", "One time"

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True)
    addon = models.ForeignKey(AddOn, on_delete=models.PROTECT, null=True, blank=True)
    currency = models.CharField(max_length=3)
    interval = models.CharField(max_length=16, choices=Interval.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "billing_price"
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(plan__isnull=False, addon__isnull=True))
                | (models.Q(plan__isnull=True, addon__isnull=False)),
                name="billing_price_one_target",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"), name="billing_price_currency"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="billing_price_amount_non_negative"
            ),
            models.UniqueConstraint(
                fields=["plan", "addon", "currency", "interval"],
                condition=models.Q(active=True),
                nulls_distinct=False,
                name="billing_price_one_active",
            ),
        ]


class Subscription(BaseModel):
    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        SUSPENDED = "suspended", "Suspended"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    tenant = models.OneToOneField(
        "tenancy.Tenant", on_delete=models.PROTECT, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIALING)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_subscription"

    def __str__(self) -> str:
        return f"subscription {self.pk}"


class SubscriptionItem(BaseModel):
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT, related_name="+")
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="items")
    addon = models.ForeignKey(AddOn, on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField(default=1)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_subscriptionitem"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "addon"],
                condition=models.Q(ended_at__isnull=True),
                name="billing_item_one_open",
            )
        ]
