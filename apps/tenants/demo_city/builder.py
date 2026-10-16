"""DCC: генератор `DemoKit` из компактной спеки `Biz` (план §1.4).

Библиотеки общих строк (часы, USP) переводятся один раз; названия заведений не
переводятся вовсе. Поддомен `sg-<…>` явно помечает демо (гейт demo_switch по слагам).
"""

from __future__ import annotations

from decimal import Decimal

from apps.core import districts

from .spec import Biz, Ev, Offer

ORIGIN = "city:solingen"
CITY = "Solingen"

# --- пресеты часов работы: ключ → {weekday: (от, до)} -------------------------------------
_WD5 = range(5)


def _hours(weekdays, saturday=None, sunday=None, days=_WD5):
    out = {d: weekdays for d in days}
    if saturday:
        out[5] = saturday
    if sunday:
        out[6] = sunday
    return out


HOURS: dict[str, dict[int, tuple[str, str]]] = {
    "laden": _hours(("09:30", "18:30"), ("10:00", "14:00")),
    "lebensmittel": _hours(("08:00", "19:00"), ("08:00", "16:00")),
    "baeckerei": _hours(("06:30", "18:00"), ("06:30", "13:00"), ("08:00", "11:00")),
    "gastro": _hours(("11:30", "22:00"), ("12:00", "23:00"), ("12:00", "21:00")),
    "cafe": _hours(("08:00", "18:00"), ("09:00", "18:00"), ("10:00", "17:00")),
    "praxis": _hours(("08:00", "18:00")),
    "handwerk": _hours(("07:30", "16:30")),
    "studio": _hours(("09:00", "20:00"), ("09:00", "15:00")),
    "kultur": _hours(("14:00", "22:00"), ("14:00", "23:00"), ("14:00", "22:00")),
    "hotel": _hours(("07:00", "22:00"), ("07:00", "22:00"), ("07:00", "22:00")),
    "freizeit": _hours(("10:00", "21:00"), ("09:00", "21:00"), ("09:00", "19:00")),
}

_DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _fmt(t: str) -> str:
    h, m = t.split(":")
    return f"{int(h)}:{m}"


def hours_text(hours: dict) -> str:
    """«Mo–Fr 9:30–18:30 · Sa 10:00–14:00» — один формат у всех китов города."""
    groups: list[tuple[int, int, tuple[str, str]]] = []
    for day in range(7):
        span = hours.get(day)
        if span is None:
            continue
        if groups and groups[-1][1] == day - 1 and groups[-1][2] == span:
            groups[-1] = (groups[-1][0], day, span)
        else:
            groups.append((day, day, span))
    parts = []
    for a, b, (start, end) in groups:
        label = _DAYS[a] if a == b else f"{_DAYS[a]}–{_DAYS[b]}"
        parts.append(f"{label} {_fmt(start)}–{_fmt(end)}")
    return " · ".join(parts)


# --- библиотека USP: ключ → (иконка siteconfig.USP_ICONS, текст) ---------------------------
USP: dict[str, tuple[str, str]] = {
    "regional": ("local", "Aus der Region"),
    "hausgemacht": ("quality", "Hausgemacht"),
    "familie": ("support", "Familienbetrieb"),
    "terrasse": ("check", "Terrasse im Sommer"),
    "meister": ("meister", "Meisterbetrieb"),
    "beratung": ("support", "Persönliche Beratung"),
    "termin": ("clock", "Termine online buchen"),
    "lieferung": ("shipping", "Lieferung in Solingen"),
    "abholung": ("shipping", "Click & Collect"),
    "bio": ("bio", "Bio-Qualität"),
    "vegan": ("bio", "Vegane Auswahl"),
    "garantie": ("quality", "Garantie auf alle Arbeiten"),
    "parken": ("local", "Parkplätze vor der Tür"),
    "barrierefrei": ("check", "Barrierefrei"),
    "kinder": ("support", "Kinderfreundlich"),
    "hunde": ("check", "Hunde willkommen"),
    "zahlung": ("payment", "Karte & bar"),
    "reparatur": ("meister", "Reparatur statt Neukauf"),
    "nachhaltig": ("bio", "Nachhaltig"),
    "schnell": ("clock", "Schnelle Termine"),
    "handarbeit": ("quality", "Handarbeit aus Solingen"),
    "geschenk": ("check", "Geschenkverpackung gratis"),
    "service": ("support", "Service vor Ort"),
    "probe": ("check", "Probestunde gratis"),
    "ruhe": ("check", "Ruhige Lage"),
    "fruehstueck": ("check", "Frühstück inklusive"),
    "fahrrad": ("local", "Fahrradfreundlich"),
    "wlan": ("check", "Kostenloses WLAN"),
    "qualitaet": ("quality", "Geprüfte Qualität"),
    "versand": ("shipping", "Versand deutschlandweit"),
}

