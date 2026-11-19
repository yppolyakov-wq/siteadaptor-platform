"""FB-33 M2f-0: аудит LMIV — у скольких сайтов еды скрыт раздел «Состав / аллергены».

Решение владельца (K3): у еды (`archetypes.FOOD_BUSINESS_TYPES`, включая продуктовые магазины)
раздел `info` страницы товара скрыть нельзя — LMIV требует эти сведения до покупки. M2f-4
перестанет применять скрытие; эта команда только ЧИТАЕТ и говорит, где страница изменится.

    python manage.py lmiv_info_audit [--schema <сайт>]

Итог — строкой `lmiv hidden: <сайтов> sites, <товаров> products`.
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from apps.core.archetypes import FOOD_BUSINESS_TYPES
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


def site_hides_info(config) -> bool:
    """СОХРАНЁННОЕ скрытие (без замка LMIV — аудит ищет именно то, что замок отменит)."""
    from apps.tenants import siteconfig

    key = siteconfig.detail_section_config_key("catalog")
    raw = siteconfig.normalize_detail_sections((config or {}).get(key), "catalog")
    return "info" in raw.get("hidden", [])


def products_hiding_info(config) -> int:
    """Товары, у которых своя структура скрывает `info` (сохранённое, без замка LMIV)."""
    from apps.catalog.models import Product
    from apps.core import object_structure

    count = 0
    for product in Product.objects.exclude(page_override={}).only("pk", "page_override"):
        own = object_structure.clean(object_structure._state(config or {}, product), "catalog")
        if "info" in own.get("hidden", []):
            count += 1
    return count


class Command(BaseCommand):
    help = "FB-33 M2f-0: где у еды скрыт раздел «Zutaten / Allergene» (только чтение)"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="один сайт (иначе все сайты еды)")

    def handle(self, *args, **options):
        tenants = Tenant.objects.exclude(schema_name="public").filter(
            business_type__in=FOOD_BUSINESS_TYPES
        )
        if options["schema"]:
            tenants = tenants.filter(schema_name=options["schema"])
            if not tenants.exists():
                raise CommandError(f"нет такого сайта еды: {options['schema']}")
        sites = products = 0
        failed = []
        for tenant in tenants.order_by("schema_name").only("schema_name", "site_config"):
            try:
                site = site_hides_info(tenant.site_config)
                own = 0
                if not site:  # весь сайт скрыл — товары сверх него не считаем (без двойного счёта)
                    with schema_context(tenant.schema_name):
                        own = products_hiding_info(tenant.site_config)
            except Exception as exc:  # noqa: BLE001 — один сайт не останавливает аудит
                logger.exception("lmiv_info_audit: %s", tenant.schema_name)
                failed.append(tenant.schema_name)
                self.stderr.write(f"{tenant.schema_name}: ОШИБКА {type(exc).__name__}: {exc}")
                continue
            if site or own:
                sites += 1
                products += own
                where = "весь сайт" if site else ""
                if own:
                    where = f"{where}{', ' if where else ''}{own} товаров"
                self.stdout.write(f"{tenant.schema_name}: скрыт «Zutaten/Allergene» — {where}")
        self.stdout.write(f"lmiv hidden: {sites} sites, {products} products")
        if failed:
            raise CommandError(f"не проверены сайты: {', '.join(failed)}")
