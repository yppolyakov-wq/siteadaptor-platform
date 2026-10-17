"""Извлечение без ИИ (T-8.27b): JSON-LD schema.org + OpenGraph/meta.

Даёт реальный результат на магазинах (Shopify/WooCommerce/Wix/Squarespace/JTL пишут
Product/Offer в JSON-LD); сайт-брошюра обычно даёт только профиль (LocalBusiness,
часы, адрес, телефон, лого). Цена берётся КАК НА САЙТЕ: старая цена, процент скидки,
«statt» не извлекаются вовсе (PAngV — импорт не создаёт ценовых обещаний).
Весь текст — плоский: разметку чужого сайта не переносим."""

from __future__ import annotations

import html as html_lib
import re
from decimal import Decimal, InvalidOperation

import nh3

NAME_MAX = 120
DESC_MAX = 1500
CATEGORY_MAX = 60
PRICE_MAX = Decimal("100000")

PRODUCT_TYPES = {"product", "productgroup", "individualproduct", "productmodel", "menuitem"}
SERVICE_TYPES = {"service"}
# Подтипы LocalBusiness, которые реально встречаются у малого бизнеса DACH; иначе —
# по признакам (адрес/часы у сущности с именем).
BUSINESS_TYPES = {
    "localbusiness", "organization", "store", "bakery", "restaurant", "cafeorcoffeeshop",
    "foodestablishment", "barorpub", "butchershop" , "grocerystore", "clothingstore",
    "hairsalon", "beautysalon", "healthandbeautybusiness", "autorepair", "hotel",
    "lodgingbusiness", "homeandconstructionbusiness", "professionalservice", "shoestore",
    "bookstore", "florist", "furniturestore", "hardwarestore", "jewelrystore",
    "petstore", "sportinggoodsstore", "toystore", "electronicsstore", "bikestore",
    "dayspa", "healthclub", "medicalbusiness", "optician", "travelagency",
}  # fmt: skip
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)")


def plain(value, limit: int) -> str:
    """HTML → плоский текст (теги срезаны, сущности раскрыты, пробелы схлопнуты)."""
    if not isinstance(value, str):
        return ""
    text = html_lib.unescape(nh3.clean(value, tags=set()))
    return " ".join(text.split())[:limit]


def price_of(value) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip().replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    if not (Decimal("0") < amount <= PRICE_MAX):
        return None
    return str(amount.quantize(Decimal("0.01")))


def _types(node) -> set:
    raw = node.get("@type") if isinstance(node, dict) else None
    values = raw if isinstance(raw, list) else [raw]
    return {str(v).rsplit("/", 1)[-1].lower() for v in values if v}


def _walk(node, out: list, depth: int = 0):
    if depth > 8:
        return
    if isinstance(node, list):
        for child in node[:500]:
            _walk(child, out, depth + 1)
    elif isinstance(node, dict):
        out.append(node)
        for key in (
            "@graph",
            "itemListElement",
            "item",
            "hasOfferCatalog",
            "makesOffer",
            "itemOffered",
            "hasMenu",
            "hasMenuSection",
            "hasMenuItem",
            "mainEntity",
        ):
            if key in node:
                _walk(node[key], out, depth + 1)