# --- вымышленные улицы по районам (реальных адресов демо не носят) -------------------------
STREETS: dict[str, tuple[str, ...]] = {
    "mitte": ("Schleifergasse", "Am Klingenhof", "Scherenweg", "Lindenplatz", "Messerstraße"),
    "graefrath": ("Klosterpfad", "Am Fachwerk", "Brunnenweg", "Zinnstraße", "Tuchmacherweg"),
    "wald": ("Walder Höhe", "Eichenallee", "Am Weiher", "Heidestraße", "Fuchsweg"),
    "burg-hoehscheid": ("Schlossblick", "Wupperufer", "Burgweg", "Am Hang", "Mühlensteig"),
    "ohligs-aufderhoehe-merscheid": (
        "Bahnhofsgasse",
        "Am Markt",
        "Merscheider Weg",
        "Lerchenstraße",
        "Höhenblick",
    ),
}

# Прямоугольники районов (lat_min, lat_max, lng_min, lng_max) — из координат существующих
# китов и карты; проверяются валидатором.
DISTRICT_BOX: dict[str, tuple[float, float, float, float]] = {
    "graefrath": (51.190, 51.230, 7.040, 7.105),
    "wald": (51.165, 51.200, 7.010, 7.075),
    "mitte": (51.155, 51.182, 7.055, 7.105),
    "burg-hoehscheid": (51.125, 51.168, 7.055, 7.175),
    "ohligs-aufderhoehe-merscheid": (51.125, 51.190, 6.975, 7.045),
}

_MODULE_LABEL_ORDER = ("catalog", "booking", "stays", "events", "jobs", "promotions")


def plz_for(district: str) -> str:
    for d in districts.districts_for(CITY):
        if d.slug == district and d.plz:
            return d.plz[0]
    return ""


def subdomain_for(key: str) -> str:
    return "sg-" + key.removeprefix("sg_").replace("_", "-")


# PAngV-единица в спеке пишется «как на ценнике» («100g», «100ml»), а
# `Product.unit` хранит ТОЛЬКО g/kg/ml/l (varchar(4), choices) и количество в
# этой единице. Поэтому «100g» × content 0.6 → unit "g", content 60.
_UNIT_SCALE = {
    "100g": ("g", 100),
    "100ml": ("ml", 100),
    "g": ("g", 1),
    "kg": ("kg", 1),
    "ml": ("ml", 1),
    "l": ("l", 1),
    "": ("", 1),
}


def product_unit(unit: str, content: str) -> tuple[str, str]:
    """Нормализует пару (unit, content) спеки к полям модели Product."""
    base, scale = _UNIT_SCALE[unit]
    if not content or scale == 1:
        return base, content
    qty = Decimal(content) * scale
    return base, str(qty.quantize(Decimal(1)) if qty == qty.to_integral() else qty.normalize())


def _sku(biz_key: str, shelf_i: int, item_i: int) -> str:
    stem = "".join(ch for ch in biz_key.removeprefix("sg_").upper() if ch.isalnum())[:4]
    return f"{stem}-{shelf_i + 1}{item_i + 1:02d}"


def _offer_spec(o: Offer) -> dict:
    spec: dict = {"title": o.title, "desc": o.desc}
    if o.price:
        spec["new_price"] = o.price
    if o.was:
        spec["compare_at"] = o.was
    if o.percent:
        spec["percent"] = o.percent
    if o.ends == "today":
        spec["ends_today"] = True
    elif o.ends == "week":
        spec["ends_in_days"] = 7
        spec["recurrence"] = "weekly"
    elif o.ends == "none":
        spec["no_end"] = True
    else:
        spec["ends_in_days"] = int(o.ends.rstrip("d") or 14)
    if o.response:
        spec["response"] = o.response
    if o.photo:
        spec["image"] = o.photo
    if o.group:
        spec["group"] = o.group
    if o.style:
        spec["discount_style"] = o.style
    if o.city_category:
        spec["city_category"] = o.city_category
    if o.tags:
        spec["city_tags"] = list(o.tags)
    if o.item:
        spec["product"] = o.item
    return spec


