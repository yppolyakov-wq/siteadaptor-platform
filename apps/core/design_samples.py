"""FB-29.8b: товары-примеры для предпросмотра дизайна на пустом магазине.

Владелец выбирает дизайн раньше, чем заводит товары — без карточек предпросмотр пуст
и дизайн не оценить. В предпросмотре дизайна (`?preview=1` вместе с `look` или
`bundle`) пустой список товаров показывает примеры: объекты `Product` в памяти, в базу
ничего не пишется, на живом сайте их нет.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

#: (название, цена, ключ демо-фото)
_SAMPLES = (
    ("Beispielprodukt 1", "9.90", "tea"),
    ("Beispielprodukt 2", "14.50", "coffee"),
    ("Beispielprodukt 3", "24.00", "chocolate"),
    ("Beispielprodukt 4", "6.80", "bakery"),
)


def wanted(request) -> bool:
    """Идёт ли предпросмотр ДИЗАЙНА (а не обычное превью страницы)."""
    get = getattr(request, "GET", None) or {}
    return get.get("preview") == "1" and bool(get.get("look") or get.get("bundle"))


def products() -> list:
    """Четыре товара-примера: несохранённые `Product`, ссылки никуда не ведут."""
    from apps.catalog.models import Product
    from apps.tenants.demo_images import demo_image_url

    out = []
    for i, (name, price, keyword) in enumerate(_SAMPLES):
        item = Product(
            pk=uuid.UUID(int=i + 1),
            name={"de": name, "en": name},
            base_price=Decimal(price),
            images=[
                {
                    "id": f"sample-{i}",
                    "url": demo_image_url(keyword, w=800, h=800, lock=700 + i),
                    "alt": name,
                    "is_primary": True,
                }
            ],
        )
        item.is_sample = True
        item.get_absolute_url = lambda: "#"
        out.append(item)
    return out


def for_empty_shop(request) -> list:
    """Примеры — только в предпросмотре дизайна и только пока своих товаров нет."""
    if not wanted(request):
        return []
    from apps.catalog.models import Product

    if Product.objects.filter(is_active=True).exists():
        return []
    return products()


# ───────── примеры услуг, номеров и событий (тот же принцип: в памяти, без записи) ─────────


def _photo(keyword: str, lock: int, alt: str) -> list:
    from apps.tenants.demo_images import demo_image_url

    return [
        {
            "id": f"sample-{lock}",
            "url": demo_image_url(keyword, w=800, h=600, lock=lock),
            "alt": alt,
            "is_primary": True,
        }
    ]


def services() -> list:
    from apps.booking.models import Service

    out = []
    for i, (name, minutes, cents) in enumerate(
        (
            ("Beispielleistung 1", 30, 2500),
            ("Beispielleistung 2", 60, 4900),
            ("Beispielleistung 3", 90, 7900),
        )
    ):
        item = Service(
            pk=uuid.UUID(int=101 + i), name=name, duration_minutes=minutes, price_cents=cents
        )
        item.is_sample = True
        out.append(item)
    return out


def stays() -> list:
    from apps.stays.models import StayUnit

    out = []
    for i, (name, cents, keyword) in enumerate(
        (
            ("Beispielzimmer 1", 8900, "bedroom"),
            ("Beispielzimmer 2", 11900, "hotel"),
            ("Beispielzimmer 3", 14900, "bedroom"),
        )
    ):
        item = StayUnit(pk=uuid.UUID(int=201 + i), name=name, price_cents=cents)
        item.images = _photo(keyword, 720 + i, name)
        item.is_sample = True
        out.append(item)
    return out


def events() -> list:
    import datetime

    from django.utils import timezone

    from apps.events.models import Event

    out = []
    for i, (title, days, cents) in enumerate(
        (
            ("Beispielveranstaltung 1", 14, 2900),
            ("Beispielveranstaltung 2", 28, 4500),
            ("Beispielveranstaltung 3", 42, 0),
        )
    ):
        item = Event(
            pk=uuid.UUID(int=301 + i),
            title=title,
            starts_at=timezone.now() + datetime.timedelta(days=days),
            status=Event.STATUS_PUBLISHED,
            price_cents=cents,
        )
        item.is_sample = True
        out.append(item)
    return out


_MAKERS = {
    "services": ("apps.booking.models.Service", services),
    "stay_rooms": ("apps.stays.models.StayUnit", stays),
    "events": ("apps.events.models.Event", events),
}


def for_empty_section(request, key: str) -> list:
    """Примеры для пустой секции главной `key` — только в предпросмотре дизайна и только
    пока своих записей этого вида нет. Сбой при сборке примера — без примеров."""
    import importlib
    import logging

    if key not in _MAKERS or not wanted(request):
        return []
    path, make = _MAKERS[key]
    module, _dot, name = path.rpartition(".")
    try:
        model = getattr(importlib.import_module(module), name)
        if model.objects.exists():
            return []
        return make()
    except Exception:  # noqa: BLE001 — предпросмотр важнее примеров
        logging.getLogger(__name__).exception("design samples: %s failed", key)
        return []
