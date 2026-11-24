"""Структурированная анкета участника события (R1).

Помимо свободных вопросов (`Event.questions`) организатор может включить
готовые поля анкеты: страна, дата рождения, экстренный контакт, питание,
уровень опыта, аллергии, мед. особенности (телефон собирается отдельно).
Включённые ключи хранятся в `Event.registration_fields`; ответы — в
`Ticket.answers` под ключом поля (например `country`, `diet`), чтобы поля
ростера/CSV были стабильны и не зависели от текста свободных вопросов.
"""

from django.utils.translation import gettext, ngettext, pgettext_lazy
from django.utils.translation import gettext_lazy as _

# Каталог пресет-полей (порядок = порядок показа). type: text|date|textarea|select.
# Вариант select — пара (value, label). value — немецкая строка, одна на всех языках: её
# хранят ответы (`Ticket.answers`, `TicketParticipant.answers`), ростер, CSV и письма —
# менять нельзя. label — перевод, виден только в тексте `<option>` формы.
FIELDS = [
    {"key": "country", "label": _("Land"), "type": "text"},
    {"key": "birth_date", "label": _("Geburtsdatum"), "type": "date"},
    {"key": "emergency_contact", "label": _("Notfallkontakt (Name & Telefon)"), "type": "text"},
    {
        "key": "diet",
        "label": _("Ernährung"),
        "type": "select",
        "options": [
            ("Vegetarisch", pgettext_lazy("registration option", "Vegetarisch")),
            ("Vegan", pgettext_lazy("registration option", "Vegan")),
            ("Rohkost", pgettext_lazy("registration option", "Rohkost")),
            ("Glutenfrei", pgettext_lazy("registration option", "Glutenfrei")),
            ("Ayurvedisch", pgettext_lazy("registration option", "Ayurvedisch")),
            ("Kindermenü", pgettext_lazy("registration option", "Kindermenü")),
        ],
    },
    {
        "key": "experience",
        "label": _("Erfahrungslevel"),
        "type": "select",
        "options": [
            ("Anfänger", pgettext_lazy("registration option", "Anfänger")),
            ("Mittel", pgettext_lazy("registration option", "Mittel")),
            ("Fortgeschritten", pgettext_lazy("registration option", "Fortgeschritten")),
        ],
    },
    {"key": "allergies", "label": _("Allergien / Unverträglichkeiten"), "type": "text"},
    {"key": "medical", "label": _("Gesundheitliche Hinweise"), "type": "textarea"},
    # MT-1: мото/квадро-туры — то, что организатор обязан знать до старта
    # (допуск к технике, реальный опыт, подбор мотоцикла по росту).
    {"key": "license_class", "label": _("Führerscheinklasse"), "type": "text"},
    {
        "key": "riding_experience",
        "label": _("Fahrpraxis"),
        "type": "select",
        "options": [
            ("Bis 5.000 km", pgettext_lazy("registration option", "Bis 5.000 km")),
            ("5.000–20.000 km", pgettext_lazy("registration option", "5.000–20.000 km")),
            ("Über 20.000 km", pgettext_lazy("registration option", "Über 20.000 km")),
            ("Offroad-erfahren", pgettext_lazy("registration option", "Offroad-erfahren")),
        ],
    },
    {"key": "height_cm", "label": _("Körpergröße (cm)"), "type": "text"},
    {
        "key": "own_bike",
        "label": _("Eigenes Motorrad oder Mietmaschine"),
        "type": "select",
        "options": [
            ("Mietmaschine", pgettext_lazy("registration option", "Mietmaschine")),
            ("Eigenes Motorrad", pgettext_lazy("registration option", "Eigenes Motorrad")),
        ],
    },
]

_BY_KEY = {f["key"]: f for f in FIELDS}
VALID_KEYS = [f["key"] for f in FIELDS]
#: FB-33 D6 (ревью): ответы, которые при ошибке формы НЕ возвращаются через сессию — здоровье
#: (Art. 9 DSGVO), экстренный контакт третьего лица, дата рождения. Гость вводит их заново.
NO_ECHO_KEYS = ("medical", "allergies", "emergency_contact", "birth_date")

# Префикс имён полей в POST-форме (изолируем от свободных вопросов q0/q1…).
POST_PREFIX = "reg_"
#: Потолок длины ответа (сервер и `maxlength` формы).
VALUE_MAX = 500


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


def collect(raw, post, prefix=POST_PREFIX) -> dict:
    """Ответы на включённые поля из POST (имя — prefix+key), непустые.
    KA-12 T-5: свой `prefix` у каждого участника группы (`p2_reg_` …)."""
    out = {}
    for f in active(raw):
        value = (post.get(prefix + f["key"]) or "").strip()[:VALUE_MAX]
        if value:
            out[f["key"]] = value
    return out


def invalid_selects(raw, post, prefix=POST_PREFIX, *, keep=None) -> list[str]:
    """FB-33 D6: ключи включённых select, чьё присланное значение не из списка вариантов.

    Решение владельца (2026-11-24): select принимает только вариант реестра (точное
    совпадение `value` после `strip`, как у `collect`). Исключение — `keep`, прежний ответ
    ЭТОГО слота из БД (старый вариант, ручная правка): он пересохраняется как был, иначе
    повторное сохранение формы стёрло бы его. Пустое значение — «не ответил», не ошибка.
    Текстовые поля не сверяются. Зовётся рядом с `collect` (сигнатура `collect` прежняя)."""
    keep = keep if isinstance(keep, dict) else {}
    bad = []
    for f in active(raw):
        if f.get("type") != "select":
            continue
        value = (post.get(prefix + f["key"]) or "").strip()[:VALUE_MAX]
        if not value or value in [v for v, _label in f.get("options") or []]:
            continue
        if value == keep.get(f["key"]):
            continue
        bad.append(f["key"])
    return bad


def error_summary(n: int) -> str:
    """Одно сводное сообщение над формой (подробность — у каждого поля)."""
    return ngettext("Bitte %(n)s Angabe korrigieren.", "Bitte %(n)s Angaben korrigieren.", n) % {
        "n": n
    }


def select_error(key: str) -> str:
    """Текст ошибки поля select — подпись поля берётся из реестра (не из POST)."""
    field = _BY_KEY.get(key)
    label = field["label"] if field else key
    return gettext("Bitte bei „%(field)s“ einen Eintrag aus der Liste wählen.") % {"field": label}
