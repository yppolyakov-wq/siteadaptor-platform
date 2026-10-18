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

    cached = getattr(product, "feed_variants", None) if merchant else None
    variants = list(cached) if cached is not None else list(product.active_variants)
    if merchant:  # вариант за 0,00 € Google отклоняет — в фид не выводим (отбор: google.py)
        variants = [v for v in variants if Decimal(str(v.price_value or 0)) > 0]
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
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">'
        f"<channel>{head}{''.join(items)}</channel></rss>"
    )
