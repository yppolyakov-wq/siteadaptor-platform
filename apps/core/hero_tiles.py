"""Первый экран «ловит направления» (фидбэк владельца 2026-07-30): плитки-входы
ВНУТРИ hero — посетитель сразу видит 2-4 задачи, ради которых он пришёл.

Данные-первым: набор плиток на архетип живёт ЗДЕСЬ, шаблон — один generic-цикл
(`sections/_hero_tiles.html`). Ветки bakery/butcher/mode/gastro/stays/services в
`sections/_hero_widget.html` остаются кастомными — у них своя вёрстка и замки;
генерик подключён `{% else %}`-веткой и самогейтится (пустой список = пусто).

Плитка: icon · label · sub · url (url_name) · query · gate.
  gate: "" — всегда; ключ модуля — только при активном модуле; "deal" — только
  при живой акции (иначе плитки нет).
  deal_sub=True — подподпись берётся из заголовка живой акции (если она есть).
  highlight=True — янтарная рамка (акцент «горячей» плитки).
"""

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

# widget → плитки в порядке показа. Гейты модулей проверяет `tiles_for`.
HERO_TILE_SETS = {
    # A3 Friseur/Kosmetik: главное действие — запись; продукты и подарочный
    # сертификат — вторичные корзины выручки.
    "friseur": [
        {
            "key": "termin",
            "icon": "🗓",
            "label": _("Termin buchen"),
            "sub": _("Freie Zeiten sofort sehen"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "key": "deals",
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
        {
            "key": "products",
            "icon": "🧴",
            "label": _("Pflegeprodukte"),
            "sub": _("Salonqualität für zu Hause"),
            "url": "storefront-products",
            "gate": "orders",
        },
        {
            "key": "gift",
            "icon": "🎁",
            "label": _("Geschenkgutschein"),
            "sub": _("Freude schenken"),
            "url": "storefront-gutschein",
            "gate": "gift",
        },
    ],
    # A9 Kfz-Werkstatt: термин и смета — две разные задачи клиента.
    "werkstatt": [
        {
            "key": "termin",
            "icon": "🔧",
            "label": _("Termin vereinbaren"),
            "sub": _("Inspektion, Reifen, Service"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "key": "anfrage",
            "icon": "📋",
            "label": _("Kostenvoranschlag"),
            "sub": _("Schaden beschreiben — Festpreis erhalten"),
            "url": "storefront-anfrage",
            "gate": "jobs",
        },
        {
            "key": "products",
            "icon": "🛞",
            "label": _("Teile & Zubehör"),
            "url": "storefront-products",
            "gate": "orders",
        },
        {
            "key": "deals",
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
    ],
    # A7 Handwerker: заявка первым; Rückruf — вход для тех, кто не пишет формы.
    "handwerker": [
        {
            "key": "anfrage",
            "icon": "📋",
            "label": _("Angebot anfordern"),
            "sub": _("Kostenlos & unverbindlich"),
            "url": "storefront-anfrage",
            "gate": "jobs",
        },
        {
            "key": "termin",
            "icon": "🗓",
            "label": _("Termin vereinbaren"),
            "sub": _("Beratung vor Ort"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "key": "rueckruf",
            "icon": "☎",
            "label": _("Rückruf anfordern"),
            "sub": _("Wir melden uns zurück"),
            "url": "storefront-rueckruf",
            # Аудит 2026-08-06: гейта не было, а вьюха требует модуль jobs
            # (`_require_jobs_active` → 404) — плитка вела в 404 при выключенном
            # модуле. GET там всё равно редиректит на /anfrage/, это нормально.
            "gate": "jobs",
        },
        {
            "key": "deals",
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
    ],
    # GK-1 Catering/Partyservice: заявка на событие первична (jobs-primary, поля
    # AF-1: дата/гости/тип), Speisekarte browse-only (catalog core, без гейта).
    "catering": [
        {
            "key": "anfrage",
            "icon": "📋",
            "label": _("Angebot anfordern"),
            "sub": _("Datum, Gäste & Wünsche — unverbindlich"),
            "url": "storefront-anfrage",
            "gate": "jobs",
        },
        {
            "key": "menu",
            "icon": "🍽",
            "label": _("Menüs & Pakete"),
            "sub": _("Unsere Speisekarte"),
            "url": "storefront-products",
            "gate": "",
        },
        {
            "key": "rueckruf",
            "icon": "☎",
            "label": _("Rückruf anfordern"),
            "sub": _("Wir melden uns zurück"),
            "url": "storefront-rueckruf",
            "gate": "jobs",
        },
        {
            "key": "deals",
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
    ],
    # A1 Hofladen/Retail: акция ловит первым, дальше каталог и предзаказ.
    "shop": [
        {
            "key": "deals",
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
        {
            "key": "sortiment",
            "icon": "🛍",
            "label": _("Sortiment ansehen"),
            "url": "storefront-products",
            "gate": "",
        },
        {
            "key": "preorder",
            "icon": "⏰",
            "label": _("Zur Wunschzeit vorbestellen"),
            "sub": _("Jetzt bestellen, ohne Warten abholen"),
            "url": "storefront-products",
            "gate": "orders",
        },
        {
            "key": "loyalty",
            "icon": "⭐",
            "label": _("Treuepunkte"),
            "sub": _("Bei jedem Einkauf sammeln"),
            "url": "storefront-loyalty",
            "gate": "loyalty",
        },
    ],
    # A8 Aktionsmarkt: акции — сам архетип, поэтому плитка БЕЗ гейта (sub
    # подтягивается из живой акции, если она есть).
    "aktionsmarkt": [
        {
            "key": "deals",
            "icon": "🔥",
            "label": _("Aktuelle Deals"),
            "url": "storefront-aktionen",
            # Аудит 2026-08-06: /aktionen/ гейтится модулем promotions (иначе 404).
            "gate": "promotions",
            "deal_sub": True,
            "highlight": True,
        },
        {
            "key": "sortiment",
            "icon": "🛍",
            "label": _("Sortiment ansehen"),
            "url": "storefront-products",
            "gate": "",
        },
        {
            "key": "loyalty",
            "icon": "⭐",
            "label": _("Treuepunkte"),
            "sub": _("Bei jedem Einkauf sammeln"),
            "url": "storefront-loyalty",
            "gate": "loyalty",
        },
        {
            "key": "newsletter",
            "icon": "🔔",
            "label": _("Deals per E-Mail"),
            "sub": _("Kein Angebot verpassen"),
            "url": "storefront-newsletter",
            "gate": "",
        },
    ],
    # A6 Touren: билет на публичную дату vs приватная группа — разные воронки.
    "touren": [
        {
            "key": "events",
            "icon": "🎟",
            "label": _("Touren & Termine"),
            "sub": _("Termine ansehen und Plätze sichern"),
            "url": "storefront-events",
            "gate": "events",
        },
        {
            "key": "private",
            "icon": "👥",
            "label": _("Private Führung"),
            "sub": _("Wunschtermin für Ihre Gruppe"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "key": "gift",
            "icon": "🎁",
            "label": _("Geschenkgutschein"),
            "sub": _("Freude schenken"),
            "url": "storefront-gutschein",
            "gate": "gift",
        },
        {
            "key": "deals",
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
    ],
    # A6/A5 Retreat: курс, ночёвка, отдельный сеанс и свободная заявка.
    "retreat": [
        {
            "key": "events",
            "icon": "🧘",
            "label": _("Retreats & Kurse"),
            "sub": _("Termine und freie Plätze"),
            "url": "storefront-events",
            "gate": "events",
        },
        {
            "key": "stays",
            "icon": "🛏",
            "label": _("Übernachtung"),
            "sub": _("Verfügbarkeit prüfen"),
            "url": "storefront-unterkunft",
            "gate": "stays",
        },
        {
            "key": "termin",
            "icon": "🗓",
            "label": _("Einzeltermin"),
            "sub": _("Massage, Beratung, Coaching"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "key": "anfrage",
            "icon": "✉",
            "label": _("Anfrage stellen"),
            "sub": _("Gruppen und Wunschtermine"),
            "url": "storefront-anfrage",
            "gate": "jobs",
        },
    ],
}

HERO_TILE_WIDGETS = tuple(HERO_TILE_SETS)


def _href(tile) -> str:
    """URL плитки; мёртвый url_name → "" (плитка выпадает — fail-safe, как
    `sellable_manage._reverse`: реестр не должен ронять главную)."""
    try:
        url = reverse(tile["url"])
    except NoReverseMatch:
        return ""
    return f"{url}{tile.get('query', '')}"


def needs_deal(widget: str) -> bool:
    """Нужен ли этому набору запрос живой акции (иначе не платим лишним SQL на
    главной у архетипов без «горячей» плитки)."""
    return any(
        t.get("gate") == "deal" or t.get("deal_sub") for t in HERO_TILE_SETS.get(widget or "", ())
    )


def _gift_reachable(tenant) -> bool:
    """Страница `/gutschein/` требует НЕ ТОЛЬКО модуль gift, но и настроенную
    онлайн-оплату (`gift_purchase_active`) — иначе отдаёт 404. Гейт плитки был
    только по модулю, поэтому на первом экране висел вход в 404 (аудит
    2026-08-06). Ошибки гасим: первый экран важнее плитки."""
    try:
        from apps.loyalty.public_views import gift_purchase_active

        return gift_purchase_active(tenant)
    except Exception:  # noqa: BLE001
        return False


# Гейты, которым мало «модуль активен»: страница за плиткой ставит доп. условие.
_EXTRA_GATES = {"gift": _gift_reachable}


def tiles_for(widget: str, tenant, deal=None, hidden=(), labels=None) -> list[dict]:
    """Плитки первого экрана для архетипа. Неизвестный widget → [] (шаблон
    ничего не рендерит). `deal` — живая акция (`siteui.deal_of_day`). FB-33 M3-5b:
    `hidden` — ключи скрытых плиток, `labels` — свои подписи {ключ: текст}."""
    spec = HERO_TILE_SETS.get(widget or "")
    if not spec:
        return []
    from apps.core import modules, storefront_profile

    aktionen = storefront_profile.is_aktionen(tenant)
    labels = labels if isinstance(labels, dict) else {}
    out = []
    for tile in spec:
        if tile.get("key") in (hidden or ()):
            continue
        # T-8.1: «Nur Aktionen» — плитки в каталог/корзину не показываем.
        if aktionen and tile.get("url") in storefront_profile.CATALOG_URL_NAMES:
            continue
        gate = tile.get("gate", "")
        if gate == "deal":
            # Плитка ведёт на /aktionen/, а страница гейтится модулем promotions:
            # живая акция в БД сама по себе не гарантирует, что модуль включён
            # (аудит 2026-08-06 — иначе клик по «горячей» плитке давал 404).
            if deal is None or not modules.is_module_active(tenant, "promotions"):
                continue
        elif gate and not modules.is_module_active(tenant, gate):
            continue
        elif gate and gate in _EXTRA_GATES and not _EXTRA_GATES[gate](tenant):
            continue
        href = _href(tile)
        if not href:
            continue
        sub = tile.get("sub", "")
        if tile.get("deal_sub") and deal is not None:
            sub = getattr(deal, "title_text", "") or sub
        out.append(
            {
                "icon": tile["icon"],
                "label": labels.get(tile.get("key")) or tile["label"],
                "sub": sub,
                "href": href,
                "highlight": bool(tile.get("highlight")),
                "deal_sub": bool(tile.get("deal_sub")) and deal is not None,
            }
        )
    return out


# ─────────── FB-33 M2c: «Быстрые ссылки» — отдельный блок `quick_links` ───────────
#: Наборы-ССЫЛКИ, которые может показать блок: кастомные ветки `_hero_widget.html` и
#: генерик-наборы реестра. `stays` (форма дат) и `services` (топ услуг) — не ссылки: при
#: переносе они становятся секцией «Suche» и списком услуг (решение владельца, план M2c).
QUICK_LINK_SETS = ("gastro", "bakery", "butcher", "mode", *HERO_TILE_WIDGETS)

#: Подпись набора в окне блока — тип бизнеса, для которого он собран (переведённые
#: подписи `Tenant.BUSINESS_TYPES`, новых строк перевода нет).
QUICK_LINK_LABELS = {
    "gastro": _("Restaurant"),
    "bakery": _("Bakery / Bäckerei"),
    "butcher": _("Butcher / Metzgerei"),
    "mode": _("Clothing / Bekleidung"),
    "friseur": _("Friseur / Salon"),
    "werkstatt": _("Werkstatt / KFZ"),
    "handwerker": _("Handwerker"),
    "catering": _("Catering / Partyservice"),
    "shop": _("Online-Shop"),
    "aktionsmarkt": _("Aktionen"),
    "touren": _("Tours"),
    "retreat": _("Veranstalter / Events"),
}


# ─────────── FB-33 M3-5b: плашки в окне блока — скрыть и переименовать ───────────
#: подсказка у плашки в окне: когда она видна (гейт) или куда ведёт
_GATE_HINTS = {
    "deal": _("nur wenn Deals laufen"),
    "promotions": _("nur wenn Deals laufen"),
    "booking": _("nur mit Terminbuchung"),
    "orders": _("nur mit Bestellungen"),
    "jobs": _("nur mit Anfragen"),
    "gift": _("nur mit Gutscheinen"),
    "loyalty": _("nur mit Bonusprogramm"),
    "events": _("nur mit Veranstaltungen"),
    "stays": _("nur mit Übernachtungen"),
}
_URL_HINTS = {
    "storefront-products": _("→ Katalog"),
    "storefront-newsletter": _("→ Newsletter"),
}


def _hint(gate: str, url: str = ""):
    return _GATE_HINTS.get(gate) or _URL_HINTS.get(url, "")


#: Плашки каждого набора в порядке показа: (ключ, стандартная подпись, подсказка). Рукописные
#: наборы (`_hero_widget.html`) — здесь же, ключи совпадают с `ql_hidden`/`ql_labels` шаблона.
QUICK_LINK_TILES: dict[str, tuple] = {
    "gastro": (
        ("reserve", _("Tisch reservieren"), _hint("booking")),
        ("menu", _("Speisekarte"), _hint("", "storefront-products")),
        ("deal", _("Angebot des Tages"), _hint("deal")),
    ),
    "bakery": (
        ("deal", _("Aktionen & Angebote"), _hint("deal")),
        ("sortiment", _("Sortiment ansehen"), _hint("", "storefront-products")),
        ("preorder", _("Zur Wunschzeit vorbestellen"), _hint("orders")),
        ("party", _("Partyservice anfragen"), _hint("jobs")),
    ),
    "mode": (
        ("deal", _("Sale"), _hint("deal")),
        ("sortiment", _("Sortiment ansehen"), _hint("", "storefront-products")),
        ("new", _("Neuheiten"), _hint("", "storefront-products")),
        ("gift", _("Geschenkgutschein"), _hint("gift")),
    ),
    **{
        name: tuple(
            (t["key"], t["label"], _hint(t.get("gate", ""), t.get("url", ""))) for t in tiles
        )
        for name, tiles in HERO_TILE_SETS.items()
    },
}
QUICK_LINK_TILES["butcher"] = QUICK_LINK_TILES["bakery"]

#: потолок своей подписи плашки (на вводе — `maxlength`, в данных — обрезка)
LABEL_MAX = 40


def tile_keys(link_set: str) -> tuple[str, ...]:
    return tuple(key for key, _label, _hint in QUICK_LINK_TILES.get(link_set or "", ()))


def _standard(label) -> str:
    """Стандартная подпись на основном языке (своя, равная ей, не хранится)."""
    from django.conf import settings
    from django.utils import translation

    with translation.override(settings.LANGUAGE_CODE):
        return str(label)


def _all_languages(label) -> set[str]:
    from django.conf import settings
    from django.utils import translation

    out = set()
    for code, _name in settings.LANGUAGES:
        with translation.override(code):
            out.add(str(label))
    return out


def clean_data(d: dict) -> dict:
    """Данные блока «Schnellzugriff»: {"set"} + скрытые плашки и свои подписи — только ключи
    своего набора; пустая или стандартная подпись не хранится (конфиги прежние байт-в-байт)."""
    link_set = d.get("set") if isinstance(d, dict) else None
    if link_set not in QUICK_LINK_SETS:
        return {}
    out: dict = {"set": link_set}
    keys = tile_keys(link_set)
    raw_hidden = d.get("hidden")
    hidden = set(raw_hidden) if isinstance(raw_hidden, (list, tuple)) else set()
    hidden = [k for k in keys if k in hidden]
    if hidden:
        out["hidden"] = hidden
    raw_labels = d.get("labels") if isinstance(d.get("labels"), dict) else {}
    standard = {key: _standard(label) for key, label, _hint in QUICK_LINK_TILES[link_set]}
    labels = {}
    for key in keys:
        text = raw_labels.get(key)
        text = " ".join(text.split())[:LABEL_MAX] if isinstance(text, str) else ""
        if text and text != standard[key]:
            labels[key] = text
    if labels:
        out["labels"] = labels
    return out


def shown_labels(link_set: str, labels) -> dict:
    """Свои подписи для показа — только ключи текущего набора (перевод прежнего набора,
    оставшийся в оверлее после смены, не показывается)."""
    if not isinstance(labels, dict):
        return {}
    keys = tile_keys(link_set)
    return {k: v for k, v in labels.items() if k in keys and isinstance(v, str) and v.strip()}


def update_data(data: dict, fields: dict) -> dict:
    """Форма плашек окна (`tiles_present`): набор `set`, показ `show_<ключ>`, подпись
    `label_<ключ>`. Сменили набор — скрытие и подписи прежнего сбрасываются (присланные
    поля плашек относятся к прежнему набору). Возвращает очищенные данные."""
    old = clean_data(data or {})
    link_set = str(fields.get("set", old.get("set", "")) or "")
    if link_set != old.get("set"):
        return clean_data({"set": link_set})
    keys = tile_keys(link_set)
    hidden = [k for k in keys if fields.get(f"show_{k}") != "1"]
    # окно показывает стандартную подпись на языке кабинета — она тоже «своей» не считается
    # (на любом языке платформы: язык кабинета у разных запросов окна может отличаться)
    shown = {key: _all_languages(label) for key, label, _hint in QUICK_LINK_TILES[link_set]}
    labels = {}
    for k in keys:
        text = fields.get(f"label_{k}", "")
        text = " ".join(text.split()) if isinstance(text, str) else ""
        labels[k] = "" if text in shown[k] else text
    return clean_data({"set": link_set, "hidden": hidden, "labels": labels})


def panel(data: dict) -> dict:
    """Модель формы плашек окна: набор и строки плашек текущего набора."""
    from django.utils.translation import gettext as gt

    d = clean_data(data or {})
    link_set = d.get("set", "")
    hidden, labels = set(d.get("hidden") or ()), d.get("labels") or {}
    rows = []
    for key, label, hint in QUICK_LINK_TILES.get(link_set, ()):
        rows.append(
            {
                "key": key,
                "label": str(label),
                "value": labels.get(key) or str(label),
                "shown": key not in hidden,
                "hint": str(hint),
                "show_label": gt("%(label)s zeigen") % {"label": label},
            }
        )
    return {
        "set": link_set,
        "options": [
            ("", gt("Bitte wählen")),
            *((k, str(QUICK_LINK_LABELS[k])) for k in QUICK_LINK_SETS),
        ],
        "rows": rows,
        "max": LABEL_MAX,
    }