def modules_of(biz: Biz) -> list[str]:
    """Модули сверх пресета типа, которые кит включает (по наполнению)."""
    out: list[str] = []
    if biz.services:
        out.append("booking")
    if biz.rooms:
        out.append("stays")
    if biz.events:
        out.append("events")
    if biz.anfrage:
        out.append("jobs")
    if biz.delivery_plz:
        out.append("orders")
    if biz.offers:
        out.append("promotions")
    return out


def primary_of(biz: Biz) -> str:
    if biz.primary:
        return biz.primary
    if biz.profile == "A":
        return "promotions"
    for mod, present in (
        ("catalog", bool(biz.shelves)),
        ("booking", bool(biz.services)),
        ("stays", bool(biz.rooms)),
        ("events", bool(biz.events)),
        ("jobs", bool(biz.anfrage)),
    ):
        if present:
            return mod
    return "promotions"


_PRIMARY_URL = {
    "catalog": ("Zum Sortiment", "/sortiment/"),
    "booking": ("Termin buchen", "/termin/"),
    "stays": ("Zimmer ansehen", "/unterkunft/"),
    "events": ("Zu den Terminen", "/veranstaltung/"),
    "jobs": ("Anfrage senden", "/anfrage/"),
    "promotions": ("Zu den Angeboten", "/aktionen/"),
}


_SECTION_LIMITS = {"products": 8, "promotions": 9, "events": 6, "categories": 30}
_COLS_PREFERENCE = (4, 3, 2, 5, 6)


def _full_row_preset(n: int, default_cols: int) -> str | None:
    """DL-11: пресет колонок, при котором n карточек заполняют ряды десктопа без
    остатка (или помещаются в один ряд). None — делителя нет (простое n > 6):
    это дефект ДАННЫХ спеки, его ловит замок test_demo_kits_rows_full_on_desktop."""
    if n <= 1:
        return None
    if n < default_cols or n % default_cols == 0:
        return None  # дефолт секции уже даёт полные ряды
    for cols in _COLS_PREFERENCE:
        if n % cols == 0:
            return f"cols{cols}"
    return f"cols{n}" if n <= 6 else None


def _snap_in_days(e: Ev) -> int:
    """Событие «am Sonntag»/«jeden Mittwoch»: сидер считает дату как now + in_days, поэтому
    день недели в тексте совпадал бы только в удачный день сидинга. Сдвигаем к ближайшему
    дню недели ≥ in_days (считается при сборке кита = при сидинге)."""
    if e.weekday is None:
        return e.in_days
    from django.utils import timezone

    today = timezone.localdate().weekday()
    shift = (e.weekday - (today + e.in_days)) % 7
    return e.in_days + shift


def section_layouts_for(biz: Biz) -> dict:
    """Раскладки секций главной под число элементов спеки (полные ряды, DL-11)."""
    from apps.tenants import siteconfig

    counts = {
        "categories": len(biz.shelves),
        "products": sum(len(sh.items) for sh in biz.shelves),
        "services": len(biz.services),
        "promotions": len(biz.offers),
        "events": len(biz.events),
        "stay_rooms": len(biz.rooms),
    }
    out: dict = {}
    for key, n in counts.items():
        n = min(n, _SECTION_LIMITS.get(key, n))
        default = siteconfig.GRID_SECTION_DEFAULTS.get(key, {"preset": "cols3"})
        default_cols = siteconfig.LAYOUT_PRESETS[default["preset"]]["cols"]
        preset = _full_row_preset(n, default_cols)
        if preset:
            out[key] = {"preset": preset}
    return out


