"""M21.2: перенести магазин CS-Cart в схему бизнеса (каталог, фото, старые адреса).

    python manage.py import_cscart --schema haanerteeladen --url https://haanerteeladen.de

По умолчанию только обход и отчёт (dry-run); ``--apply`` записывает. Повторный
прогон обновляет цены/фасовки и дописывает переадресации, не создавая дублей.
План — ``docs/m21-cscart-migration-plan-2026-10-31.md``.
"""

import re
import secrets
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
        # M21.3: главная, меню, логотип, цвет, контакты — как на старом сайте.
        parser.add_argument("--no-design", action="store_true", help="Без главной/меню/лого.")
        parser.add_argument("--hero-title", default="", help="Заголовок слайдов баннера.")
        parser.add_argument("--hero-button", default="", help="Подпись кнопки слайдов.")
        parser.add_argument("--hero-url", default="/sortiment/", help="Ссылка кнопки слайдов.")
        parser.add_argument(
            "--skip-banner",
            type=int,
            action="append",
            default=[],
            help="Номер баннера (с 1), который не переносить; можно повторять.",
        )
        parser.add_argument(
            "--banner-crop",
            default="",
            help="Полоса баннера без надписей, доли высоты «верх:низ», напр. 0.30:0.72.",
        )
        parser.add_argument(
            "--refresh-pages",
            action="store_true",
            help="Пересобрать страницы Versand/Zahlung/Über uns, если их не правили.",
        )
        parser.add_argument(
            "--replace-menu",
            action="store_true",
            help=(
                "Перезаписать верхнее меню меню старого магазина и порядок разделов "
                "каталога по нему (иначе — только если меню нет)."
            ),
        )
        parser.add_argument(
            "--locales",
            default="",
            help="Языки витрины через запятую, первый — основной (напр. de). С --create — de.",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help=(
                "Убрать то, чего нет в оригинале: демо-контент платформы и дубли "
                "второго импортёра («Website importieren»). Без --apply — только список."
            ),
        )
        parser.add_argument(
            "--codes",
            default="",
            help="CSV-выгрузка CS-Cart (колонка «Product code»): после импорта показать недостающие.",
        )
        # Создать магазин, если его ещё нет (вместо регистрации на сайте).
        parser.add_argument("--create", action="store_true", help="Создать бизнес-получатель.")
        parser.add_argument("--name", default="", help="Название бизнеса (для --create).")
        parser.add_argument("--owner-email", default="", help="E-Mail владельца (для --create).")
        parser.add_argument("--city", default="", help="Город (для --create).")
        parser.add_argument(
            "--business-type", default="online_shop", help="Тип бизнеса (для --create)."
        )

    def handle(self, *args, **opts):
        schema = opts["schema"]
        if schema == get_public_schema_name():
            raise CommandError("public schema is not a business")
        tenant = get_tenant_model().objects.filter(schema_name=schema).first()
        if tenant is None and not opts["create"]:
            raise CommandError(f"schema {schema!r} not found (use --create)")
        if tenant is None:
            self._check_create_args(opts, schema)
        try:
            vat = Decimal(str(opts["vat"]).replace(",", "."))
        except InvalidOperation as exc:
            raise CommandError("invalid --vat") from exc
        if vat not in (Decimal("0"), Decimal("7"), Decimal("19")):
            raise CommandError("--vat must be 0, 7 or 19")
        crop = None
        if opts["banner_crop"]:
            try:
                top, bottom = (float(x) for x in opts["banner_crop"].split(":"))
            except ValueError as exc:
                raise CommandError("--banner-crop must look like 0.30:0.72") from exc
            if not 0 <= top < bottom <= 1:
                raise CommandError("--banner-crop must satisfy 0 <= top < bottom <= 1")
            crop = (top, bottom)
        locales = [x.strip() for x in opts["locales"].split(",") if x.strip()]
        if not locales and tenant is None:
            locales = ["de"]
        if locales:
            from django.conf import settings

            known = {code for code, _ in settings.LANGUAGES}
            unknown = [x for x in locales if x not in known]
            if unknown:
                raise CommandError(f"unknown --locales: {', '.join(unknown)}")
        codes = set()
        if opts["codes"]:
            try:
                with open(opts["codes"], encoding="utf-8-sig") as fh:
                    codes = cscart.read_export_codes(fh.read())
            except OSError as exc:
                raise CommandError(f"cannot read --codes: {exc}") from exc
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
        if opts["cleanup"] and tenant is None:
            self.stdout.write("  cleanup: skipped (business does not exist yet)")
        elif opts["cleanup"]:
            with schema_context(schema):
                for note in cscart.cleanup_foreign(tenant, apply=opts["apply"]):
                    self.stdout.write(f"  cleanup: {note}")
        if not opts["apply"]:
            if tenant is None:
                self.stdout.write(f"would create business {opts['name']!r} ({schema})")
            self.stdout.write("dry-run: nothing written (use --apply)")
            return
        if tenant is None:
            tenant = self._create(opts, schema)

        with schema_context(schema):
            stats = cscart.apply_site(
                site,
                vat=vat.quantize(Decimal("0.01")),
                with_images=not opts["no_images"],
                log=self.stdout.write,
            )
            about = cscart.apply_about(tenant, site)
            design_notes = cscart.apply_legal(tenant, site)
            if not opts["no_design"]:
                design_notes += cscart.apply_design(
                    tenant,
                    site,
                    options=cscart.DesignOptions(
                        hero_title=opts["hero_title"],
                        hero_button_label=opts["hero_button"],
                        hero_button_url=opts["hero_url"],
                        skip_banners=tuple(opts["skip_banner"]),
                        banner_crop=crop,
                        replace_menu=opts["replace_menu"],
                        refresh_pages=opts["refresh_pages"],
                    ),
                    with_images=not opts["no_images"],
                )
        if locales:
            cscart.apply_locales(tenant, locales)
            design_notes.append(f"storefront languages: {', '.join(locales)}")
        self.stdout.write(
            self.style.SUCCESS(
                f"done: {stats.categories_created} categories, {stats.products_created} new / "
                f"{stats.products_updated} updated products, {stats.variants} variants, "
                f"{stats.images} images, {stats.redirects} redirects"
                + (", about text set" if about else "")
            )
        )
        for note in [*design_notes, *stats.notes]:
            self.stdout.write(f"  - {note}")
        if codes:
            with schema_context(schema):
                missing = cscart.missing_codes(codes)
            self.stdout.write(f"export codes: {len(codes)}, missing after import: {len(missing)}")
            for code in missing:
                self.stdout.write(f"  ? {code}")

    def _check_create_args(self, opts, schema):
        from django.core.validators import validate_email
        from django.forms import ValidationError

        from apps.tenants.models import Tenant

        if not opts["name"].strip() or not opts["city"].strip():
            raise CommandError("--create needs --name and --city")
        try:
            validate_email(opts["owner_email"])
        except ValidationError as exc:
            raise CommandError("--create needs a valid --owner-email") from exc
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,62}", schema):
            raise CommandError("--schema: lowercase letters, digits, underscore")
        if opts["business_type"] not in dict(Tenant.BUSINESS_TYPES):
            raise CommandError("unknown --business-type")

    def _create(self, opts, schema):
        """Бизнес + схема + домен + владелец (как регистрация, синхронно). Пароль
        случайный: владелец входит ссылкой на почту (/anmelden/link/) или
        «Passwort vergessen» и задаёт свой."""
        from apps.tenants import onboarding, services

        tenant, login_url = services.create_business(
            business_name=opts["name"].strip(),
            slug=schema.replace("_", "-"),
            business_type=opts["business_type"],
            city=opts["city"].strip(),
            email=opts["owner_email"].strip().lower(),
            password=secrets.token_urlsafe(24),
        )
        onboarding.mark_complete(tenant, source="import")  # сайт наполняет импорт — мастер не нужен
        self.stdout.write(self.style.SUCCESS(f"created business {tenant.name} → {login_url}"))
        self.stdout.write("  owner login: open the shop, /anmelden/link/ — link by e-mail")
        return tenant
