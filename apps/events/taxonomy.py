"""Таксономия событий/ретритов (R2): направление, уровень, язык, длительность.

Пресет-списки для фильтров каталога витрины и агрегатора. Значения хранятся в
полях `Event.category` / `level` / `language` (короткий ключ); метки — DE
(витрина DACH). `duration_kind` выводится из дат (не поле) для фильтра
«Tagesworkshop / Wochenende / Mehrtägig».
"""

# Направления / темы (для каталога, SEO-страниц и фильтра агрегатора).
CATEGORIES = [
    ("yoga", "Yoga"),
    ("meditation", "Meditation"),
    ("achtsamkeit", "Achtsamkeit"),
    ("ayurveda", "Ayurveda"),
    ("fasten", "Fasten & Detox"),
    ("klang", "Klang & Musik"),
    ("pilgern", "Pilgern & Spiritualität"),
    ("natur", "Natur & Wandern"),
    ("coaching", "Persönlichkeitsentwicklung"),
]

# Требуемый уровень подготовки участника.
LEVELS = [
    ("alle", "Alle Level"),
    ("anfaenger", "Anfänger"),
    ("mittel", "Mittel"),
    ("fortgeschritten", "Fortgeschritten"),
]

# Язык проведения (контент-тег; не влияет на язык интерфейса витрины).
LANGUAGES = [
    ("de", "Deutsch"),
    ("en", "English"),
    ("mixed", "DE/EN"),
]

# Длительность (выводится из дат события) — ключ → метка.
DURATIONS = [
    ("tag", "Tagesveranstaltung"),
    ("wochenende", "Wochenende"),
    ("mehrtaegig", "Mehrtägig"),
]

_CATEGORY_LABELS = dict(CATEGORIES)
_LEVEL_LABELS = dict(LEVELS)
_LANGUAGE_LABELS = dict(LANGUAGES)
_DURATION_LABELS = dict(DURATIONS)


def category_label(key) -> str:
    return _CATEGORY_LABELS.get(key or "", "")


def level_label(key) -> str:
    return _LEVEL_LABELS.get(key or "", "")


def language_label(key) -> str:
    return _LANGUAGE_LABELS.get(key or "", "")


def duration_label(key) -> str:
    return _DURATION_LABELS.get(key or "", "")


def duration_kind(starts_at, ends_at) -> str:
    """Грубая классификация длительности по датам (для фильтра/бейджа).

    Нет конца или тот же день → tag; до 2 ночей → wochenende; иначе mehrtaegig.
    """
    if not starts_at or not ends_at:
        return "tag"
    days = (ends_at.date() - starts_at.date()).days
    if days <= 0:
        return "tag"
    if days <= 2:
        return "wochenende"
    return "mehrtaegig"
