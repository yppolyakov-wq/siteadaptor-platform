"""FB-19: поле «Stadt» — подсказки городов и каноническое написание.

Поле остаётся текстовым (малый город не теряется), но подсказывает города, а знакомое
название сервер приводит к официальному написанию («köln» → «Köln», «leichlingen» →
«Leichlingen (Rheinland)»). Германия — ВСЕ муниципалитеты (FB-19b, 10 443 названия,
static/data/gemeinden_de.json из Gemeindeverzeichnis Destatis — scripts/build_gemeinden.py,
© Statistisches Bundesamt (Destatis)); Австрия/Швейцария — крупные города списком ниже.

Без JS браузер подсказывает короткий список (города порталов, Bergisches Land, крупнейшие
города); со скриптом static/js/city-suggest.js — поиск по всему списку при вводе.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from django import forms
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

logger = logging.getLogger(__name__)

#: Bergisches Land / Kreis Mettmann — пилотный регион (Solingen и соседи).
REGION = (
    "Solingen",
    "Wuppertal",
    "Remscheid",
    "Haan",
    "Hilden",
    "Leichlingen (Rheinland)",
    "Langenfeld (Rheinland)",
    "Wermelskirchen",
    "Burscheid",
    "Monheim am Rhein",
    "Erkrath",
    "Mettmann",
    "Wülfrath",
    "Heiligenhaus",
    "Velbert",
    "Ratingen",
    "Radevormwald",
    "Hückeswagen",
    "Bergisch Gladbach",
    "Leverkusen",
)

#: Größte Städte in Österreich und der Schweiz.
AUSTRIA_SWITZERLAND = (
    "Wien", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt am Wörthersee",
    "Villach", "Wels", "St. Pölten", "Dornbirn",
    "Zürich", "Genf", "Basel", "Lausanne", "Bern", "Winterthur", "Luzern", "St. Gallen",
    "Lugano", "Biel/Bienne",
)  # fmt: skip

_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _key(value: str) -> str:
    return " ".join((value or "").casefold().translate(_FOLD).split())


DATA = Path(settings.BASE_DIR) / "static" / "data" / "gemeinden_de.json"
#: сколько крупнейших городов Германии в списке без JS
TOP = 60


@lru_cache(maxsize=1)
def _germany() -> tuple[str, ...]:
    """Все муниципалитеты Германии по убыванию населения ("" при отсутствии файла)."""
    try:
        return tuple(name for name, _pop in json.loads(DATA.read_text("utf-8"))["items"])
    except (OSError, ValueError, KeyError):
        logger.exception("gemeinden_de.json unreadable")
        return ()


def _short(name: str) -> str:
    """«Leichlingen (Rheinland)» / «Cottbus/Chóśebuz» → ключ без уточнения."""
    return _key(name.split(" (", 1)[0].split("/", 1)[0])


@lru_cache(maxsize=1)
def _index() -> tuple[dict, dict]:
    exact: dict[str, str] = {}
    short: dict[str, set] = {}
    for name in (*REGION, *_germany(), *AUSTRIA_SWITZERLAND):
        exact.setdefault(_key(name), name)
        short.setdefault(_short(name), set()).add(name)
    unique = {k: next(iter(v)) for k, v in short.items() if len(v) == 1}
    return exact, unique


def suggestions() -> list[str]:
    """Короткий список без JS: города порталов и реестра районов, Bergisches Land,
    крупнейшие города Германии, Австрия/Швейцария; без дублей."""
    try:
        from apps.tenants.quickstart import known_cities

        live = known_cities()
    except Exception:  # noqa: BLE001 — подсказки не роняют форму
        live = []
    seen, out = set(), []
    for name in (*live, *REGION, *_germany()[:TOP], *AUSTRIA_SWITZERLAND):
        k = _key(name)
        if k and k not in seen:
            seen.add(k)
            out.append(name)
    return out


def canonical(value: str) -> str:
    """Знакомый город → официальное написание; незнакомый или неоднозначный («Oldenburg»
    — их несколько) — как ввёл (пробелы сжаты)."""
    text = " ".join((value or "").split())
    if not text:
        return ""
    exact, unique = _index()
    return exact.get(_key(text)) or unique.get(_short(text)) or text


class CityInput(forms.TextInput):
    """Текстовое поле города + `<datalist>` подсказок сразу за ним (шаблоны не трогаем)."""

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_attrs = context["widget"]["attrs"]
        widget_attrs.setdefault("autocomplete", "address-level2")
        widget_attrs["list"] = f"{widget_attrs.get('id') or name}-cities"
        widget_attrs["data-city-suggest"] = static("data/gemeinden_de.json")
        return context

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        list_id = f"{(attrs or {}).get('id') or self.attrs.get('id') or name}-cities"
        options = format_html_join("", '<option value="{}">', ((c,) for c in suggestions()))
        return format_html(
            '{}<datalist id="{}">{}</datalist><script src="{}" defer></script>',
            html,
            list_id,
            options,
            static("js/city-suggest.js"),
        )
