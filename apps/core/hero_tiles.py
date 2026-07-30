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
            "icon": "🗓",
            "label": _("Termin buchen"),
            "sub": _("Freie Zeiten sofort sehen"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
        {
            "icon": "🧴",
            "label": _("Pflegeprodukte"),
            "sub": _("Salonqualität für zu Hause"),
            "url": "storefront-products",
            "gate": "orders",
        },
        {
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
            "icon": "🔧",
            "label": _("Termin vereinbaren"),
            "sub": _("Inspektion, Reifen, Service"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "icon": "📋",
            "label": _("Kostenvoranschlag"),
            "sub": _("Schaden beschreiben — Festpreis erhalten"),
            "url": "storefront-anfrage",
            "gate": "jobs",
        },
        {
            "icon": "🛞",
            "label": _("Teile & Zubehör"),
            "url": "storefront-products",
            "gate": "orders",
        },
        {
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
            "icon": "📋",
            "label": _("Angebot anfordern"),
            "sub": _("Kostenlos & unverbindlich"),
            "url": "storefront-anfrage",
            "gate": "jobs",
        },
        {
            "icon": "🗓",
            "label": _("Termin vereinbaren"),
            "sub": _("Beratung vor Ort"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "icon": "☎",
            "label": _("Rückruf anfordern"),
            "sub": _("Wir melden uns zurück"),
            "url": "storefront-rueckruf",
            "gate": "",
        },
        {
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
            "icon": "🔥",
            "label": _("Aktionen & Angebote"),
            "url": "storefront-aktionen",
            "gate": "deal",
            "deal_sub": True,
            "highlight": True,
        },
        {
            "icon": "🛍",
            "label": _("Sortiment ansehen"),
            "url": "storefront-products",
            "gate": "",
        },
        {
            "icon": "⏰",
            "label": _("Zur Wunschzeit vorbestellen"),
            "sub": _("Jetzt bestellen, ohne Warten abholen"),
            "url": "storefront-products",
            "gate": "orders",
        },
        {
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
            "icon": "🔥",
            "label": _("Aktuelle Deals"),
            "url": "storefront-aktionen",
            "gate": "",
            "deal_sub": True,
            "highlight": True,
        },
        {
            "icon": "🛍",
            "label": _("Sortiment ansehen"),
            "url": "storefront-products",
            "gate": "",
        },
        {
            "icon": "⭐",
            "label": _("Treuepunkte"),
            "sub": _("Bei jedem Einkauf sammeln"),
            "url": "storefront-loyalty",
            "gate": "loyalty",
        },
        {
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
            "icon": "🎟",
            "label": _("Touren & Termine"),
            "sub": _("Termine ansehen und Plätze sichern"),
            "url": "storefront-events",
            "gate": "events",
        },
        {
            "icon": "👥",
            "label": _("Private Führung"),
            "sub": _("Wunschtermin für Ihre Gruppe"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
            "icon": "🎁",
            "label": _("Geschenkgutschein"),
            "sub": _("Freude schenken"),
            "url": "storefront-gutschein",
            "gate": "gift",
        },
        {
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
            "icon": "🧘",
            "label": _("Retreats & Kurse"),
            "sub": _("Termine und freie Plätze"),
            "url": "storefront-events",
            "gate": "events",
        },
        {
            "icon": "🛏",
            "label": _("Übernachtung"),
            "sub": _("Verfügbarkeit prüfen"),
            "url": "storefront-unterkunft",
            "gate": "stays",
        },
        {
            "icon": "🗓",
            "label": _("Einzeltermin"),
            "sub": _("Massage, Beratung, Coaching"),
            "url": "storefront-termin",
            "gate": "booking",
        },
        {
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


def tiles_for(widget: str, tenant, deal=None) -> list[dict]:
    """Плитки первого экрана для архетипа. Неизвестный widget → [] (шаблон
    ничего не рендерит). `deal` — живая акция (`siteui.deal_of_day`)."""
    spec = HERO_TILE_SETS.get(widget or "")
    if not spec:
        return []
    from apps.core import modules

    out = []
    for tile in spec:
        gate = tile.get("gate", "")
        if gate == "deal":
            if deal is None:
                continue
        elif gate and not modules.is_module_active(tenant, gate):
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
                "label": tile["label"],
                "sub": sub,
                "href": href,
                "highlight": bool(tile.get("highlight")),
                "deal_sub": bool(tile.get("deal_sub")) and deal is not None,
            }
        )
    return out
