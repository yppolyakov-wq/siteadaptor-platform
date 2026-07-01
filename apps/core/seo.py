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


# JSON-LD встраивается в <script> через mark_safe → экранируем символы, которыми можно
# вырваться из блока (`</script>`) или сломать JS-парсер (U+2028/U+2029). Значения
# остаются валидным JSON (парсер декодирует `<` обратно). По образцу Django
# `json_script`. Централизованно в `_dumps` → защищает ВСЕ JSON-LD (LocalBusiness/Offer/
# Product/Service/…), т.к. name/description/title — свободно редактируемые поля тенанта.
_JSONLD_ESCAPES = {
    ord("<"): "\\u003c",
    ord(">"): "\\u003e",
    ord("&"): "\\u0026",
    0x2028: "\\u2028",
    0x2029: "\\u2029",
}


def _dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).translate(_JSONLD_ESCAPES)


def localbusiness_ld(
    tenant, *, url: str, aggregate_rating=None, price_range="", image="", schema_type=""
) -> str:
    """JSON-LD LocalBusiness из полей тенанта (или '' если тенанта нет).

    aggregate_rating (G8): (avg, count) — добавляет schema.org AggregateRating
    (звёзды в Google-сниппете). None/нулевой count — не добавляем.
    price_range/image (H6): для отелей — диапазон цен «ab …€» и фото (Hotel-rich).
    schema_type (A9): явный тип schema.org (напр. «AutoRepair» для Kfz-Werkstatt),
    иначе выводится из business_type (фолбэк LocalBusiness)."""
    if tenant is None:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": schema_type
        or _SCHEMA_TYPES.get(getattr(tenant, "business_type", "") or "", "LocalBusiness"),
        "name": getattr(tenant, "name", "") or "",
        "url": url,
    }
    if price_range:
        data["priceRange"] = price_range
    if image:
        data["image"] = image
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
    # A8: часы работы → schema.org OpeningHoursSpecification (сильный сигнал Map Pack/AI).
    # Ленивый импорт (core не тянет tenants на уровне модуля). Один интервал на день (v1).
    from apps.tenants import openinghours

    _hours = openinghours.normalize(getattr(tenant, "opening_hours_structured", None))
    if _hours:
        _days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        data["openingHoursSpecification"] = [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": f"https://schema.org/{_days[int(wd)]}",
                "opens": rng[0],
                "closes": rng[1],
            }
            for wd, rng in sorted(_hours.items(), key=lambda kv: int(kv[0]))
        ]
    # A8: лого бренда + фолбэк image (если фото не передано), официальный сайт → sameAs.
    logo = getattr(tenant, "logo_url", "") or ""
    if logo:
        data["logo"] = logo
        data.setdefault("image", logo)
    website = getattr(tenant, "website_url", "") or ""
    if website:
        data["sameAs"] = [website]
    if aggregate_rating is not None:
        value, count = aggregate_rating
        if count:
            data["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": f"{float(value):.1f}",
                "reviewCount": int(count),
                "bestRating": "5",
                "worstRating": "1",
            }
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


# UA4-4b: kind продаваемой сущности → тип schema.org (по плану U-A). Отзывы/рейтинг
# (AggregateRating) добавляются, если у сущности есть опубликованные отзывы.
_ENTITY_SCHEMA_TYPES = {
    "product": "Product",
    "service": "Service",
    "stay": "LodgingBusiness",
    "event": "Event",
}


def entity_ld(sellable, *, url: str, review_summary=None, schema_type: str = "") -> str:
    """JSON-LD продаваемой сущности из протокола `SellableEntity` + AggregateRating
    из generic-summary отзывов (UA4-4b). Пусто → '' (нет sellable).

    Работает с КОНТРАКТОМ (`kind`/`name`/`description`/`image_url`), не со знанием
    модели — один helper для товара/услуги/номера/события. `review_summary` —
    {avg, count} из `apps.reviews.services.summary`; при count>0 добавляем звёзды."""
    if sellable is None:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": schema_type or _ENTITY_SCHEMA_TYPES.get(getattr(sellable, "kind", ""), "Product"),
        "name": getattr(sellable, "name", "") or "",
        "url": url,
    }
    description = getattr(sellable, "description", "") or ""
    if description:
        data["description"] = description
    image = getattr(sellable, "image_url", "") or ""
    if image:
        data["image"] = image
    if review_summary and review_summary.get("count"):
        data["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": f"{float(review_summary['avg']):.1f}",
            "reviewCount": int(review_summary["count"]),
            "bestRating": "5",
            "worstRating": "1",
        }
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
