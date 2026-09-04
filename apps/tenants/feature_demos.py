"""Живые примеры ПО ФУНКЦИЯМ для платформенной страницы `/branchen/`.

Решение владельца 2026-08-01: демо-витрины подписаны видами бизнеса
(«Lebensmittel», «Friseur»), поэтому найти пример конкретной ВОЗМОЖНОСТИ —
акций, брони, подбора — по названию нельзя: владелец искал «сайт с акциями» и не
нашёл, хотя он есть (`aktionsmarkt`). Реестр ниже даёт второй разрез: функция →
конкретная страница живого демо.

Каждая запись указывает на демо-кит (`host` = `DEMO_KIT_HOST`-поддомен) и путь,
который у этого кита заведомо включён — ссылка ведёт сразу на нужный экран, а не
на главную. Пункты без засеянного демо просто не показываются (мёртвых ссылок не
бывает), поэтому реестр можно пополнять раньше, чем прогонят `seed_demo_tenants`.
"""

from django.utils.translation import gettext_lazy as _

# (ключ, иконка, заголовок, что показывает, поддомен демо, путь)
FEATURE_DEMOS = [
    {
        "key": "promotions",
        "icon": "🔥",
        "title": _("Aktionen & Rabatte"),
        "blurb": _(
            "Prozent, Festpreis, Mystery-Deal, Countdown, begrenzte Stückzahl — "
            "alle Aktionstypen auf einer Seite."
        ),
        "host": "aktionsmarkt",
        "path": "/aktionen/",
    },
    {
        "key": "booking",
        "icon": "🗓",
        "title": _("Termine online buchen"),
        "blurb": _("Mitarbeiter wählen, Kalender, freie Zeiten — Buchung ohne Anruf."),
        "host": "friseur",
        "path": "/termin/",
    },
    {
        "key": "stays",
        "icon": "🛏",
        "title": _("Übernachtungen buchen"),
        "blurb": _("Verfügbarkeit im Kalender, Tarife mit Frühstück, Preis pro Nacht."),
        "host": "hotel",
        "path": "/unterkunft/",
    },
    {
        "key": "orders",
        "icon": "🧺",
        "title": _("Bestellen & abholen"),
        "blurb": _("Warenkorb, Abholzeit, Bezahlung — Click & Collect für den Laden."),
        "host": "baeckerei",
        "path": "/sortiment/",
    },
    {
        "key": "variants",
        "icon": "👗",
        "title": _("Größen & Farben"),
        "blurb": _("Varianten mit eigenem Foto, Größentabelle, Warteliste bei Ausverkauf."),
        "host": "mode",
        "path": "/sortiment/",
    },
    {
        "key": "events",
        "icon": "🎟",
        "title": _("Veranstaltungen & Tickets"),
        "blurb": _("Termine, Ticketkategorien, Teilnehmerzahl — Anmeldung online."),
        "host": "retreat",
        "path": "/veranstaltung/",
    },
    {
        "key": "jobs",
        "icon": "📋",
        "title": _("Anfragen & Angebote"),
        "blurb": _("Anfrage vom Kunden, Festpreis-Angebot zurück, Annahme mit einem Klick."),
        "host": "handwerker",
        "path": "/anfrage/",
    },
    {
        # GK-1: событийная заявка кейтеринга (AF-1 поля даты/гостей/типа).
        "key": "catering_anfrage",
        "icon": "🍽",
        "title": _("Event-Anfrage fürs Catering"),
        "blurb": _("Wunschdatum, Gästezahl und Anlass — Angebot kommt per E-Mail."),
        "host": "catering",
        "path": "/anfrage/",
    },
    {
        "key": "finder",
        "icon": "🧭",
        "title": _("Produktfinder"),
        "blurb": _("Zwei, drei Fragen an den Gast — und die passende Empfehlung."),
        "host": "baeckerei",
        "path": "/finder/",
    },
    {
        # O-6: фильтры — то, чего в реестре не было вовсе, а спрашивают о нём
        # первым делом («можно ли фильтровать по размеру и цвету»).
        "key": "facets",
        "icon": "🎛",
        "title": _("Filter & Facetten"),
        "blurb": _(
            "Zustand, Marke, Größe, Farbe, Preis und „nur reduziert“ — "
            "ein Katalog mit über 200 Einzelstücken."
        ),
        "host": "outlet",
        "path": "/sortiment/damenmode/",
    },
    {
        # O-6: B-Ware/Restposten — второй разрез того же демо: цена и состояние.
        "key": "condition",
        "icon": "🏷",
        "title": _("Zustand & UVP"),
        "blurb": _(
            "Neu ohne OVP, Ausstellungsstück, geprüfte Retoure — mit "
            "Streichpreis gegen die UVP und ehrlichem Hinweis zum Zustand."
        ),
        "host": "outlet",
        "path": "/aktionen/",
    },
]


def feature_demo_cards(request=None) -> list[dict]:
    """Карточки «примеры по функциям» — только с реально засеянным демо.

    Пустой список (демо не прогнаны) → блок на странице не рендерится.
    """
    from django.conf import settings

    from .onboarding import _seeded_demo_hosts

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    base_host = base.split(":")[0]
    scheme = getattr(request, "scheme", "https") if request is not None else "https"
    seeded = _seeded_demo_hosts()

    cards = []
    for item in FEATURE_DEMOS:
        if f"{item['host']}.{base_host}" not in seeded:
            continue
        cards.append(
            {
                "key": item["key"],
                "icon": item["icon"],
                "title": str(item["title"]),
                "blurb": str(item["blurb"]),
                "url": f"{scheme}://{item['host']}.{base}{item['path']}",
            }
        )
    return cards
