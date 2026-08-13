"""Структурированная анкета участника события (R1).

Помимо свободных вопросов (`Event.questions`) организатор может включить
готовые поля анкеты: страна, дата рождения, экстренный контакт, питание,
уровень опыта, аллергии, мед. особенности (телефон собирается отдельно).
Включённые ключи хранятся в `Event.registration_fields`; ответы — в
`Ticket.answers` под ключом поля (например `country`, `diet`), чтобы поля
ростера/CSV были стабильны и не зависели от текста свободных вопросов.
"""

# Каталог пресет-полей (порядок = порядок показа). type: text|date|textarea|select.
FIELDS = [
    {"key": "country", "label": "Land", "type": "text"},
    {"key": "birth_date", "label": "Geburtsdatum", "type": "date"},
    {"key": "emergency_contact", "label": "Notfallkontakt (Name & Telefon)", "type": "text"},
    {
        "key": "diet",
        "label": "Ernährung",
        "type": "select",
        "options": [
            "Vegetarisch",
            "Vegan",
            "Rohkost",
            "Glutenfrei",
            "Ayurvedisch",
            "Kindermenü",
        ],
    },
    {
        "key": "experience",
        "label": "Erfahrungslevel",
        "type": "select",
        "options": ["Anfänger", "Mittel", "Fortgeschritten"],
    },
    {"key": "allergies", "label": "Allergien / Unverträglichkeiten", "type": "text"},
    {"key": "medical", "label": "Gesundheitliche Hinweise", "type": "textarea"},
    # MT-1: мото/квадро-туры — то, что организатор обязан знать до старта
    # (допуск к технике, реальный опыт, подбор мотоцикла по росту).
    {"key": "license_class", "label": "Führerscheinklasse", "type": "text"},
    {
        "key": "riding_experience",
        "label": "Fahrpraxis",
        "type": "select",
        "options": [
            "Bis 5.000 km",
            "5.000–20.000 km",
            "Über 20.000 km",
            "Offroad-erfahren",
        ],
    },
    {"key": "height_cm", "label": "Körpergröße (cm)", "type": "text"},
    {
        "key": "own_bike",
        "label": "Eigenes Motorrad oder Mietmaschine",
        "type": "select",
        "options": ["Mietmaschine", "Eigenes Motorrad"],
    },
]

_BY_KEY = {f["key"]: f for f in FIELDS}
VALID_KEYS = [f["key"] for f in FIELDS]

# Префикс имён полей в POST-форме (изолируем от свободных вопросов q0/q1…).
POST_PREFIX = "reg_"


def choices() -> list[tuple[str, str]]:
    """(key, label) для чекбоксов формы кабинета — в порядке каталога."""
    return [(f["key"], f["label"]) for f in FIELDS]


def active(raw) -> list[dict]:
    """Включённые поля события в порядке каталога (мусор/дубли отфильтрованы)."""
    enabled = {k for k in (raw or []) if k in _BY_KEY}
    return [f for f in FIELDS if f["key"] in enabled]


def labels(raw) -> list[tuple[str, str]]:
    """(key, label) включённых полей — для колонок ростера/CSV."""
    return [(f["key"], f["label"]) for f in active(raw)]


def collect(raw, post) -> dict:
    """Ответы на включённые поля из POST (имя — POST_PREFIX+key), непустые."""
    out = {}
    for f in active(raw):
        value = (post.get(POST_PREFIX + f["key"]) or "").strip()[:500]
        if value:
            out[f["key"]] = value
    return out
