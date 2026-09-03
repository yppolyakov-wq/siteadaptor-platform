"""Виды отображения вариантов товара и модификаторов (план
`docs/option-display-styles-plan-2026-08-01.md`).

Решение владельца 2026-08-01: вид выбирает ВЛАДЕЛЕЦ из реестра — как
`CBLOCK_VARIANTS`/`SECTION_STYLES` в редакторе, а не «одна разметка на всех».
Пустой ключ ВЕЗДЕ = сегодняшняя разметка (выпадающий список), поэтому включение
реестра ничего не меняет на существующих сайтах.

Инвариант формы корзины: имена полей пинит `test_cart_form_variants_and_modifiers_
fields` (regex по `name="…"` во всём HTML формы). Поэтому свотчи НИЧЕГО не шлют
сами — они управляют существующим `select name="variant"`, а их кнопки идут без
атрибута `name`. Без JS остаётся ровно прежний селект.
"""

from django.utils.translation import gettext_lazy as _

# (ключ, подпись, подсказка «когда уместно»)
VARIANT_STYLES = [
    ("", _("Dropdown list"), _("Compact — good for many pack sizes.")),
    ("buttons", _("Buttons"), _("Sizes and volumes at a glance.")),
    ("color", _("Colour dots"), _("For clothing: one dot per colour.")),
    ("photo", _("Photo tiles"), _("Shows the variant photo — needs photos.")),
    ("list", _("List with photo"), _("Row per variant: photo, name, price, stock.")),
    ("axes", _("Colour + size"), _("Two rows: colour dots, then sizes.")),
]

MODIFIER_STYLES = [
    ("", _("As before"), _("Dropdown for a single choice, checkboxes for several.")),
    ("tiles", _("Photo tiles"), _("Big tappable tiles — like a food delivery app.")),
    ("list", _("List with photo"), _("Row with thumbnail, label and surcharge.")),
    ("chips", _("Chips"), _("Compact pills, no photos.")),
]

VARIANT_STYLE_KEYS = [k for k, _label, _hint in VARIANT_STYLES]
MODIFIER_STYLE_KEYS = [k for k, _label, _hint in MODIFIER_STYLES]

# Цвет кружка — ТОЛЬКО по явному словарю. «Угадывание» по строке недопустимо:
# «Sonnengelb» без словаря стало бы чёрным, а гость решил бы, что товар чёрный.
# Ключи в нижнем регистре; неизвестный цвет → фото варианта → первая буква.
COLOR_HEX = {
    "schwarz": "#111827",
    "weiß": "#ffffff",
    "weiss": "#ffffff",
    "grau": "#9ca3af",
    "anthrazit": "#374151",
    "silber": "#d1d5db",
    "blau": "#2563eb",
    "hellblau": "#7dd3fc",
    "dunkelblau": "#1e3a8a",
    "navy": "#1e3a8a",
    "türkis": "#14b8a6",
    "tuerkis": "#14b8a6",
    "grün": "#16a34a",
    "gruen": "#16a34a",
    "oliv": "#4d7c0f",
    "rot": "#dc2626",
    "bordeaux": "#7f1d1d",
    "rosa": "#f9a8d4",
    "pink": "#ec4899",
    "lila": "#8b5cf6",
    "violett": "#7c3aed",
    "gelb": "#facc15",
    "orange": "#f97316",
    "braun": "#78350f",
    "beige": "#e7dcc7",
    "creme": "#f5f0e1",
    "sand": "#e0cfa9",
    "gold": "#d4af37",
    # 2026-09-03: современные оттенки модных коллекций. Без записи здесь кружок
    # не рисуется вовсе, поэтому магазин с палитрой «Salbei/Terrakotta/Petrol»
    # показывал бы вместо свотчей буквы — реестр, а не угадывание (см. выше).
    "ecru": "#f0e9dc",
    "taupe": "#b8a89a",
    "khaki": "#a8a06a",
    "salbei": "#a3b18a",
    "mint": "#9ee2c4",
    "petrol": "#0f766e",
    "nachtblau": "#172554",
    "jeansblau": "#3b6ea5",
    "lavendel": "#c4b5fd",
    "flieder": "#d8b4fe",
    "altrosa": "#d8a7a1",
    "rosé": "#e8b4b8",
    "rose": "#e8b4b8",
    "koralle": "#fb7185",
    "rostrot": "#b7410e",
    "terrakotta": "#c96f4a",
    "curry": "#d69e2e",
    "senf": "#c9a227",
    "camel": "#c19a6b",
    "cognac": "#9a4f20",
    "aubergine": "#5b2333",
    "waldgrün": "#14532d",
    "waldgruen": "#14532d",
    "bunt": "",  # многоцветный — кружок не рисуем, покажем подпись
}


def color_hex(name: str) -> str:
    """HEX для названия цвета ('' — если цвет неизвестен или многоцветный)."""
    return COLOR_HEX.get((name or "").strip().lower(), "")


def variant_style(product, site_default: str = "") -> str:
    """Действующий вид выбора вариантов: свой у товара, иначе дефолт магазина.

    Неизвестное значение (руками в БД / старый конфиг) → "" (список), а не 500.
    """
    own = getattr(product, "variant_style", "") or ""
    if own in VARIANT_STYLE_KEYS and own:
        return own
    return site_default if site_default in VARIANT_STYLE_KEYS else ""


def modifier_style(group) -> str:
    """Вид группы модификаторов ('' = как раньше)."""
    own = getattr(group, "display_style", "") or ""
    return own if own in MODIFIER_STYLE_KEYS else ""
