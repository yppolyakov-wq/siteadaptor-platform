"""CM-4: идемпотентный засев реестра MediaAsset из существующих FileRef-копий.

По всем схемам тенантов (или --schema). Повторный запуск безопасен (unique path).
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.core import media_registry
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "CM-4: заполнить реестр MediaAsset из существующих FileRef-медиа"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="одна схема (иначе все тенанты)")

    def handle(self, *args, **options):
        schemas = (
            [options["schema"]]
            if options["schema"]
            else list(
                Tenant.objects.exclude(schema_name="public").values_list("schema_name", flat=True)
            )
        )
        total = 0
        for schema in schemas:
            tenant = Tenant.objects.filter(schema_name=schema).first()
            with schema_context(schema):
                created = media_registry.backfill(tenant)
            total += created
            self.stdout.write(f"{schema}: +{created}")
        self.stdout.write(self.style.SUCCESS(f"Готово: {total} записей"))
