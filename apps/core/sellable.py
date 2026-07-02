"""Контракт `SellableEntity` (U-A / UA1-3): единое представление любой продаваемой
сущности витрины (товар/услуга/номер/событие/комбо) для унифицированной детали,
листинга и buy-box (U-A2…U-A4).

Принципы (решения U-A):
- Модели НЕ сливаем. Адаптеры ДЕЛЕГИРУЮТ i18n/цену/фото существующим методам и
  свойствам объекта (напр. `get_i18n`/`name_localized`, `price_eur`, `image_url`) —
  ничего не переизобретаем.
- Импорт `apps.core.sellable` НЕ тянет catalog/stays/events/booking на загрузке:
  адаптеры работают с УЖЕ переданным объектом (методы инстанса), а `purchase_mode`/
  `purchase_label` берём из `apps.core.archetypes` (там модели грузятся лениво).
- `jobs.Job`/Auftrag — НЕ sellable (индивидуальная смета, транзакция под U-D).
"""

from dataclasses import dataclass, field

from django.urls import NoReverseMatch, reverse

from apps.core import archetypes


@dataclass(frozen=True)
class SellableEntity:
    """Нормализованный вид продаваемой сущности. `buybox_context`/`attributes`/
    `info_sections` — швы под U-A3 (buy-box) и U-A4 (секции/атрибуты), пока пустые."""

    kind: str
    pk: object
    name: str
    description: str
    price_display: str
    image_url: str
    gallery: list
    purchase_mode: str
    purchase_label: str
    detail_url: str
    # UA3-2: двухшаговый buy-box. select_url — ГДЕ выбирают (GET; ""=одношаговый
    # kind), submit_url — КУДА бронируют/покупают (POST). buybox_ready — валидный
    # выбор в текущем запросе (quote.available / выбранный слот) — задаёт вьюха.
    select_url: str = ""
    submit_url: str = ""
    buybox_ready: bool = False
    buybox_context: dict = field(default_factory=dict)
    attributes: list = field(default_factory=list)
    info_sections: list = field(default_factory=list)
    # UC4-2: машиночитаемая цена для JSON-LD Offer (price_display — строка для
    # людей) + ld_extra — kind-специфичные SEO-поля (Event startDate/location;
    # вложенный "offer" мержится в Offer — см. core.seo.entity_ld).
    price_value: object = None
    price_currency: str = "EUR"
    ld_extra: dict = field(default_factory=dict)


def _price_str(value, currency: str = "EUR") -> str:
    """DE-строка цены из готового значения в евро (Decimal/float). Пусто → ''."""
    if value in (None, ""):
        return ""
    s = f"{float(value):.2f}".replace(".", ",")
    return f"{s} €" if currency == "EUR" else f"{s} {currency}"


def _gallery_urls(images) -> list:
    """Список URL из FileRef-конвертов (`{url, is_primary, …}`); мусор игнорируем."""
    return [i["url"] for i in (images or []) if isinstance(i, dict) and i.get("url")]


# --- per-kind адаптеры: (obj, locale) → dict(name, description, price_display,
#     image_url, gallery). Только методы/свойства объекта — без обращений к БД сверх
#     тех, что уже делают эти свойства.


def _product(obj, locale):
    base = obj.price_from if obj.has_variants else obj.base_price
    prefix = "ab " if obj.has_variants else ""
    img = obj.primary_image
    return {
        "name": obj.get_i18n("name", locale),
        "description": obj.get_i18n("description", locale),
        "price_display": (prefix + _price_str(base, obj.currency)) if base is not None else "",
        "image_url": img.get("url", "") if isinstance(img, dict) else "",
        "gallery": _gallery_urls(obj.images),
        "price_value": base,
        "price_currency": obj.currency,
        "ld_extra": {
            "offer": {
                "availability": "https://schema.org/InStock"
                if obj.in_stock
                else "https://schema.org/OutOfStock"
            }
        },
    }


def _service(obj, locale):
    return {
        "name": obj.name_localized(locale),
        "description": obj.description_localized(locale),
        "price_display": _price_str(obj.price_eur) if obj.price_cents else "",
        "image_url": obj.image_url,
        "gallery": _gallery_urls(obj.images),
        "price_value": obj.price_eur if obj.price_cents else None,
    }


def _stay(obj, locale):
    return {
        "name": obj.name_localized(locale),
        "description": obj.description_localized(locale),
        "price_display": ("ab " + _price_str(obj.price_eur)) if obj.price_cents else "",
        "image_url": obj.image_url,
        "gallery": _gallery_urls(obj.images),
        "price_value": obj.price_eur if obj.price_cents else None,
    }


