"""T-8.23d / S3: свободные акции лёгких магазинов → товар + акция.

Решение владельца 2026-10-11: акция всегда от товара. Магазины, созданные через
«Aktion in 3 Klicks» до T-8.23d, получили акции без товара. Команда по каждому
магазину «Nur Aktionen» создаёт товар из данных акции (название, описание, цена
«statt», иначе акционная; фото переходят в товар) и привязывает акцию. Заодно
включает модуль акций, если пресет вертикали его выключил (T-8.23a, отель).

Без ``--apply`` — только отчёт. Идемпотентно: акция с товаром не трогается; акция
без цены («−20 % auf alles») остаётся свободной.

    python manage.py convert_lite_promotions            # что будет сделано
    python manage.py convert_lite_promotions --apply    # сделать
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import tenant_context

from apps.core import storefront_profile
from apps.tenants.models import Tenant
from apps.tenants.services import QUICK_REQUIRED_MODULES


def convert_promotion(promo) -> bool:
    """Товар из свободной акции. True — сконвертирована."""
    from apps.catalog.models import Product

    if promo.target is not None:
        return False
    regular = promo.compare_at_price if promo.compare_at_price is not None else None
    if regular is None:
        regular = promo.price_override
    if regular is None:
        return False
    with transaction.atomic():
        promo.product = Product.objects.create(
            name=dict(promo.title or {}),
            description=dict(promo.description or {}),
            base_price=regular,
            images=list(promo.images or []),
        )
        promo.images = []
        promo.save(update_fields=["product", "images", "updated_at"])
    return True


class Command(BaseCommand):
    help = "Свободные акции магазинов «Nur Aktionen» → товар + акция (T-8.23d)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Изменить данные.")

    def handle(self, *args, apply=False, **options):
        total = 0
        for tenant in Tenant.objects.exclude(schema_name="public").order_by("slug"):
            if not storefront_profile.is_aktionen(tenant):
                continue
            off = [m for m in (tenant.disabled_modules or []) if m in QUICK_REQUIRED_MODULES]
            with tenant_context(tenant):
                from apps.promotions.models import Promotion

                free = [
                    p
                    for p in Promotion.objects.filter(
                        product__isnull=True,
                        service__isnull=True,
                        stay_unit__isnull=True,
                        combo__isnull=True,
                    )
                    if p.compare_at_price is not None or p.price_override is not None
                ]
                if not free and not off:
                    continue
                self.stdout.write(
                    f"{tenant.slug}: акций → товар: {len(free)}"
                    + (f"; включить модули: {', '.join(off)}" if off else "")
                )
                if not apply:
                    total += len(free)
                    continue
                total += sum(convert_promotion(p) for p in free)
            if apply and off:
                tenant.disabled_modules = [
                    m for m in tenant.disabled_modules if m not in QUICK_REQUIRED_MODULES
                ]
                tenant.save(update_fields=["disabled_modules"])
        verb = "переведено" if apply else "будет переведено (пробный прогон, --apply — выполнить)"
        self.stdout.write(self.style.SUCCESS(f"Акций {verb}: {total}."))
