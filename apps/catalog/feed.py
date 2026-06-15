"""Product-feed (M23b): Google Merchant / Meta Commerce RSS 2.0.

Один формат ест и Google Merchant Center, и Meta Commerce Manager (загрузка по
URL по расписанию). Отдаётся публично на субдомене бизнеса (как sitemap.xml).
Билдер чистый: URL-функции передаём снаружи (мульти-тенант — домен из request).

Варианты (R1) — отдельные <item> с общим g:item_group_id (товар), своей ценой
и наличием. Наличие — из R3 (in_stock). Без фото товар всё равно в фиде
(g:image_link опускаем — площадка предупредит, владелец дополнит).
"""

from decimal import Decimal
from xml.sax.saxutils import escape


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


def _entries(product, *, product_url, absolutize):
    """Записи фида для товара: по одной на активный вариант, иначе одна на товар."""
    link = product_url(product)
    img = product.primary_image
    image_link = absolutize(img["url"]) if img and img.get("url") else ""
    title = product.name_text or str(product)
    description = product.description_text or title
    brand = product.metadata.get("brand") if isinstance(product.metadata, dict) else ""

    def base(item_id, item_title, price, available, gtin=""):
        eff_gtin = gtin or product.gtin or ""  # A1: вариантный EAN перебивает товарный
        return {
            "id": item_id,
            "title": item_title,
            "description": description,
            "link": link,
            "image_link": image_link,
            "availability": "in_stock" if available else "out_of_stock",
            "price": _money(price, product.currency),
            "brand": brand,
            "condition": "new",
            "gtin": eff_gtin,
            "mpn": product.sku or "",
            "identifier_exists": "no" if not (eff_gtin or product.sku or brand) else "",
        }

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
                ),
                "item_group_id": str(product.pk),
            }
            for v in variants
        ]
    return [base(str(product.pk), title, product.base_price, product.in_stock)]


def build_google_feed(*, products, title, link, description, product_url, absolutize):
    """RSS 2.0 (g:-namespace) строка по активным товарам.

    product_url(product) → абсолютная ссылка на товар; absolutize(url) → абсолютный
    URL медиа. products — итерируемое Product (с active_variants).
    """
    items = []
    for product in products:
        items += [
            _item_xml(f) for f in _entries(product, product_url=product_url, absolutize=absolutize)
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
