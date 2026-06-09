"""Бэкофилл/реконсиляция агрегатора по всем арендаторам.

Запускать после деплоя Sprint 4, чтобы /entdecken сразу наполнился (хук
материализует листинги только по будущим переходам акций):

    python manage.py sync_aggregator
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import get_tenant_model

from apps.aggregator.tasks import reconcile_schema


class Command(BaseCommand):
    help = "Пересинхронизировать активные акции всех арендаторов в агрегатор."

    def handle(self, *args, **options):
        total = 0
        for tenant in get_tenant_model().objects.exclude(schema_name="public"):
            count = reconcile_schema(tenant.schema_name)
            total += count
            self.stdout.write(f"{tenant.schema_name}: {count} active")
        self.stdout.write(self.style.SUCCESS(f"Aggregator synced: {total} listings"))