def _event(obj, locale):
    if obj.has_tiers:
        price = "ab " + _price_str(obj.from_price_eur)
    elif obj.price_cents:
        price = _price_str(obj.price_eur)
    else:
        price = ""
    # UC4-2 (A6): Event-поля JSON-LD — startDate обязателен Google, location
    # опционален (Place по названию площадки).
    extra = {"startDate": obj.starts_at.isoformat()} if obj.starts_at else {}
    if obj.location:
        extra["location"] = {"@type": "Place", "name": obj.location}
    if obj.has_tiers:
        price_value = obj.from_price_eur
    elif obj.price_cents:
        price_value = obj.price_eur
    else:
        price_value = None
    return {
        "name": obj.get_i18n("title_i18n", locale) or obj.title,
        "description": obj.get_i18n("description_i18n", locale) or obj.description,
        "price_display": price,
        "image_url": obj.image_url,
        "gallery": _gallery_urls(obj.images),
        "price_value": price_value,
        "ld_extra": extra,
    }


def _combo(obj, locale):
    # Комбо (A4 Gastro): фикс-цена + надбавки опций; i18n — L3-оверлей (база в
    # плоских name/description, переводы в *_i18n) — i18n для 5/5 kind.
    # Богатая деталь/варианты — позже.
    return {
        "name": obj.name_localized(locale),
        "description": obj.description_localized(locale),
        "price_display": _price_str(obj.price, obj.currency),
        "image_url": "",
        "gallery": [],
        "price_value": obj.price,
        "price_currency": obj.currency,
    }


# kind → (адаптер, module для purchase_mode/label, URL-имена: деталь, шаг выбора
# (GET, ""=одношаговый kind), submit покупки/брони (POST)). UA3-2: select/submit —
# контрактные адреса двухшагового buy-box.
_KINDS = {
    "product": (_product, "catalog", "storefront-product", "", "storefront-cart-add"),
    "service": (
        _service,
        "booking",
        "storefront-service-detail",
        "storefront-service-slots",
        "storefront-service-book",
    ),
    "stay": (
        _stay,
        "stays",
        "storefront-unterkunft-unit",
        "storefront-unterkunft-unit",
        "storefront-unterkunft-book",
    ),
    "event": (_event, "events", "storefront-event", "", "storefront-event-book"),
    "combo": (_combo, "catalog", "storefront-combo", "storefront-combo", "storefront-combo-add"),
}

SELLABLE_KINDS = tuple(_KINDS)


def _reverse_or_empty(url_name: str, pk) -> str:
    """Реверс маршрута сущности: с pk, затем без (cart-add/combo-add — без арга);
    нет маршрута → '' (как detail_url — без падения)."""
    if not url_name:
        return ""
    try:
        return reverse(url_name, args=[pk])
    except NoReverseMatch:
        try:
            return reverse(url_name)
        except NoReverseMatch:
            return ""


def sellable_for(
    kind: str, obj, locale: str | None = None, *, buybox_ready: bool = False
) -> SellableEntity:
    """Нормализовать объект `kind` к `SellableEntity`.

    `purchase_mode`/`purchase_label` — из `archetypes` (без дублей). `detail_url`/
    `select_url`/`submit_url` реверсятся по маршрутам сущности (пусто при
    `NoReverseMatch`). `buybox_ready` — валидный выбор в ТЕКУЩЕМ запросе (UA3-2,
    задаёт вьюха: `quote.available` у stay / выбранный слот у service; дефолт False).
    `jobs` — НЕ sellable (индивидуальная смета, U-D); неизвестный kind → `ValueError`.
    """
    try:
        adapter, module, url_name, select_name, submit_name = _KINDS[kind]
    except KeyError:
        raise ValueError(f"unknown sellable kind: {kind!r} (known: {SELLABLE_KINDS})") from None
    f = adapter(obj, locale)
    return SellableEntity(
        kind=kind,
        pk=obj.pk,
        name=f["name"],
        description=f["description"],
        price_display=f["price_display"],
        image_url=f["image_url"],
        gallery=f["gallery"],
        purchase_mode=archetypes.purchase_mode(module),
        purchase_label=archetypes.purchase_label(module),
        detail_url=_reverse_or_empty(url_name, obj.pk),
        select_url=_reverse_or_empty(select_name, obj.pk),
        submit_url=_reverse_or_empty(submit_name, obj.pk),
        buybox_ready=buybox_ready,
    )