def _first_url(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl") or ""
    value = value if isinstance(value, str) else ""
    return value if value.startswith(("http://", "https://")) else ""


def _offer_price(offers) -> tuple[str | None, str]:
    """Цена из Offer/AggregateOffer (lowPrice → «ab»). Только EUR (или без валюты)."""
    items = offers if isinstance(offers, list) else [offers]
    for offer in items:
        if not isinstance(offer, dict):
            continue
        currency = str(offer.get("priceCurrency") or "EUR").upper()
        if currency != "EUR":
            continue
        spec = offer.get("priceSpecification")
        candidates = [offer.get("price"), offer.get("lowPrice")]
        if isinstance(spec, dict):
            candidates.append(spec.get("price"))
        for raw in candidates:
            price = price_of(raw)
            if price:
                return price, "EUR"
    return None, "EUR"


def _gtin(node) -> str:
    for key in ("gtin13", "gtin", "gtin14", "gtin12", "gtin8"):
        value = str(node.get(key) or "").strip()
        if value.isdigit() and 8 <= len(value) <= 14:
            return value
    return ""


def _item(node, kind: str, page_url: str) -> dict | None:
    name = plain(node.get("name"), NAME_MAX)
    if not name:
        return None
    price, currency = _offer_price(node.get("offers"))
    url = node.get("url") if isinstance(node.get("url"), str) else ""
    category = node.get("category")
    if isinstance(category, dict):
        category = category.get("name")
    return {
        "kind": kind,
        "name": name,
        "description": plain(node.get("description"), DESC_MAX),
        "price": price,
        "currency": currency,
        "image_url": _first_url(node.get("image")),
        "page_url": url if url.startswith(("http://", "https://")) else page_url,
        "sku": plain(node.get("sku"), 64),
        "gtin": _gtin(node),
        "category_hint": plain(category, CATEGORY_MAX),
        "method": "structured",
    }


def _hours(node) -> dict:
    out = {}
    specs = node.get("openingHoursSpecification") or []
    for spec in specs if isinstance(specs, list) else [specs]:
        if not isinstance(spec, dict):
            continue
        opens, closes = str(spec.get("opens") or ""), str(spec.get("closes") or "")
        if not (_TIME.match(opens) and _TIME.match(closes)):
            continue
        days = spec.get("dayOfWeek") or []
        for day in days if isinstance(days, list) else [days]:
            key = str(day).rsplit("/", 1)[-1].lower()
            if key in _DAYS:
                out[str(_DAYS.index(key))] = [opens[:5].zfill(5), closes[:5].zfill(5)]
    return out


def _address(node) -> str:
    addr = node.get("address")
    if isinstance(addr, str):
        return plain(addr, 300)
    if not isinstance(addr, dict):
        return ""
    street = plain(addr.get("streetAddress"), 150)
    city = " ".join(
        p for p in (plain(addr.get("postalCode"), 10), plain(addr.get("addressLocality"), 80)) if p
    )
    return ", ".join(p for p in (street, city) if p)


def _business(node) -> dict:
    return {
        "name": plain(node.get("name"), 200),
        "description": plain(node.get("description"), DESC_MAX),
        "phone": plain(node.get("telephone"), 40),
        "address": _address(node),
        "opening_hours_structured": _hours(node),
        "logo_url": _first_url(node.get("logo")),
        "image_url": _first_url(node.get("image")),
    }


def _identity(item: dict) -> str:
    if item.get("gtin"):
        return f"gtin:{item['gtin']}"
    if item.get("sku"):
        return f"sku:{item['sku'].lower()}"
    return f"url:{item.get('page_url', '')}|{item['name'].lower()}"


def extract(pages) -> dict:
    """pages: список `htmlparse.Page` → {"profile": {...}, "items": [...], "lang": "de"}."""
    items: dict[str, dict] = {}
    profile: dict = {}
    langs: dict[str, int] = {}
    for page in pages:
        if page.lang:
            langs[page.lang] = langs.get(page.lang, 0) + 1
        nodes: list = []
        for block in page.jsonld:
            _walk(block, nodes)
        page_has_item = False
        for node in nodes:
            types = _types(node)
            kind = (
                "product" if types & PRODUCT_TYPES else "service" if types & SERVICE_TYPES else ""
            )
            if kind:
                item = _item(node, kind, page.url)
                if item:
                    items.setdefault(_identity(item), item)
                    page_has_item = True
            elif types & BUSINESS_TYPES or ("address" in node and node.get("name")):
                for key, value in _business(node).items():
                    if value and not profile.get(key):
                        profile[key] = value
        meta = page.meta
        if not page_has_item and (
            meta.get("og:type", "").lower().startswith("product")
            or meta.get("product:price:amount")
        ):
            currency = (meta.get("product:price:currency") or "EUR").upper()
            item = {
                "kind": "product",
                "name": plain(meta.get("og:title") or page.title, NAME_MAX),
                "description": plain(meta.get("og:description"), DESC_MAX),
                "price": price_of(meta.get("product:price:amount")) if currency == "EUR" else None,
                "currency": "EUR",
                "image_url": _first_url(meta.get("og:image")),
                "page_url": page.url,
                "sku": "",
                "gtin": "",
                "category_hint": "",
                "method": "structured",
            }
            if item["name"]:
                items.setdefault(_identity(item), item)
        if not profile.get("name") and meta.get("og:site_name"):
            profile["name"] = plain(meta["og:site_name"], 200)
        if not profile.get("description") and meta.get("description"):
            profile["description"] = plain(meta["description"], DESC_MAX)
        if not profile.get("phone") and page.phones:
            profile["phone"] = plain(page.phones[0], 40)
    for key, item in items.items():
        item["identity"] = key
    lang = max(langs, key=langs.get) if langs else ""
    return {"profile": profile, "items": list(items.values()), "lang": lang}
