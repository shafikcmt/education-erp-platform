from django.apps import AppConfig


class BillingConfig(AppConfig):
    """`billing` module: SaaS plans, add-ons, prices, subscriptions (Phase 4)."""

    name = "apps.billing"
    label = "billing"
    verbose_name = "Billing"
