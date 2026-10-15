"""T-8.8: JSON-LD страницы предложения каталога города — тип по виду листинга.

План — docs/t8-8-machine-readable-plan-2026-10-15.md §2 (Р-2). Страница предложения
портала (`views.offer_page`) раньше отдавала всегда `Product` с продавцом из одного
имени; здесь тип зависит от `listing_kind`, продавец — полный `LocalBusiness` из
ПУБЛИЧНЫХ полей тенанта (`core.seo.localbusiness_data`), наличие — по полю листинга.

Правила (все замками в test_machine_readable):
* mystery-акции цены не имеют уже в снимке (`tasks._snapshot`) → Offer без price;
* `old_price` в разметку НЕ отдаём (StrikethroughPrice без «низшей цены за 30 дней»
  §11 PAngV — тот же анонс снижения, только машинный);
* featured ничем не отличается: «sponsored» — не свойство schema.org;
* сирота без Tenant → фолбэк-продавец из денормализованных полей, не 500.
"""

from __future__ import annotations

from django.utils import timezone

AVAILABILITY = {
    "sold_out": "https://schema.org/SoldOut",
    # MadeToOrder точнее PreOrder: «ещё не вышло» ≠ «делаем под заказ».
    "on_request": "https://schema.org/MadeToOrder",
}
IN_STOCK = "https://schema.org/InStock"
# Виды, у которых пустое наличие значит «есть» (у номера/услуги/бизнеса — не указываем).
_STOCKED_KINDS = ("product", "promotion", "menu", "event")


def availability_iri(listing) -> str | None:
    value = getattr(listing, "availability", "") or ""
    if value in AVAILABILITY:
        return AVAILABILITY[value]
    if listing.listing_kind in _STOCKED_KINDS:
        return IN_STOCK
    return None


def price_visible(listing) -> bool:
    return listing.new_price is not None


def _localdate(dt) -> str:
    return timezone.localdate(dt).isoformat()


def seller_data(listing, tenant, *, request) -> dict:
    """LocalBusiness продавца: тенант есть → публичные поля; нет → из листинга."""
    if tenant is not None:
        from apps.core.seo import localbusiness_data

        data = localbusiness_data(tenant, url=_origin(listing.detail_url))
        if data:
            return data
    data = {"@type": "LocalBusiness", "name": listing.business_name}
    if listing.city:
        data["address"] = {"@type": "PostalAddress", "addressLocality": listing.city}
    return data


def _origin(url: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}/" if parts.scheme and parts.netloc else url


def offer_data(listing, *, url: str) -> dict | None:
    """schema.org Offer для листинга или None (нет цены и нет наличия — нечего сказать)."""
    offer: dict = {"@type": "Offer", "url": url}
    if price_visible(listing):
        offer["price"] = f"{listing.new_price:.2f}"
        offer["priceCurrency"] = listing.currency or "EUR"
        kind = listing.listing_kind
        if kind == "menu" and listing.price_per_person:
            offer["priceSpecification"] = {
                "@type": "UnitPriceSpecification",
                "price": f"{listing.new_price:.2f}",
                "priceCurrency": listing.currency or "EUR",
                "unitText": "Person",
            }
        elif kind == "stay":
            offer["priceSpecification"] = {
                "@type": "UnitPriceSpecification",
                "price": f"{listing.new_price:.2f}",
                "priceCurrency": listing.currency or "EUR",
                "unitCode": "DAY",
            }
    if listing.listing_kind == "menu" and listing.min_persons:
        offer["eligibleQuantity"] = {
            "@type": "QuantitativeValue",
            "minValue": int(listing.min_persons),
        }
    if listing.starts_at and listing.listing_kind == "promotion":
        offer["validFrom"] = listing.starts_at.isoformat()
    if listing.ends_at and listing.listing_kind in ("promotion", "product", "menu"):
        offer["priceValidUntil"] = _localdate(listing.ends_at)
    availability = availability_iri(listing)
    if availability:
        offer["availability"] = availability
    # Без цены (mystery, номер/услуга «на запрос») Offer имеет смысл только при ЯВНОМ
    # наличии (sold_out/on_request); «InStock» по умолчанию без цены — пустой шум.
    explicit = (getattr(listing, "availability", "") or "") in AVAILABILITY
    if not price_visible(listing) and not explicit:
        return None
    return offer


def listing_ld(listing, *, request, tenant=None) -> dict:
    """Полный JSON-LD страницы предложения (диспатч по `listing_kind`)."""
    kind = listing.listing_kind
    url = listing.detail_url
    seller = seller_data(listing, tenant, request=request)
    if kind == "business":
        data = dict(seller)
        data.setdefault("@context", "https://schema.org")
        data["url"] = url
        if listing.teaser_text:
            data["description"] = listing.teaser_text
        return data

    types = {"stay": "HotelRoom", "service": "Service", "event": "Event"}
    data: dict = {
        "@context": "https://schema.org",
        "@type": types.get(kind, "Product"),
        "name": listing.title_text,
        "url": url,
    }
    if listing.teaser_text:
        data["description"] = listing.teaser_text
    if (listing.image or {}).get("url"):
        data["image"] = request.build_absolute_uri(listing.image["url"])
    offer = offer_data(listing, url=url)
    if kind == "stay":
        lodging = dict(seller)
        lodging["@type"] = "LodgingBusiness"
        data["containedInPlace"] = lodging
    elif kind == "service":
        data["provider"] = seller
    elif kind == "event":
        if listing.starts_at:
            data["startDate"] = listing.starts_at.isoformat()
        if listing.ends_at:
            data["endDate"] = listing.ends_at.isoformat()
        data["eventStatus"] = "https://schema.org/EventScheduled"
        data["eventAttendanceMode"] = "https://schema.org/OfflineEventAttendanceMode"
        place: dict = {"@type": "Place", "name": listing.business_name}
        address = dict(seller.get("address") or {})
        if listing.district_name:
            address.setdefault("@type", "PostalAddress")
            address["addressRegion"] = listing.district_name
        if listing.city:
            address.setdefault("@type", "PostalAddress")
            address.setdefault("addressLocality", listing.city)
        if address:
            place["address"] = address
        data["location"] = place
        data["organizer"] = seller
    if offer is not None:
        if kind not in ("stay", "service"):
            offer["seller"] = seller
        data["offers"] = offer
    return data
