"""Write the code's module manifests into the database.

Run on every deploy, before traffic is sent to the new release, so the control plane can attach
newly declared modules and features to plans.
"""

from typing import Any

from django.core.management.base import BaseCommand

from kernel.entitlements.services import sync_modules


class Command(BaseCommand):
    help = "Sync module and feature manifests into the database (idempotent)."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002 (Django signature)
        result = sync_modules()
        self.stdout.write(f"modules: {result['modules']}, features: {result['features']}")
        if result["orphans"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{result['orphans']} feature(s) are no longer declared in code. "
                    "They are kept so existing grants survive; remove them deliberately."
                )
            )
