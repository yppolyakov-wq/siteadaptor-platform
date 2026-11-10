"""M21.7: цены и фасовки по артикулам из CSV (прайс-лист владельца).

    python manage.py update_prices --schema haanerteeladen --file /tmp/preise.csv
    python manage.py update_prices --schema haanerteeladen --file /tmp/preise.csv --apply

CSV через «;», строка = артикул;фасовка;цена;действие:
- ``HT515;100 g;9,30``          — цена фасовки (действие пусто);
- ``HT90644;50 g;4,99;nur``     — только эта фасовка: товар продаётся одной фасовкой по
                                   этой цене, остальные фасовки сняты с продажи (не стёрты —
                                   история заказов цела), скрытый товар снова виден;
- ``HT428;;;loeschen``          — товар удалить (мягко, как кнопка «Löschen»).

Артикул ищется у товара и у фасовок (``HT515`` = товар, ``HT515.1`` — его фасовка 250 г),
без учёта регистра. Без ``--apply`` — только таблица «было → станет». Ошибка в строке
не останавливает остальные; запись — одной транзакцией.
"""

import csv
import io
import re
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import get_tenant_model, schema_context

from apps.core.money import parse_amount

_SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l|stk|st)?\s*$", re.I)
ACTIONS = ("", "nur", "loeschen")


def parse_size(raw: str):
    """«100 g» / «100g» / «1 kg» → граммы (Decimal) или None."""
    m = _SIZE_RE.match(raw or "")
    if not m:
        return None
    amount = Decimal(m.group(1).replace(",", "."))
    unit = (m.group(2) or "g").lower()
    return amount * 1000 if unit in ("kg", "l") else amount


def _variant_grams(variant):
    if variant.content_amount:
        return Decimal(variant.content_amount)
    return parse_size(variant.size or variant.label)


def _find_product(code: str):
    from apps.catalog.models import Product, ProductVariant

    product = Product.objects.filter(sku__iexact=code).first()
    if product is not None:
        return product
    variant = (
        ProductVariant.objects.filter(sku__iexact=code).select_related("product").first()
        or ProductVariant.objects.filter(sku__istartswith=code + ".")
        .select_related("product")
        .first()
    )
    return variant.product if variant is not None else None


def _money(value) -> str:
    return "—" if value is None else f"{Decimal(value):.2f}".replace(".", ",")


class Command(BaseCommand):
    help = "Цены и фасовки по артикулам из CSV (артикул;фасовка;цена;действие)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True)
        parser.add_argument("--file", required=True, help="CSV через «;» (UTF-8)")
        parser.add_argument("--apply", action="store_true", help="Записать (иначе показ).")

    def handle(self, *args, **opts):
        try:
            with open(opts["file"], encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError as exc:
            raise CommandError(f"file: {exc}") from exc
        tenant = get_tenant_model().objects.filter(schema_name=opts["schema"]).first()
        if tenant is None:
            raise CommandError(f"business {opts['schema']!r} not found")
        rows = [
            r for r in csv.reader(io.StringIO(text), delimiter=";") if any(c.strip() for c in r)
        ]
        with schema_context(tenant.schema_name):
            with transaction.atomic():
                errors = self._run(rows)
                if not opts["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"rows: {len(rows)}, errors: {errors}")
        self.stdout.write("saved" if opts["apply"] else "dry-run: nothing written (use --apply)")

    def _run(self, rows) -> int:
        errors = 0
        for n, row in enumerate(rows, 1):
            code, size, price, action = (list(row) + ["", "", "", ""])[:4]
            code, action = code.strip(), action.strip().lower()
            if n == 1 and code.lower() in ("artikel", "art", "sku"):
                continue  # строка заголовков
            try:
                self._row(code, size.strip(), price.strip(), action)
            except ValueError as exc:
                errors += 1
                self.stdout.write(f"  ! {n}: {code} — {exc}")
        return errors

    def _row(self, code, size, price, action):
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r} (leer | nur | loeschen)")
        product = _find_product(code) if code else None
        if product is None:
            raise ValueError("article not found")
        name = product.get_i18n("name")
        self._lock(product)
        if action == "loeschen":
            product.delete()
            self.stdout.write(f"  - {code} {name}: deleted")
            return
        grams = parse_size(size)
        if grams is None:
            raise ValueError(f"pack size {size!r} not understood (z. B. 100 g)")
        try:
            amount = parse_amount(price)
        except ValueError as exc:
            raise ValueError(f"price {price!r} not understood") from exc
        if amount is None or amount <= 0:
            raise ValueError("price missing")
        variants = list(product.variants.all())
        match = [v for v in variants if _variant_grams(v) == grams]
        if action == "nur":
            self._only(product, variants, match, grams, amount, code, name, size)
            return
        if not match:
            raise ValueError(f"no pack {size} (packs: {', '.join(v.label for v in variants)})")
        variant = match[0]
        old = variant.price
        variant.price = amount
        variant.is_active = True
        variant.save(update_fields=["price", "is_active"])
        self._sync_base(product)
        self.stdout.write(f"  {code} {name} {variant.label}: {_money(old)} → {_money(amount)}")

    def _only(self, product, variants, match, grams, amount, code, name, size):
        """Одна фасовка: товар продаётся без выбора фасовки — цена и вес на самом товаре."""
        old = match[0].price if match else product.base_price
        off = [v for v in variants if v.is_active]
        for v in off:
            v.is_active = False
            v.save(update_fields=["is_active"])
        product.base_price = amount
        product.unit = "g"
        product.content_amount = grams
        product.is_active = True
        if product.primary_action == "request":
            product.primary_action = ""  # скрыт импортом «до цены» — цена появилась
        product.save(
            update_fields=["base_price", "unit", "content_amount", "is_active", "primary_action"]
        )
        removed = f", {len(off)} packs off sale" if off else ""
        self.stdout.write(
            f"  {code} {name}: only {size} — {_money(old)} → {_money(amount)}{removed}"
        )

    @staticmethod
    def _lock(product):
        """Повторный import_cscart больше не перезапишет цены старым сайтом."""
        from apps.imports.cscart import OWNER_PRICES_KEY

        meta = dict(product.metadata or {})
        if not meta.get(OWNER_PRICES_KEY):
            meta[OWNER_PRICES_KEY] = True
            product.metadata = meta
            product.save(update_fields=["metadata"])

    @staticmethod
    def _sync_base(product):
        """Цена товара в списках = цена первой продаваемой фасовки (как у импорта)."""
        first = product.variants.filter(is_active=True).order_by("sort_order", "created_at").first()
        if first is not None and first.price and product.base_price != first.price:
            product.base_price = first.price
            product.save(update_fields=["base_price"])
