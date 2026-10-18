"""Product-feed (M23b): Google Merchant / Meta Commerce RSS 2.0.

Один формат ест и Google Merchant Center, и Meta Commerce Manager (загрузка по
URL по расписанию). Отдаётся публично на субдомене бизнеса (как sitemap.xml).
Билдер чистый: URL-функции передаём снаружи (мульти-тенант — домен из request).

Варианты (R1) — отдельные <item> с общим g:item_group_id (товар), своей ценой
и наличием. Наличие — из R3 (in_stock). Без фото товар всё равно в фиде
(g:image_link опускаем — площадка предупредит, владелец дополнит).
"""

import re
from decimal import Decimal
from xml.sax.saxutils import escape as _escape

# M23b.1: управляющие символы (кроме \t \n \r) запрещены в XML 1.0 — один такой символ
# в названии товара делал весь фид нечитаемым для площадки.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")

# M23b.1 (В-3): состояние товара (O-1) → g:condition. Пусто/новое → new, прочее → used.
_NEW_CONDITIONS = {"", "neu", "neu_ohne_ovp"}


def escape(value: str) -> str:
    return _escape(_XML_ILLEGAL.sub("", value))


def _money(value, currency: str) -> str:
    # DecimalField у не перезагруженных из БД инстансов может быть строкой.
    return f"{Decimal(str(value)):.2f} {currency}"


def _item_xml(fields: dict) -> str:
    parts = []
    for key, value in fields.items():
        if value in (None, ""):
            continue
        parts.append(f"<g:{key}>{escape(str(value))}</g:{key}>")
    return "<item>" + "".join(parts) + "</item>"


def _merchant_variants(product) -> list:
    cached = getattr(product, "feed_variants", None)
    variants = list(cached) if cached is not None else list(product.active_variants)
    # Вариант за 0,00 € Google отклоняет — в фид не выводим (отбор: google.py).
    return [v for v in variants if Decimal(str(v.price_value or 0)) > 0]


def merchant_item_rows(product) -> list[dict]:
    """M23b.3: позиции товара в фидах Merchant Center — ОДИН источник id для фида товаров
    и фида наличия (Google сопоставляет их по id). [{"id", "variant", "stock"}].

    id ≤ 50 знаков (лимит Google): товар — `str(pk)` (36), вариант — `pk.hex` (32);
    прежний вид «товар:вариант» давал 73 знака."""
    variants = _merchant_variants(product)
    if variants:
        return [{"id": v.pk.hex, "variant": v, "stock": v.stock_quantity} for v in variants]
    return [{"id": str(product.pk), "variant": None, "stock": product.stock_quantity}]


def local_availability(stock) -> tuple[str, int | None]:
    """Наличие в магазине (В-8: без limited_availability — Google сам считает 1–2 «мало»).
    Остаток не ведётся → «в наличии» без количества; ноль и меньше → «нет»."""
    if stock is None:
        return "in_stock", None
    if stock > 0:
        return "in_stock", stock
    return "out_of_stock", 0


def _entries(product, *, product_url, absolutize, merchant=False):
    """Записи фида для товара: по одной на активный вариант, иначе одна на товар.

    merchant=True (M23b.1, фид Merchant Center): марка из поля `Product.brand`, состояние по
    `Product.condition`, варианты из предзагрузки `feed_variants` (google.merchant_products)."""
    link = product_url(product)
    img = product.primary_image
    image_link = absolutize(img["url"]) if img and img.get("url") else ""
    title = product.name_text or str(product)
    description = product.description_text or title
    legacy_brand = product.metadata.get("brand") if isinstance(product.metadata, dict) else ""
    if merchant:
        brand = product.brand or legacy_brand or ""
        condition = "new" if (product.condition or "") in _NEW_CONDITIONS else "used"
    else:
        brand, condition = legacy_brand, "new"

    def base(item_id, item_title, price, available, gtin="", sku=""):
        eff_gtin = gtin or product.gtin or ""  # A1: вариантный EAN перебивает товарный
        # Фидбэк 2026-08-04: вариантный артикул перебивает товарный (как EAN).
        eff_sku = sku or product.sku or ""
        return {
            "id": item_id,
            "title": item_title,
            "description": description,
            "link": link,
            "image_link": image_link,
            "availability": "in_stock" if available else "out_of_stock",
            "price": _money(price, product.currency),
            "brand": brand,
            "condition": condition,
            "gtin": eff_gtin,
            "mpn": eff_sku,
            "identifier_exists": "no" if not (eff_gtin or eff_sku or brand) else "",
        }

    if merchant:
        rows = merchant_item_rows(product)
        if rows[0]["variant"] is None:
            in_stock = product.stock_quantity is None or product.stock_quantity > 0
            return [base(rows[0]["id"], title, product.base_price, in_stock)]
        return [
            {
                **base(
                    row["id"],
                    f"{title} – {row['variant'].label}",
                    row["variant"].price_value,
                    row["variant"].in_stock,
                    gtin=row["variant"].gtin,
                    sku=row["variant"].sku,
                ),
                "item_group_id": str(product.pk),
            }
            for row in rows
        ]
    variants = list(product.active_variants)
    if variants:
        return [
            {
                **base(
                    f"{product.pk}:{v.pk}",
                    f"{title} – {v.label}",
                    v.price_value,
                    v.in_stock,
                    gtin=v.gtin,
                    sku=v.sku,
                ),
                "item_group_id": str(product.pk),
            }
            for v in variants
        ]
    in_stock = product.stock_quantity is None or product.stock_quantity > 0
    return [base(str(product.pk), title, product.base_price, in_stock)]


def _rss(head: str, items: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">'
        f"<channel>{head}{''.join(items)}</channel></rss>"
    )


def build_local_inventory_feed(*, products, store_code, title, link) -> str:
    """M23b.3: фид наличия в магазине (Merchant Center «Lokales Inventar») — те же id, что в
    фиде товаров, + store_code из профиля Google. Без кода магазина — пустой валидный фид."""
    items = []
    if store_code:
        for product in products:
            for row in merchant_item_rows(product):
                availability, quantity = local_availability(row["stock"])
                items.append(
                    _item_xml(
                        {
                            "id": row["id"],
                            "store_code": store_code,
                            "availability": availability,
                            "quantity": "" if quantity is None else quantity,
                        }
                    )
                )
    head = f"<title>{escape(title)}</title><link>{escape(link)}</link>"
    return _rss(head, items)


def build_google_feed(
    *, products, title, link, description, product_url, absolutize, merchant=False
):
    """RSS 2.0 (g:-namespace) строка по активным товарам.

    product_url(product) → абсолютная ссылка на товар; absolutize(url) → абсолютный
    URL медиа. products — итерируемое Product (с active_variants).
    """
    items = []
    for product in products:
        items += [
            _item_xml(f)
            for f in _entries(
                product, product_url=product_url, absolutize=absolutize, merchant=merchant
            )
        ]
    head = (
        f"<title>{escape(title)}</title>"
        f"<link>{escape(link)}</link>"
        f"<description>{escape(description)}</description>"
    )
    return _rss(head, items)
