"""M21.2: перенести магазин CS-Cart в схему бизнеса (каталог, фото, старые адреса).

    python manage.py import_cscart --schema haanerteeladen --url https://haanerteeladen.de

По умолчанию только обход и отчёт (dry-run); ``--apply`` записывает. Повторный
прогон обновляет цены/фасовки и дописывает переадресации, не создавая дублей.
План — ``docs/m21-cscart-migration-plan-2026-10-31.md``.
"""

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from apps.imports import cscart


class Command(BaseCommand):
    help = "Перенос магазина CS-Cart: категории, товары с фасовками, фото, 301 со старых адресов."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Схема бизнеса-получателя.")
        parser.add_argument("--url", required=True, help="Адрес старого магазина.")
        parser.add_argument("--apply", action="store_true", help="Записать (иначе отчёт).")
        parser.add_argument("--no-images", action="store_true", help="Без загрузки фото.")
        parser.add_argument("--vat", default="7", help="Ставка НДС товаров (чай — 7).")

    def handle(self, *args, **opts):
        schema = opts["schema"]
        if schema == get_public_schema_name():
            raise CommandError("public schema is not a business")
        tenant = get_tenant_model().objects.filter(schema_name=schema).first()
        if tenant is None:
            raise CommandError(f"schema {schema!r} not found")
        try:
            vat = Decimal(str(opts["vat"]).replace(",", "."))
        except InvalidOperation as exc:
            raise CommandError("invalid --vat") from exc
        if vat not in (Decimal("0"), Decimal("7"), Decimal("19")):
            raise CommandError("--vat must be 0, 7 or 19")
        url = opts["url"].strip()
        if not url.startswith(("https://", "http://")):
            raise CommandError("--url must start with http(s)://")

        site = cscart.scrape(url, log=self.stdout.write)
        variants = sum(len(p.variants) for p in site.products)
        self.stdout.write(
            f"found: {len(site.categories)} categories, {len(site.products)} products, "
            f"{variants} variants, {len(site.errors)} errors"
        )
        for err in site.errors[:30]:
            self.stdout.write(f"  ! {err}")
        if not opts["apply"]:
            self.stdout.write("dry-run: nothing written (use --apply)")
            return

        with schema_context(schema):
            stats = cscart.apply_site(
                site,
                vat=vat.quantize(Decimal("0.01")),
                with_images=not opts["no_images"],
                log=self.stdout.write,
            )
            about = cscart.apply_about(tenant, site)
        self.stdout.write(
            self.style.SUCCESS(
                f"done: {stats.categories_created} categories, {stats.products_created} new / "
                f"{stats.products_updated} updated products, {stats.variants} variants, "
                f"{stats.images} images, {stats.redirects} redirects"
                + (", about text set" if about else "")
            )
        )
        for note in stats.notes:
            self.stdout.write(f"  - {note}")
