"""Пресеты акций по вертикали бизнеса (Track B3).

Один кор — много вертикалей. Пресет = подпись + initial для PromotionForm
(пред-заполнение формы создания при ?preset=<key>). Цель — «просто и понятно»:
владелец создаёт типичную для своей отрасли акцию в один клик. Неизвестные
initial-ключи форма игнорирует, поэтому `recurrence` безопасно держать заранее
(включится, когда появится поле, B3b).
"""

from django.utils.translation import gettext_lazy as _

# Универсальные пресеты — доступны всем вертикалям.
_COMMON = [
    {
        "key": "rabatt",
        "label": _("Rabatt-Aktion"),
        "initial": {"title_de": "Aktion", "promo_type": "discount", "discount_percent": 20},
    },
]

# business_type → список пресетов.
PRESETS = {
    "bakery": [
        {
            "key": "feierabend",
            "label": _("Feierabend-Tüte 🌱"),
            "initial": {
                "title_de": "Feierabend-Überraschungstüte",
                "promo_type": "reservation",
                "is_surprise": True,
                "discount_percent": 50,
                "available_quantity": 10,
                "reservation_ttl_hours": 3,
            },
        },
        {
            "key": "woche",
            "label": _("Angebot der Woche"),
            "initial": {
                "title_de": "Angebot der Woche",
                "promo_type": "discount",
                "discount_percent": 20,
                "recurrence": "weekly",
            },
        },
    ],
    "butcher": [
        {
            "key": "grill",
            "label": _("Grillpaket vorbestellen"),
            "initial": {
                "title_de": "Grillpaket",
                "promo_type": "reservation",
                "available_quantity": 20,
                "reservation_ttl_hours": 48,
            },
        },
        {
            "key": "woche",
            "label": _("Wochenangebot"),
            "initial": {
                "title_de": "Wochenangebot",
                "promo_type": "discount",
                "discount_percent": 15,
                "recurrence": "weekly",
            },
        },
    ],
    "grocery": [
        {
            "key": "mhd",
            "label": _("MHD-Rabatt 🌱"),
            "initial": {
                "title_de": "Kurz vor MHD",
                "promo_type": "reservation",
                "is_surprise": True,
                "discount_percent": 40,
                "available_quantity": 15,
                "reservation_ttl_hours": 6,
            },
        },
    ],
    "restaurant": [
        {
            "key": "mittag",
            "label": _("Mittagstisch"),
            "initial": {
                "title_de": "Mittagstisch",
                "promo_type": "reservation",
                "reservation_ttl_hours": 4,
                "recurrence": "daily",
            },
        },
        {
            "key": "happy",
            "label": _("Happy Hour"),
            "initial": {"title_de": "Happy Hour", "promo_type": "discount", "discount_percent": 30},
        },
    ],
    "cafe": [
        {
            "key": "mittag",
            "label": _("Mittagstisch"),
            "initial": {
                "title_de": "Mittagstisch",
                "promo_type": "reservation",
                "reservation_ttl_hours": 4,
                "recurrence": "daily",
            },
        },
    ],
    "clothing": [
        {
            "key": "sale",
            "label": _("Schlussverkauf"),
            "initial": {
                "title_de": "Schlussverkauf",
                "promo_type": "discount",
                "discount_percent": 30,
            },
        },
    ],
    # GK-1 Catering: раннее бронирование даты + сезонное предложение.
    "catering": [
        {
            "key": "fruehbucher",
            "label": _("Frühbucher-Rabatt"),
            "initial": {
                "title_de": "Frühbucher-Rabatt: 10 % bei Buchung 8 Wochen im Voraus",
                "promo_type": "discount",
                "discount_percent": 10,
            },
        },
        {
            "key": "saison",
            "label": _("Saison-Angebot"),
            "initial": {
                "title_de": "Saison-Menü zum Aktionspreis",
                "promo_type": "discount",
                "discount_percent": 15,
                "recurrence": "weekly",
            },
        },
    ],
    "online_shop": [
        {
            "key": "sale",
            "label": _("Sale-Aktion"),
            "initial": {
                "title_de": "Sale-Aktion",
                "promo_type": "discount",
                "discount_percent": 25,
            },
        },
        {
            "key": "launch",
            "label": _("Neu im Shop"),
            "initial": {
                "title_de": "Neu im Shop",
                "promo_type": "discount",
                "discount_percent": 10,
            },
        },
    ],
    "retail": [
        {
            "key": "sale",
            "label": _("Sonderangebot"),
            "initial": {
                "title_de": "Sonderangebot",
                "promo_type": "discount",
                "discount_percent": 25,
            },
        },
    ],
    "hotel": [
        {
            "key": "lastminute",
            "label": _("Last-Minute-Angebot"),
            "initial": {
                "title_de": "Last-Minute-Angebot",
                "promo_type": "reservation",
                "discount_percent": 25,
                "available_quantity": 5,
            },
        },
    ],
    # S6-архетипы: тип «discount» (generisch %-Rabatt) — без reservation-механики
    # (Menge/TTL), которая завязана на каталог; для услуг/термина/анфраге корректнее.
    "friseur": [
        {
            "key": "neukunde",
            "label": _("Neukunden-Rabatt"),
            "initial": {
                "title_de": "Neukunden-Rabatt",
                "promo_type": "discount",
                "discount_percent": 20,
            },
        },
    ],
    "werkstatt": [
        {
            "key": "check",
            "label": _("Saison-Check-Aktion"),
            "initial": {
                "title_de": "Frühjahrs-Check",
                "promo_type": "discount",
                "discount_percent": 15,
            },
        },
    ],
    "handwerker": [
        {
            "key": "saison",
            "label": _("Saison-Aktion"),
            "initial": {
                "title_de": "Saison-Aktion",
                "promo_type": "discount",
                "discount_percent": 10,
            },
        },
    ],
    "events": [
        {
            "key": "fruehbucher",
            "label": _("Frühbucher-Ticket"),
            "initial": {
                "title_de": "Frühbucher-Rabatt",
                "promo_type": "discount",
                "discount_percent": 15,
            },
        },
    ],
}


def presets_for(business_type: str) -> list:
    """Пресеты для вертикали + универсальные."""
    return list(PRESETS.get(business_type, [])) + _COMMON


def preset_initial(business_type: str, key: str) -> dict:
    """initial конкретного пресета (или пусто)."""
    for preset in presets_for(business_type):
        if preset["key"] == key:
            return dict(preset["initial"])
    return {}
