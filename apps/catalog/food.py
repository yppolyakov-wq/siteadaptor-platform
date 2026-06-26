"""LMIV: 14 EU-Allergene (Anhang II LMIV) для маркировки товаров каталога (R4).

Структурный список — источник для формы товара и витрины. Коды стабильны
(храним в Product.allergens), подписи — немецкие (DE-рынок).
"""

# (код, подпись DE) — порядок как в Anhang II LMIV.
ALLERGENS: list[tuple[str, str]] = [
    ("gluten", "Glutenhaltiges Getreide"),
    ("krebstiere", "Krebstiere"),
    ("eier", "Eier"),
    ("fisch", "Fisch"),
    ("erdnuss", "Erdnüsse"),
    ("soja", "Soja"),
    ("milch", "Milch (Laktose)"),
    ("schalenfruechte", "Schalenfrüchte (Nüsse)"),
    ("sellerie", "Sellerie"),
    ("senf", "Senf"),
    ("sesam", "Sesam"),
    ("sulfit", "Schwefeldioxid und Sulfite"),
    ("lupine", "Lupinen"),
    ("weichtiere", "Weichtiere"),
]

_LABELS = dict(ALLERGENS)
VALID_CODES = frozenset(_LABELS)


# A4: диет-теги для меню (код, подпись DE, иконка). Источник для формы товара,
# иконок на карточке и фасетного фильтра «/sortiment/?diet=…».
DIETS: list[tuple[str, str, str]] = [
    ("vegan", "Vegan", "🌱"),
    ("vegetarisch", "Vegetarisch", "🥕"),
    ("glutenfrei", "Glutenfrei", "🌾"),
    ("laktosefrei", "Laktosefrei", "🥛"),
    ("halal", "Halal", "☪️"),
    ("bio", "Bio", "🍃"),
]
_DIET_LABELS = {code: label for code, label, _icon in DIETS}
_DIET_ICONS = {code: icon for code, _label, icon in DIETS}
VALID_DIETS = frozenset(_DIET_LABELS)


def allergen_labels(codes) -> list[str]:
    """Коды → подписи DE. Неизвестные коды отбрасываем, порядок — как в ALLERGENS."""
    wanted = set(codes or [])
    return [label for code, label in ALLERGENS if code in wanted]


def diet_badges(codes) -> list[dict]:
    """Коды → [{code, label, icon}] в порядке DIETS (неизвестные отброшены)."""
    wanted = set(codes or [])
    return [
        {"code": code, "label": label, "icon": _DIET_ICONS[code]}
        for code, label, _icon in DIETS
        if code in wanted
    ]
