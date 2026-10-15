"""DCC: компактная спека демо-бизнеса города (план docs/demo-city-coverage-plan-2026-10-15.md §1.3).

Спека — данные (frozen dataclass'ы), генератор `builder.build_kit` превращает её в обычный
`DemoKit`. Один бизнес описывается 20–40 строками вместо 80–120 у рукописного кита.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    """Товар полки. `photo` — ключ фонда static/demo/photos (или кортеж ключей)."""

    name: str
    price: str
    desc: str
    photo: str | tuple[str, ...] = ""
    diets: tuple[str, ...] = ()
    allergens: tuple[str, ...] = ()
    badge: str = ""
    unit: str = ""  # Grundpreis (PAngV): "kg" | "l" | "100g" … вместе с content
    content: str | None = None
    vat: str = ""  # "" = 19 %; еда — "7.00"
    origin: str = ""
    stock: int | None = None
    sku: str = ""
    ingredients: str = ""


@dataclass(frozen=True)
class Shelf:
    """Категория кита = одна категория справочника города."""

    name: str
    slug: str
    city_category: str
    items: tuple[Item, ...] = ()


@dataclass(frozen=True)
class Svc:
    """Услуга (модуль booking)."""

    name: str
    minutes: int
    price: str
    desc: str = ""
    photo: str = ""


@dataclass(frozen=True)
class Offer:
    """Акция. `ends`: today | week (повторяется еженедельно) | 14d | none (бессрочно).
    `response` — отклик T-8.2 ("" = по умолчанию, show/coupon/reserve/inquire).
    `item` — цель по ИМЕНИ товара (STU-18h), не по индексу."""

    title: str
    desc: str
    price: str = ""
    was: str = ""
    ends: str = "week"
    response: str = ""
    photo: str = ""
    group: str = ""
    style: str = ""
    city_category: str = ""
    tags: tuple[str, ...] = ()
    item: str = ""
    percent: int = 0


@dataclass(frozen=True)
class Ev:
    """Событие (модуль events). `theme` → категория каталога города по BY_EVENT_THEME."""

    title: str
    in_days: int
    hour: int
    price: str
    capacity: int
    desc: str = ""
    photo: str = ""
    theme: str = ""
    duration_hours: int = 2


@dataclass(frozen=True)
class Room:
    """Номер/юнит (модуль stays)."""

    name: str
    kind: str
    qty: int
    price: str
    guests: int
    desc: str = ""
    photos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Biz:
    key: str  # "sg_trattoria_lumetto"
    label: str  # название (не переводится)
    btype: str  # Tenant.BUSINESS_TYPES
    category: str  # Tenant.city_category
    district: str  # slug apps/core/districts
    street: str  # ВЫМЫШЛЕННАЯ улица из builder.STREETS[district]
    house: str
    lat: str
    lng: str
    phone: str
    profile: str = "K"  # K — компактный (каталог/услуги в городе) | A — «Nur Aktionen»
    accent: str = "#334155"
    hero_photo: str = ""
    tagline: str = ""
    about: str = ""
    hours: str = "laden"  # ключ пресета builder.HOURS
    usp: tuple[str, ...] = ()  # ключи builder.USP
    shelves: tuple[Shelf, ...] = ()
    services: tuple[Svc, ...] = ()
    events: tuple[Ev, ...] = ()
    rooms: tuple[Room, ...] = ()
    offers: tuple[Offer, ...] = ()
    anfrage: tuple[str, ...] = ()  # поля формы заявки AF-1 → модуль jobs
    event_types: tuple[str, ...] = ()
    delivery_plz: tuple[str, ...] = ()  # lieferservice
    whatsapp: str = ""
    primary: str = ""  # явный главный модуль (пусто = по содержимому)
    extra: dict = field(default_factory=dict)  # редкие поля DemoKit как есть
