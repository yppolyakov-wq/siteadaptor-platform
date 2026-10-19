"""Отбор товаров для фида Google Merchant Center (M23b.1, план docs/m23b-merchant-feed-plan-2026-10-18.md).

Одна точка истины для фида и экрана кабинета (M23b.2): что уходит в Google и почему остальное нет.
Причины исключения (жёсткие) — товар в фид не попадает; предупреждения — попадает, но Google
может показать хуже. Старый `/feed/google.xml` (общий с Meta) этим модулем не фильтруется."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

_MAX_DEPTH = 10  # предохранитель от цикла parent в данных

REASONS = ("hidden", "category_hidden", "no_image", "no_price", "promo_mystery", "promo_sold_out")
WARNINGS = ("no_identifier", "no_description")

# M23b.2: подписи для экрана кабинета (коды наружу не показываем).
REASON_LABELS = {
    "hidden": _("Mit „Nicht an Google senden“ ausgeblendet"),
    "category_hidden": _("Kategorie ausgeblendet oder inaktiv"),
    "no_image": _("Kein Foto"),
    "no_price": _("Kein Preis"),
    # M23b.4: цену фида нельзя сказать честно — товар уходит из фида на время акции.
    "promo_mystery": _("Überraschungsaktion läuft – Preis bleibt geheim"),
    "promo_sold_out": _("Aktionslimit erreicht"),
}
WARNING_LABELS = {
    "no_identifier": _("Keine EAN, Artikelnummer oder Marke – Google zeigt das Produkt seltener"),
    "no_description": _("Keine Beschreibung"),
}


def _hidden_category_ids() -> set:
    """id категорий, чья ветка не уходит в Google: своя галочка, галочка предка, неактивна
    или удалена. Один запрос на весь каталог (категорий у бизнеса — десятки)."""
    from .models import Category

    rows = {
        pk: (parent_id, hide or not active or deleted is not None)
        for pk, parent_id, hide, active, deleted in Category.all_objects.values_list(
            "pk", "parent_id", "hide_in_google", "is_active", "deleted_at"
        )
    }
    hidden = set()
    for pk in rows:
        current, seen = pk, set()
        while current is not None:
            row = rows.get(current)
            # Нет строки, своя галочка или цикл parent в данных — ветку не отдаём (fail-closed).
            if row is None or row[1] or current in seen or len(seen) > _MAX_DEPTH:
                hidden.add(pk)
                break
            seen.add(current)
            current = row[0]
    return hidden


def _variants(product) -> list:
    cached = getattr(product, "feed_variants", None)
    return cached if cached is not None else list(product.active_variants)


def _positive(value) -> bool:
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _promo_block(promo) -> str | None:
    """M23b.4: акция, при которой честной цены для Google нет.

    Проверяется ТА ЖЕ акция, что выбрала корзина (`product_promo_map`), — иначе фид
    взял бы другую акцию, чем чекаут. Mystery: любая цена либо раскрыла бы секрет,
    либо разошлась со страницей товара. Исчерпанный лимит: чекаут не продаёт вовсе."""
    if promo is None:
        return None
    if promo.discount_style == "mystery":
        return "promo_mystery"
    if promo.available_quantity is not None and promo.available_quantity <= 0:
        return "promo_sold_out"
    return None


def eligibility(
    product, *, hidden_categories: set | None = None, promo=None
) -> tuple[bool, list, list]:
    """(уходит ли в фид, причины исключения, предупреждения). У исключённого товара
    предупреждений нет — экран показывает ему только то, что его исключило.

    В цикле передавайте `hidden_categories=_hidden_category_ids()` один раз — без него
    каждый вызов читает категории заново. `promo` — акция корзины на товар (M23b.4)."""
    if product.hide_in_google:
        return False, ["hidden"], []
    if hidden_categories is None:
        hidden_categories = _hidden_category_ids()
    reasons = []
    if product.category_id and product.category_id in hidden_categories:
        reasons.append("category_hidden")
    img = product.primary_image
    if not (img and img.get("url")):
        reasons.append("no_image")
    variants = _variants(product)
    prices = [v.price_value for v in variants] if variants else [product.base_price]
    if not any(_positive(p) for p in prices):
        reasons.append("no_price")
    if not reasons and (block := _promo_block(promo)):
        reasons.append(block)
    if reasons:
        return False, reasons, []
    warnings = []
    has_id = product.gtin or product.sku or product.brand or any(v.gtin or v.sku for v in variants)
    if not has_id:
        warnings.append("no_identifier")
    if not product.description_text:
        warnings.append("no_description")
    return True, [], warnings


def _active_products():
    from .models import Product, ProductVariant

    return (
        Product.objects.filter(is_active=True)
        .select_related("category")  # KAT-3: SEO-ссылка товара без N+1
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True),
                to_attr="feed_variants",
            )
        )
        .order_by("-created_at")
    )


def _evaluated():
    """Товары с вердиктом. Каждому товару ставится `merchant_promo` — акция, которую
    применит корзина (`price_layer.product_promo_map`, один запрос на весь фид)."""
    from apps.promotions.price_layer import product_promo_map

    hidden = _hidden_category_ids()
    products = list(_active_products())
    promos = product_promo_map([p.pk for p in products])
    if promos:
        # §11 PAngV (SF-7): «Sie sparen» витрины = `has_discount`; цена сравнения —
        # одним батчем, как у `attach_promos` (без N+1 на `prior_lowest_price`).
        from apps.promotions import reference_price

        reference_price.attach(list(promos.values()))
    for product in products:
        product.merchant_promo = promos.get(product.pk)
        yield (
            product,
            eligibility(product, hidden_categories=hidden, promo=product.merchant_promo),
        )


def merchant_products() -> list:
    """Активные товары, годные для фида (с предзагруженными активными вариантами)."""
    return [product for product, (ok, _r, _w) in _evaluated() if ok]


def overview(limit_per_group: int = 50) -> dict:
    """Для экрана кабинета: что в фиде, что исключено и почему, что стоит дополнить.

    Исключённый товар группируется по ПЕРВОЙ причине (как `summary`, суммы сходятся),
    но несёт все свои причины; предупреждения — только у товаров, которые в фиде."""
    from .feed import merchant_item_rows, merchant_row_price, merchant_sale

    included = 0
    excluded: dict = {}
    warned: dict = {}
    # M23b.3: позиции фида наличия — с ведением остатка, без него, распроданные.
    local = {"tracked": 0, "untracked": 0, "out_of_stock": 0}
    on_sale = 0  # M23b.4: позиции с ценой акции — тем же расчётом, что фид
    for product, (ok, reasons, warnings) in _evaluated():
        if ok:
            included += 1
            for row in merchant_item_rows(product):
                if "sale_price" in merchant_sale(
                    product, row["variant"], merchant_row_price(product, row)
                ):
                    on_sale += 1
                if row["stock"] is None:
                    local["untracked"] += 1
                else:
                    local["tracked"] += 1
                    if row["stock"] <= 0:
                        local["out_of_stock"] += 1
            for code in warnings:
                group = warned.setdefault(code, {"count": 0, "items": []})
                group["count"] += 1
                if len(group["items"]) < limit_per_group:
                    group["items"].append(product)
            continue
        group = excluded.setdefault(reasons[0], {"count": 0, "items": []})
        group["count"] += 1
        if len(group["items"]) < limit_per_group:
            group["items"].append((product, reasons))
    return {
        "included": included,
        "excluded": excluded,
        "warnings": warned,
        "local": local,
        "on_sale": on_sale,
    }


def summary() -> dict:
    """{"included": N, "excluded": {причина: N}} — исключённый считается по первой причине,
    чтобы сумма совпадала с числом товаров. Те же числа, что у `overview` (выведено из него)."""
    data = overview(limit_per_group=0)
    return {
        "included": data["included"],
        "excluded": {code: group["count"] for code, group in data["excluded"].items()},
    }