def build_kit(biz: Biz):
    """Спека → DemoKit (общие поля — из библиотек; профиль A = «Nur Aktionen»)."""
    from apps.tenants import demo_kits as dk
    from apps.tenants.demo_kits import DemoKit, _p

    hours = HOURS[biz.hours]
    address = f"{biz.street} {biz.house}, {plz_for(biz.district)} {CITY}"
    usp = [USP[k] for k in biz.usp if k in USP]
    offers = [_offer_spec(o) for o in biz.offers]
    primary = primary_of(biz)
    button, url = _PRIMARY_URL[primary]
    first_offer = biz.offers[0] if biz.offers else None
    heroes = dk._solingen_heroes(
        biz.hero_photo,
        biz.label,
        biz.tagline,
        (first_offer.photo if first_offer and first_offer.photo else biz.hero_photo),
        first_offer.title if first_offer else biz.label,
        first_offer.desc if first_offer else biz.tagline,
        button,
        url,
    )
    common: dict = {
        "key": biz.key,
        "label": biz.label,
        "business_type": biz.btype,
        "accent": biz.accent,
        "hero_image_kw": biz.hero_photo,
        "hero_title": biz.label,
        "hero_text": biz.tagline,
        "about_title": "Über uns",
        "about_text": biz.about,
        "address": address,
        "phone": biz.phone,
        "lat": biz.lat,
        "lng": biz.lng,
        "district": biz.district,
        "business_city_category": biz.category,
        "opening_hours": hours,
        "opening_hours_text": hours_text(hours),
        "usp": usp,
        "subdomain": subdomain_for(biz.key),
        "origin": ORIGIN,
        "whatsapp_number": biz.whatsapp,
        "promotions_spec": offers,
        "heroes": heroes,
    }
    if biz.profile == "A":
        lite = {**common, **dk._LITE_COMMON, "menus": dk._lite_menus()}
        return DemoKit(**{**lite, "section_layouts": section_layouts_for(biz), **biz.extra})
    categories = []
    city_categories: dict[str, str] = {}
    for si, shelf in enumerate(biz.shelves):
        items = []
        for ii, it in enumerate(shelf.items):
            photo = it.photo if isinstance(it.photo, str) else ",".join(it.photo)
            unit, content = product_unit(it.unit, it.content)
            items.append(
                _p(
                    it.name,
                    it.price,
                    it.desc,
                    photo,
                    allergens=list(it.allergens),
                    diets=list(it.diets),
                    badge=it.badge,
                    unit=unit,
                    content=content,
                    stock=it.stock,
                    sku=it.sku or _sku(biz.key, si, ii),
                    vat=it.vat,
                    origin=it.origin,
                    ingredients=it.ingredients,
                )
            )
        categories.append((shelf.name, shelf.slug, items))
        city_categories[shelf.slug] = shelf.city_category
    modules = modules_of(biz)
    menu_targets = [
        m
        for m in _MODULE_LABEL_ORDER
        if (m == "catalog" and biz.shelves)
        or (m == "promotions" and biz.offers)
        or (m in modules and m != "orders")
    ]
    kit_kwargs: dict = dict(
        categories=categories,
        city_categories=city_categories,
        enable_modules=modules,
        primary_module=primary,
        services=[(s.name, s.minutes, s.price, s.desc, s.photo) for s in biz.services],
        events=[
            {
                "title": e.title,
                "in_days": _snap_in_days(e),
                "hour": e.hour,
                "duration_hours": e.duration_hours,
                "capacity": e.capacity,
                "price": e.price,
                "description": e.desc,
                "photos": [e.photo] if e.photo else [],
                "category": e.theme,
                "city": CITY,
            }
            for e in biz.events
        ],
        stay_units=[
            {
                "name": r.name,
                "type": r.kind,
                "qty": r.qty,
                "price": r.price,
                "guests": r.guests,
                "description": r.desc,
                "photos": list(r.photos),
            }
            for r in biz.rooms
        ],
        menus=dk._solingen_menus(*menu_targets),
        enable_categories_section=len(biz.shelves) >= 2,
        section_layouts=section_layouts_for(biz),
    )
    kit_kwargs = {**common, **dk._SOLINGEN_COMMON, **kit_kwargs, "promo_count": len(offers) or 2}
    if biz.anfrage:
        kit_kwargs["anfrage_form"] = {
            "fields": list(biz.anfrage),
            "event_types": list(biz.event_types),
        }
    if biz.delivery_plz:
        kit_kwargs["delivery"] = {
            "enabled": True,
            "fee_cents": 290,
            "free_cents": 3000,
            "min_cents": 1500,
            "area": f"Lieferung in {CITY} ({', '.join(biz.delivery_plz)}).",
            "zones": [
                {"plz": plz, "fee_cents": 290, "free_cents": 3000, "min_cents": 1500}
                for plz in biz.delivery_plz
            ],
        }
    kit_kwargs.update(biz.extra)
    return DemoKit(**kit_kwargs)


def city_kits(businesses) -> dict:
    return {biz.key: build_kit(biz) for biz in businesses}
