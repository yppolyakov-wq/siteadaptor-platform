"""Пресеты акций по вертикали бизнеса (Track B3).

Один кор — много вертикалей. Пресет = подпись + initial для PromotionForm
(пред-заполнение формы создания при ?preset=<key>). Цель — «просто и понятно»:
владелец создаёт типичную для своей отрасли акцию в один клик. Неизвестные
initial-ключи форма игнорирует, поэтому `recurrence` безопасно держать заранее
(включится, когда появится поле, B3b).
"""

# Универсальные пресеты — доступны всем вертикалям.
_COMMON = [
    {
        "key": "rabatt",
        "label": "Rabatt-Aktion",
        "initial": {"title_de": "Aktion", "promo_type": "discount", "discount_percent": 20},
    },
]

# business_type → список пресетов.
PRESETS = {
    "bakery": [
        {
            "key": "feierabend",
            "label": "Feierabend-Tüte 🌱",
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
            "label": "Angebot der Woche",
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
            "label": "Grillpaket vorbestellen",
            "initial": {
                "title_de": "Grillpaket",
                "promo_type": "reservation",
                "available_quantity": 20,
                "reservation_ttl_hours": 48,
            },
        },
        {
            "key": "woche",
            "label": "Wochenangebot",
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
            "label": "MHD-Rabatt 🌱",
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
            "label": "Mittagstisch",
            "initial": {
                "title_de": "Mittagstisch",
                "promo_type": "reservation",
                "reservation_ttl_hours": 4,
                "recurrence": "daily",
            },
        },
        {
            "key": "happy",
            "label": "Happy Hour",
            "initial": {"title_de": "Happy Hour", "promo_type": "discount", "discount_percent": 30},
        },
    ],
    "cafe": [
        {
            "key": "mittag",
            "label": "Mittagstisch",
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
            "label": "Schlussverkauf",
            "initial": {
                "title_de": "Schlussverkauf",
                "promo_type": "discount",
                "discount_percent": 30,
            },
        },
    ],
    "retail": [
        {
            "key": "sale",
            "label": "Sonderangebot",
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
            "label": "Last-Minute-Angebot",
            "initial": {
                "title_de": "Last-Minute-Angebot",
                "promo_type": "reservation",
                "discount_percent": 25,
                "available_quantity": 5,
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
