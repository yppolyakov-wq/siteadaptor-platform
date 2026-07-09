"""LMIV: 14 EU-Allergene (Anhang II LMIV) для маркировки товаров каталога (R4).

Структурный список — источник для формы товара и витрины. Коды стабильны
(храним в Product.allergens). Подписи — немецкие (база, msgid), но обёрнуты в
gettext_lazy: на витрине резолвятся в язык, выбранный клиентом (Ф3 — переводы
меток-справочников в locale/<lang>/LC_MESSAGES/django.po; DE=msgid, EN в .po).
"""

from django.utils.translation import gettext_lazy as _

# (код, подпись DE) — порядок как в Anhang II LMIV.
ALLERGENS: list[tuple[str, str]] = [
    ("gluten", _("Glutenhaltiges Getreide")),
    ("krebstiere", _("Krebstiere")),
    ("eier", _("Eier")),
    ("fisch", _("Fisch")),
    ("erdnuss", _("Erdnüsse")),
    ("soja", _("Soja")),
    ("milch", _("Milch (Laktose)")),
    ("schalenfruechte", _("Schalenfrüchte (Nüsse)")),
    ("sellerie", _("Sellerie")),
    ("senf", _("Senf")),
    ("sesam", _("Sesam")),
    ("sulfit", _("Schwefeldioxid und Sulfite")),
    ("lupine", _("Lupinen")),
    ("weichtiere", _("Weichtiere")),
]

_LABELS = dict(ALLERGENS)
VALID_CODES = frozenset(_LABELS)


# A4: диет-теги для меню (код, подпись DE, иконка). Источник для формы товара,
# иконок на карточке и фасетного фильтра «/sortiment/?diet=…».
DIETS: list[tuple[str, str, str]] = [
    ("vegan", _("Vegan"), "🌱"),
    ("vegetarisch", _("Vegetarisch"), "🥕"),
    ("glutenfrei", _("Glutenfrei"), "🌾"),
    ("laktosefrei", _("Laktosefrei"), "🥛"),
    ("halal", _("Halal"), "☪️"),
    ("bio", _("Bio"), "🍃"),
]
_DIET_LABELS = {code: label for code, label, _icon in DIETS}
_DIET_ICONS = {code: icon for code, _label, icon in DIETS}
VALID_DIETS = frozenset(_DIET_LABELS)


# E-2/PAngV+LMIV: kennzeichnungspflichtige Zusatzstoff-Klassen (Gastro-Fußnoten,
# LMZDV/LMIDV). Коды стабильны (храним в Product.additives), подписи — немецкие.
ADDITIVES: list[tuple[str, str]] = [
    ("farbstoff", _("mit Farbstoff")),
    ("konservierungsstoff", _("mit Konservierungsstoff")),
    ("antioxidationsmittel", _("mit Antioxidationsmittel")),
    ("geschmacksverstaerker", _("mit Geschmacksverstärker")),
    ("geschwefelt", _("geschwefelt")),
    ("geschwaerzt", _("geschwärzt")),
    ("gewachst", _("gewachst")),
    ("phosphat", _("mit Phosphat")),
    ("suessungsmittel", _("mit Süßungsmittel")),
    ("phenylalanin", _("enthält eine Phenylalaninquelle")),
    ("koffeinhaltig", _("koffeinhaltig")),
    ("chininhaltig", _("chininhaltig")),
    ("taurin", _("mit Taurin")),
]
_ADDITIVE_LABELS = dict(ADDITIVES)
VALID_ADDITIVES = frozenset(_ADDITIVE_LABELS)


def allergen_labels(codes) -> list[str]:
    """Коды → подписи DE. Неизвестные коды отбрасываем, порядок — как в ALLERGENS."""
    wanted = set(codes or [])
    return [label for code, label in ALLERGENS if code in wanted]


def additive_labels(codes) -> list[str]:
    """Коды → подписи DE. Неизвестные отброшены, порядок — как в ADDITIVES."""
    wanted = set(codes or [])
    return [label for code, label in ADDITIVES if code in wanted]


def diet_badges(codes) -> list[dict]:
    """Коды → [{code, label, icon}] в порядке DIETS (неизвестные отброшены)."""
    wanted = set(codes or [])
    return [
        {"code": code, "label": label, "icon": _DIET_ICONS[code]}
        for code, label, _icon in DIETS
        if code in wanted
    ]
