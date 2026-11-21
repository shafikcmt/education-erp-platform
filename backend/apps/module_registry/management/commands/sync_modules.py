from typing import Any

from django.core.management.base import BaseCommand

from apps.module_registry.sync import sync_modules


class Command(BaseCommand):
    help = (
        "Sync the module catalogue from the app manifests and the planned catalogue "
        "(idempotent). Owner role only: run by the migrate bootstrap step."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        result = sync_modules()
        self.stdout.write(
            f"modules: {result.declared} declared, {result.created} created, "
            f"{result.updated} updated, {result.deprecated} deprecated"
        )
