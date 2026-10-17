"""T-8.17: реестр районов городов (план docs/t8-15-districts-portal-plan-2026-10-09.md).

Район бизнеса — выбор из справочника, а не свободный текст: иначе «Ohligs»,
«Solingen-Ohligs» и «ohligs» стали бы тремя районами (та же каша, что с городом,
дыра A6). Хранение — slug района в ``Tenant.district`` и ``AggregatorListing.district``.

PLZ — только ПОДСКАЗКА при заполнении: в Solingen индексы с районами совпадают не
один к одному, поэтому здесь лишь уверенные индексы, остальное владелец выбирает сам.
"""

from __future__ import annotations

import functools
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

# Г5: соседние Stadtbezirke (общая граница) — откуда брать «Auch in der Nähe», когда в
# районе мало бизнесов. Порядок = кого показывать первым. Явный список, а не расстояние по
# координатам: координаты есть не у всех, а подпись «aus Mitte» обязана быть стабильной.
NEIGHBORS: dict[str, dict[str, tuple[str, ...]]] = {
    "solingen": {
        "graefrath": ("wald", "mitte"),
        "wald": ("graefrath", "mitte", "ohligs-aufderhoehe-merscheid"),
        "mitte": ("graefrath", "wald", "burg-hoehscheid", "ohligs-aufderhoehe-merscheid"),
        "burg-hoehscheid": ("mitte", "ohligs-aufderhoehe-merscheid"),
        "ohligs-aufderhoehe-merscheid": ("wald", "mitte", "burg-hoehscheid"),
    },
}

# Как город пишется для людей (ключ реестра → название).
CITY_NAMES: dict[str, str] = {"solingen": "Solingen"}

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


_DIACRITICS = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def toponym_tokens(city: str) -> frozenset[str]:
    """T-8.26 п.4: слова-топонимы (город, районы, алиасы) в ОБЕИХ свёртках — «ö→oe» (как
    `_key`) и «ö→o» (как `aggregator.search.fold`). Фолбэк опечаток исключает их из
    значимых слов запроса: «Friseur in Solingen-Wald» ищет парикмахера, а не всё
    «Solingen…». Пустой город → объединение по реестру (главный домен без `?city=`);
    город ЕСТЬ, но вне реестра → пусто (иначе «Burg»/«Wald» в Хильдене молча пропадали бы)."""
    return _toponym_tokens(city_key(city) if (city or "").strip() else None)


@functools.lru_cache(maxsize=64)
def _toponym_tokens(key: str | None) -> frozenset[str]:
    if key == "":
        return frozenset()
    keys = [key] if key else list(CITIES)
    out: set[str] = set()
    for key in keys:
        words = [key, CITY_NAMES.get(key, "")]
        for d in CITIES[key]:
            words += [d.slug, d.name, *d.aliases]
        for w in words:
            for part in re.split(r"[\s/_-]+", w or ""):
                if part:
                    out.add(_key(part))
                    out.add(part.casefold().translate(_DIACRITICS))
    return frozenset(out)


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


def neighbors(city: str, slug: str) -> tuple[str, ...]:
    """Г5: соседние районы по реестру; город вне реестра или незнакомый slug → ()."""
    return NEIGHBORS.get(city_key(city), {}).get(slug or "", ())


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


def city_label(city: str) -> str:
    """Каноническое название города реестра («solingen» → «Solingen») или ""."""
    key = city_key(city)
    return CITY_NAMES.get(key, key.title()) if key else ""


def all_options() -> list[dict]:
    """Все районы всех городов реестра — для формы, где город выбирается рядом
    (T-8.5c): {city_key, city, slug, name}."""
    return [
        {"city_key": key, "city": CITY_NAMES.get(key, key.title()), "slug": d.slug, "name": d.name}
        for key, items in CITIES.items()
        for d in items
    ]
