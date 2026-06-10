"""schema.org JSON-LD для локального SEO витрины (Track B5).

Малый бизнес выигрывает локальную выдачу: LocalBusiness на каждой странице
витрины + Offer/Product на странице акции. Чистые функции отдают готовую
JSON-строку — шаблон вставляет её в <script type="application/ld+json">.
Всё через getattr с дефолтами: на неполном тенанте/акции не падаем.
"""

import json

# business_type тенанта → более конкретный тип schema.org (точнее LocalBusiness)
_SCHEMA_TYPES = {
    "bakery": "Bakery",
    "butcher": "Store",
    "grocery": "GroceryStore",
    "clothing": "ClothingStore",
    "restaurant": "Restaurant",
    "cafe": "CafeOrCoffeeShop",
    "retail": "Store",
    "hotel": "Hotel",
}


def _dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def localbusiness_ld(tenant, *, url: str) -> str:
    """JSON-LD LocalBusiness из полей тенанта (или '' если тенанта нет)."""
    if tenant is None:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": _SCHEMA_TYPES.get(getattr(tenant, "business_type", "") or "", "LocalBusiness"),
        "name": getattr(tenant, "name", "") or "",
        "url": url,
    }
    address = getattr(tenant, "address", "") or ""
    city = getattr(tenant, "city", "") or ""
    if address or city:
        addr = {"@type": "PostalAddress"}
        if address:
            addr["streetAddress"] = address
        if city:
            addr["addressLocality"] = city
        if getattr(tenant, "country", "") or "":
            addr["addressCountry"] = tenant.country
        data["address"] = addr
    phone = getattr(tenant, "public_phone", "") or ""
    if phone:
        data["telephone"] = phone
    lat, lng = getattr(tenant, "latitude", None), getattr(tenant, "longitude", None)
    if lat is not None and lng is not None:
        data["geo"] = {"@type": "GeoCoordinates", "latitude": str(lat), "longitude": str(lng)}
    return _dumps(data)


def offer_ld(promo, *, url: str, image_url: str = "") -> str:
    """JSON-LD Product+Offer из акции (или '' если акции нет)."""
    if promo is None:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": promo.title_text,
        "url": url,
    }
    if promo.description_text:
        data["description"] = promo.description_text
    if image_url:
        data["image"] = image_url
    price = promo.new_price
    if price is not None:
        offer = {
            "@type": "Offer",
            "price": f"{price:.2f}",
            "priceCurrency": getattr(promo, "currency", "") or "EUR",
            "url": url,
            "availability": (
                "https://schema.org/SoldOut"
                if getattr(promo, "is_sold_out", False)
                else "https://schema.org/InStock"
            ),
        }
        if promo.ends_at:
            offer["priceValidUntil"] = promo.ends_at.date().isoformat()
        data["offers"] = offer
    return _dumps(data)


def _itemlist_elements(items) -> list:
    return [
        {"@type": "ListItem", "position": i, "name": name, "url": url}
        for i, (name, url) in enumerate(items, start=1)
        if url
    ]


def itemlist_ld(items) -> str:
    """JSON-LD ItemList из [(name, url), …] для страниц агрегатора (или '')."""
    elements = _itemlist_elements(items)
    if not elements:
        return ""
    return _dumps(
        {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": elements}
    )


def collectionpage_ld(*, name: str, url: str, items) -> str:
    """JSON-LD CollectionPage (+ вложенный ItemList) для страниц портала (P2.1c)."""
    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": name,
        "url": url,
    }
    elements = _itemlist_elements(items)
    if elements:
        data["mainEntity"] = {"@type": "ItemList", "itemListElement": elements}
    return _dumps(data)
