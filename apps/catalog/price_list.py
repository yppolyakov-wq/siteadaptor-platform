"""M21.7: прайс-лист владельца — цены и фасовки по артикулам (одно место правил).

Строка = артикул · фасовка · цена · действие. Действие:
- пусто — цена фасовки (``HT515;250 g;22,10``);
- ``nur`` — только эта фасовка: товар продаётся одной фасовкой по этой цене, остальные
  фасовки сняты с продажи (не стёрты — история заказов цела), скрытый товар снова виден;
- ``loeschen`` — удалить товар (мягко, как кнопка «Löschen»).

Используют: команда ``update_prices`` и мастер импорта (тип «Preisliste»).
Товар, тронутый прайс-листом, помечается ``OWNER_PRICES_KEY`` — повторный импорт со
старого сайта (``import_cscart``) его цены больше не синхронизирует.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from django.utils.translation import gettext as _

OWNER_PRICES_KEY = "prices_by_owner"

_SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(g|gr|kg|ml|l)?\.?\s*$", re.I)
# Синонимы действий: файл пишут руками на разных языках.
_ACTIONS = {
    "": "",
    "preis": "",
    "price": "",
    "nur": "only",
    "only": "only",
    "einzeln": "only",
    "только": "only",
    "loeschen": "delete",
    "löschen": "delete",
    "delete": "delete",
    "entfernen": "delete",
    "удалить": "delete",
}


class PriceListError(ValueError):
    """Строку нельзя применить — текст для владельца/оператора."""


@dataclass(frozen=True)
class Change:
    code: str
    name: str
    text: str  # «100 g: 9,00 → 9,30» / «nur 50 g: — → 4,99» / «gelöscht»
    product: object = None


def parse_action(raw) -> str:
    key = str(raw or "").strip().lower()
    if key not in _ACTIONS:
        raise PriceListError(_("Aktion „%(a)s“ unbekannt (leer, nur oder löschen).") % {"a": raw})
    return _ACTIONS[key]


def parse_size(raw):
    """«100 g» / «100g» / «100 gr» / «1 kg» → граммы (Decimal) или None."""
    m = _SIZE_RE.match(str(raw or ""))
    if not m:
        return None
    amount = Decimal(m.group(1).replace(",", "."))
    unit = (m.group(2) or "g").lower()
    return amount * 1000 if unit in ("kg", "l") else amount


def parse_price(raw) -> Decimal:
    from apps.core.money import parse_amount

    try:
        amount = parse_amount(str(raw or ""))
    except ValueError as exc:
        raise PriceListError(_("Preis „%(p)s“ nicht lesbar.") % {"p": raw}) from exc
    if amount is None or amount <= 0:
        raise PriceListError(_("Preis fehlt."))
    return amount


def find_product(code: str):
    """Товар по артикулу товара или фасовки (``HT515.1`` → товар HT515), без регистра."""
    from apps.catalog.models import Product, ProductVariant

    code = (code or "").strip()
    if not code:
        return None
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


def _variant_grams(variant):
    if variant.content_amount:
        return Decimal(variant.content_amount)
    return parse_size(variant.size or variant.label)


def _money(value) -> str:
    return "—" if value is None else f"{Decimal(value):.2f}".replace(".", ",")


def check_row(code, size, price, action):
    """Проверка без записи: (товар, действие, граммы, цена, совпавшая фасовка)."""
    action = parse_action(action)
    product = find_product(code)
    if product is None:
        raise PriceListError(_("Artikel nicht gefunden."))
    if action == "delete":
        return product, action, None, None, None
    grams = parse_size(size)
    if grams is None:
        raise PriceListError(_("Packung „%(s)s“ nicht lesbar (z. B. 100 g).") % {"s": size})
    amount = parse_price(price)
    match = next((v for v in product.variants.all() if _variant_grams(v) == grams), None)
    if action == "" and match is None:
        packs = ", ".join(v.label for v in product.variants.all()) or "—"
        raise PriceListError(
            _("Packung %(s)s gibt es nicht (vorhanden: %(packs)s).") % {"s": size, "packs": packs}
        )
    return product, action, grams, amount, match


def apply_row(code, size, price, action) -> Change:
    """Применить строку (вызывать внутри транзакции)."""
    product, action, grams, amount, match = check_row(code, size, price, action)
    name = product.get_i18n("name")
    _lock(product)
    if action == "delete":
        product.delete()
        return Change(code, name, _("gelöscht"), product)
    if action == "only":
        old = match.price if match else product.base_price
        off = [v for v in product.variants.all() if v.is_active]
        for v in off:
            v.is_active = False
            v.save(update_fields=["is_active"])
        product.base_price = amount
        product.unit = "g"
        product.content_amount = grams
        product.is_active = True
        if product.primary_action == "request":
            product.primary_action = ""  # импорт скрыл «до цены» — цена появилась
        product.save(
            update_fields=["base_price", "unit", "content_amount", "is_active", "primary_action"]
        )
        text = _("nur %(s)s: %(old)s → %(new)s") % {
            "s": size,
            "old": _money(old),
            "new": _money(amount),
        }
        if off:
            text += " · " + _("%(n)s Packungen aus dem Verkauf") % {"n": len(off)}
        return Change(code, name, text, product)
    old = match.price
    match.price = amount
    match.is_active = True
    match.save(update_fields=["price", "is_active"])
    _sync_base(product)
    return Change(code, name, f"{match.label}: {_money(old)} → {_money(amount)}", product)


def _lock(product) -> None:
    meta = dict(product.metadata or {})
    if not meta.get(OWNER_PRICES_KEY):
        meta[OWNER_PRICES_KEY] = True
        product.metadata = meta
        product.save(update_fields=["metadata"])


def _sync_base(product) -> None:
    """Цена товара в списках = цена первой продаваемой фасовки (как у импорта)."""
    first = product.variants.filter(is_active=True).order_by("sort_order", "created_at").first()
    if first is not None and first.price and product.base_price != first.price:
        product.base_price = first.price
        product.save(update_fields=["base_price"])
