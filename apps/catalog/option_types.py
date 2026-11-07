"""FB-24: типы опций товара — стандартные (сопоставлены с фильтрами портала и Google) и
свои типы владельца. Типы ОБЩИЕ НА МАГАЗИН (решение владельца 2026-11-07).

Хранение:
* стандартные `size` и `color` читаются из полей варианта (`ProductVariant.size/color`):
  на них держатся склад, матрица «размер × цвет», фид, CSV-импорт и фасеты — дублировать их
  в таблицу значит завести второй источник правды;
* все остальные типы (стандартные `material`, `volume`, … и свои) — `VariantOption`
  (вариант × тип → значение).

Единое чтение осей варианта — `variant_axes(variant)`; сборка метки — `axes_label`.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

#: код → (подпись, атрибут Google Merchant или "", ключ фильтра портала или "").
#: Базовый набор «пополняем по ходу» (решение владельца).
STANDARD = {
    "size": (_("Größe"), "size", "groesse"),
    "color": (_("Farbe"), "color", "farbe"),
    "material": (_("Material"), "material", "material"),
    "volume": (_("Volumen"), "", "volumen"),
    "weight": (_("Gewicht"), "", "gewicht"),
    "flavor": (_("Geschmack"), "", "geschmack"),
    "length": (_("Länge"), "", "laenge"),
    "pack": (_("Stückzahl"), "", "stueckzahl"),
}

#: Типы, значение которых живёт в полях варианта, а не в VariantOption.
FIELD_BACKED = ("size", "color")

#: Сколько осей может быть у одного товара (генератор строит их произведение).
MAX_AXES = 3
#: Сколько своих типов на магазин и значений на тип.
MAX_TYPES = 30
MAX_VALUES = 60


def standard_label(code: str) -> str:
    entry = STANDARD.get(code)
    return str(entry[0]) if entry else ""


def type_label(option_type) -> str:
    """Подпись типа на языке посетителя: своё имя (с переводом) или подпись стандарта."""
    from apps.core.models import resolve_overlay

    name = resolve_overlay(option_type.name, option_type.name_i18n)
    return name or standard_label(option_type.standard) or option_type.code


def clean_axes(codes, allowed) -> list[str]:
    """Список кодов осей товара → только известные, без дублей, не больше MAX_AXES."""
    out: list[str] = []
    for code in codes or []:
        if isinstance(code, str) and code in allowed and code not in out:
            out.append(code)
        if len(out) >= MAX_AXES:
            break
    return out


def variant_axes(variant, codes=None) -> dict[str, str]:
    """Оси варианта {код типа: значение} (базовый язык — ключи учёта).

    `codes` — порядок осей товара; без него — размер, цвет и все свои значения варианта.
    Значения своих типов читаются из `option_links` (prefetch-friendly)."""
    links = {}
    for link in variant.option_links.all():
        links[link.option_type.code] = link.value.value
    values = {"size": variant.size or "", "color": variant.color or "", **links}
    order = list(codes) if codes else [*FIELD_BACKED, *links]
    return {code: values.get(code, "") for code in order if values.get(code, "")}


def axes_label(values: dict[str, str]) -> str:
    """Метка варианта из осей: «M · Blau · Baumwolle» (порядок — порядок осей)."""
    return " · ".join(v for v in values.values() if v)
