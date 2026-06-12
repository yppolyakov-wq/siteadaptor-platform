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


def allergen_labels(codes) -> list[str]:
    """Коды → подписи DE. Неизвестные коды отбрасываем, порядок — как в ALLERGENS."""
    wanted = set(codes or [])
    return [label for code, label in ALLERGENS if code in wanted]
