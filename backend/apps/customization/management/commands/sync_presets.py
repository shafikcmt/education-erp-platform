from typing import Any

from django.core.management.base import BaseCommand

from apps.customization.sync import sync_presets


class Command(BaseCommand):
    help = "Sync institution-type presets from the repo files (idempotent; owner role only)."

    def handle(self, *args: Any, **options: Any) -> None:
        result = sync_presets()
        self.stdout.write(
            f"presets: {result.declared} declared, {result.created} created, "
            f"{result.deprecated} deprecated"
        )
