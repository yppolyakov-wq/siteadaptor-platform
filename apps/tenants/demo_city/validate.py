"""DCC: валидатор спек и предсказатель категорий каталога города (план §6)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from apps.core import city_categories as cc
from apps.core import districts

from . import builder
from .spec import Biz

CITY_BOX = (51.12, 51.23, 6.98, 7.17)
_PHONE = re.compile(r"^\+49 212 555\d{4}$")
_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
FOOD_TYPES = {"bakery", "butcher", "grocery", "restaurant", "cafe", "catering"}
# 7 % НДС без LMIV — печатное (книги/альбомы), живые растения, корм для животных
# (Futtermittelrecht); всё остальное с 7 % считаем едой для людей.
_NON_FOOD_7 = (
    "buch",
    "bildband",
    "roman",
    "erstleser",
    "lesetagebuch",
    "bücher",
    "pflanze",
    "topf",
    "staude",
    "kräuterset",
    "futter",
    "kauknochen",
)


def _money(value: str) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def validate(biz: Biz, *, section: str = "") -> list[str]:
    """Список нарушений (пусто = ок). `section` — ключ раздела файла-реестра."""
    from apps.tenants.models import Tenant

    errs: list[str] = []
    types = {k for k, _l in Tenant.BUSINESS_TYPES}
    if biz.btype not in types:
        errs.append(f"тип {biz.btype!r} не в BUSINESS_TYPES")
    cat = cc.category(biz.category)
    if cat is None:
        errs.append(f"категория {biz.category!r} не в справочнике")
    elif section and cat.section != section:
        errs.append(f"категория {biz.category} из раздела {cat.section}, файл — {section}")
    if districts.normalize("Solingen", biz.district) != biz.district:
        errs.append(f"район {biz.district!r} не в реестре")
    if biz.street not in builder.STREETS.get(biz.district, ()):
        errs.append(f"улица {biz.street!r} не из вымышленного реестра района")
    try:
        lat, lng = float(biz.lat), float(biz.lng)
    except ValueError:
        errs.append("координаты не числа")
    else:
        lo, hi, wlo, whi = CITY_BOX
        if not (lo <= lat <= hi and wlo <= lng <= whi):
            errs.append("координаты вне Золингена")
        box = builder.DISTRICT_BOX.get(biz.district)
        if box and not (box[0] <= lat <= box[1] and box[2] <= lng <= box[3]):
            errs.append(f"координаты вне прямоугольника района {biz.district}")
    if not _PHONE.match(biz.phone):
        errs.append(f"телефон {biz.phone!r} не из вымышленного диапазона")
    if not _HOST.match(builder.subdomain_for(biz.key)):
        errs.append("поддомен не валиден")
    if biz.hours not in builder.HOURS:
        errs.append(f"пресет часов {biz.hours!r} неизвестен")
    for key in biz.usp:
        if key not in builder.USP:
            errs.append(f"USP {key!r} неизвестен")
    if not biz.label or not biz.tagline or not biz.about:
        errs.append("пустые label/tagline/about")
    if not biz.hero_photo:
        errs.append("нет hero_photo")
    sec = cat.section if cat else ""
    allowed = set(cc.tags_for(biz.category)) if cat else set()
    for shelf in biz.shelves:
        scat = cc.category(shelf.city_category)
        if scat is None:
            errs.append(f"полка {shelf.slug}: категория {shelf.city_category!r} неизвестна")
        if not shelf.items:
            errs.append(f"полка {shelf.slug} пуста")
        for it in shelf.items:
            price = _money(it.price)
            if price is None or price <= 0:
                errs.append(f"{it.name}: цена {it.price!r}")
            if not it.photo:
                errs.append(f"{it.name}: нет фото-ключа")
            food = biz.btype in FOOD_TYPES or (
                it.vat == "7.00" and not any(w in it.name.lower() for w in _NON_FOOD_7)
            )
            if food and not it.allergens and not it.ingredients:
                errs.append(f"{it.name}: еда без аллергенов/состава (LMIV)")
            if it.unit and not it.content:
                errs.append(f"{it.name}: unit без content (PAngV)")
    for o in biz.offers:
        p, w = _money(o.price) if o.price else None, _money(o.was) if o.was else None
        if o.price and (p is None or p <= 0):
            errs.append(f"акция {o.title}: цена {o.price!r}")
        if w is not None and (p is None or w <= p):
            errs.append(f"акция {o.title}: compare_at {o.was} не выше цены (UWG)")
        if w is not None and o.ends == "none":
            errs.append(f"акция {o.title}: бессрочная акция со Streichpreis (UWG)")
        if o.ends not in ("today", "week", "none") and not re.match(r"^\d+d$", o.ends):
            errs.append(f"акция {o.title}: ends {o.ends!r}")
        if o.city_category and cc.category(o.city_category) is None:
            errs.append(f"акция {o.title}: категория {o.city_category!r}")
        bad = set(o.tags) - set(cc.tags_for(o.city_category or biz.category))
        if bad:
            errs.append(f"акция {o.title}: признаки {sorted(bad)} не из раздела")
        if o.response and o.response not in ("show", "coupon", "reserve", "inquire"):
            errs.append(f"акция {o.title}: response {o.response!r}")
    for s in biz.services:
        if _money(s.price) is None or s.minutes <= 0:
            errs.append(f"услуга {s.name}: цена/длительность")
    for e in biz.events:
        if not (1 <= e.in_days <= 90):
            errs.append(f"событие {e.title}: in_days {e.in_days} вне 1..90")
        if e.theme and e.theme not in cc.BY_EVENT_THEME:
            errs.append(f"событие {e.title}: тема {e.theme!r} неизвестна")
    if biz.profile == "A":
        if biz.shelves or biz.services or biz.rooms or biz.events:
            errs.append("профиль A — без полок/услуг/номеров/событий")
        if not (4 <= len(biz.offers) <= 6):
            errs.append("профиль A — 4–6 акций")
    elif biz.profile == "K":
        n = sum(len(sh.items) for sh in biz.shelves)
        if n and n < 3:
            errs.append("профиль K — минимум 3 позиции на полках")
        if not (biz.shelves or biz.services or biz.rooms or biz.events or biz.anfrage):
            errs.append("профиль K — нет наполнения")
    else:
        errs.append(f"профиль {biz.profile!r}")
    _ = (sec, allowed)
    return errs


def predicted_categories(biz: Biz) -> set[str]:
    """Категории, которые листинги кита получат в каталоге города (правила
    aggregator.tasks._city_fields): карточка бизнеса и услуги — категория бизнеса,
    товар — категория полки, номер — hotels/ferienwohnungen, событие — по теме,
    акция — своя → товара → бизнеса."""
    out = {biz.category}
    for shelf in biz.shelves:
        out.add(shelf.city_category)
    if biz.rooms:
        out.add(biz.category if biz.category in ("hotels", "ferienwohnungen") else "hotels")
    for e in biz.events:
        out.add(cc.BY_EVENT_THEME.get(e.theme, "events") if e.theme else "events")
    for o in biz.offers:
        if o.city_category:
            out.add(o.city_category)
        elif o.item:
            for shelf in biz.shelves:
                if any(it.name == o.item for it in shelf.items):
                    out.add(shelf.city_category)
    return out
