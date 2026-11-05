"""Install the PostgreSQL extensions the platform relies on (docs/DATABASE_DESIGN.md §5).

`vector` is not a trusted extension, so the bootstrap script
(infra/docker/postgres/init/01-roles.sh) pre-installs all four as superuser in the
application database and in template1. ``CREATE EXTENSION IF NOT EXISTS`` here is then a
no-op that documents and verifies the requirement for every environment.
"""

from django.contrib.postgres.operations import (
    BtreeGistExtension,
    CITextExtension,
    CreateExtension,
    TrigramExtension,
)
from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies: list[tuple[str, str]] = []

    operations = [
        CreateExtension("vector"),
        TrigramExtension(),
        BtreeGistExtension(),
        CITextExtension(),
    ]
