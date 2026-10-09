"""T-8.17: реестр районов городов (план docs/t8-15-districts-portal-plan-2026-10-09.md).

Район бизнеса — выбор из справочника, а не свободный текст: иначе «Ohligs»,
«Solingen-Ohligs» и «ohligs» стали бы тремя районами (та же каша, что с городом,
дыра A6). Хранение — slug района в ``Tenant.district`` и ``AggregatorListing.district``.

PLZ — только ПОДСКАЗКА при заполнении: в Solingen индексы с районами совпадают не
один к одному, поэтому здесь лишь уверенные индексы, остальное владелец выбирает сам.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class District:
    slug: str
    name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    plz: tuple[str, ...] = field(default_factory=tuple)


# Ключ — нормализованное название города (см. city_key). Порядок районов = официальная
# нумерация Stadtbezirke (так их видит житель на сайте города).
CITIES: dict[str, tuple[District, ...]] = {
    "solingen": (
        District("graefrath", "Gräfrath", aliases=("Grafrath", "Graefrath"), plz=("42653",)),
        District("wald", "Wald", plz=("42719",)),
        District("mitte", "Mitte", aliases=("Solingen-Mitte", "Innenstadt"), plz=("42651",)),
        District(
            "burg-hoehscheid",
            "Burg/Höhscheid",
            aliases=("Burg", "Höhscheid", "Hoehscheid", "Unterburg"),
            plz=("42659",),
        ),
        District(
            "ohligs-aufderhoehe-merscheid",
            "Ohligs/Aufderhöhe/Merscheid",
            aliases=("Ohligs", "Aufderhöhe", "Aufderhoehe", "Merscheid"),
            plz=("42697", "42699"),
        ),
    ),
}

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _key(value: str) -> str:
    """Сравнимая форма: регистр, умлауты, разделители «-»/«/»/пробелы схлопнуты."""
    text = (value or "").strip().casefold().translate(_UMLAUTS)
    return re.sub(r"[\s/_-]+", "-", text).strip("-")


def city_key(city: str) -> str:
    """Ключ города реестра или "". «Solingen-Ohligs» → solingen (первая часть)."""
    key = _key(city)
    if key in CITIES:
        return key
    head = key.split("-", 1)[0]
    return head if head in CITIES else ""


def districts_for(city: str) -> tuple[District, ...]:
    return CITIES.get(city_key(city), ())


def choices_for(city: str) -> list[tuple[str, str]]:
    return [(d.slug, d.name) for d in districts_for(city)]


def normalize(city: str, value: str) -> str:
    """slug, название или алиас района → slug; незнакомое → ""."""
    want = _key(value)
    if not want:
        return ""
    for d in districts_for(city):
        if want == d.slug or want == _key(d.name) or want in {_key(a) for a in d.aliases}:
            return d.slug
    # «Solingen-Ohligs» в поле района — отрезать город
    prefix = city_key(city)
    if prefix and want.startswith(prefix + "-"):
        return normalize(city, want[len(prefix) + 1 :])
    return ""


def label(city: str, slug: str) -> str:
    for d in districts_for(city):
        if d.slug == slug:
            return d.name
    return ""


def suggest(city: str, address: str) -> str:
    """Район по индексу в адресе (только уверенные PLZ реестра) или ""."""
    for plz in re.findall(r"\b(\d{5})\b", address or ""):
        for d in districts_for(city):
            if plz in d.plz:
                return d.slug
    return ""
