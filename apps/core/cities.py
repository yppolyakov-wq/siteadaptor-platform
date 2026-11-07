"""FB-19: поле «Stadt» — подсказки городов и каноническое написание.

Поле остаётся текстовым (малый город не теряется), но браузер подсказывает города из
списка (`<datalist>`), а знакомое название сервер приводит к правильному написанию
(«köln» → «Köln», «duesseldorf» → «Düsseldorf»). Источники по порядку: города
действующих порталов и реестра районов (`quickstart.known_cities`), затем Städte DACH от
~50 000 жителей и Bergisches Land вокруг Solingen. Полный список муниципалитетов
(~11 000, Destatis GV-ISys) — следующим шагом (docs/fb-feedback-batch-2026-11-07.md).
"""

from __future__ import annotations

from functools import lru_cache

from django import forms
from django.utils.html import format_html, format_html_join

#: Bergisches Land / Kreis Mettmann — пилотный регион (Solingen и соседи).
REGION = (
    "Solingen",
    "Wuppertal",
    "Remscheid",
    "Haan",
    "Hilden",
    "Leichlingen",
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

#: Städte in Deutschland ab ~50 000 Einwohnern (amtliche Schreibweise).
GERMANY = (
    "Berlin", "Hamburg", "München", "Köln", "Frankfurt am Main", "Stuttgart",
    "Düsseldorf", "Leipzig", "Dortmund", "Essen", "Bremen", "Dresden", "Hannover",
    "Nürnberg", "Duisburg", "Bochum", "Bielefeld", "Bonn", "Münster", "Mannheim",
    "Karlsruhe", "Augsburg", "Wiesbaden", "Mönchengladbach", "Gelsenkirchen", "Aachen",
    "Braunschweig", "Kiel", "Chemnitz", "Halle (Saale)", "Magdeburg",
    "Freiburg im Breisgau", "Krefeld", "Mainz", "Lübeck", "Erfurt", "Oberhausen",
    "Rostock", "Kassel", "Hagen", "Potsdam", "Saarbrücken", "Hamm",
    "Ludwigshafen am Rhein", "Oldenburg", "Mülheim an der Ruhr", "Osnabrück",
    "Darmstadt", "Heidelberg", "Herne", "Regensburg", "Neuss", "Paderborn",
    "Ingolstadt", "Offenbach am Main", "Fürth", "Würzburg", "Ulm", "Heilbronn",
    "Pforzheim", "Wolfsburg", "Göttingen", "Bottrop", "Reutlingen", "Erlangen",
    "Bremerhaven", "Koblenz", "Trier", "Recklinghausen", "Jena", "Moers", "Salzgitter",
    "Siegen", "Gütersloh", "Hildesheim", "Hanau", "Kaiserslautern", "Cottbus",
    "Schwerin", "Witten", "Esslingen am Neckar", "Ludwigsburg", "Gera", "Iserlohn",
    "Düren", "Tübingen", "Flensburg", "Zwickau", "Gießen", "Lünen", "Konstanz", "Marl",
    "Worms", "Villingen-Schwenningen", "Minden", "Neumünster", "Dessau-Roßlau",
    "Norderstedt", "Delmenhorst", "Bamberg", "Viersen", "Marburg", "Rheine",
    "Wilhelmshaven", "Gladbeck", "Troisdorf", "Lüneburg", "Dorsten", "Detmold",
    "Arnsberg", "Castrop-Rauxel", "Brandenburg an der Havel", "Bayreuth", "Landshut",
    "Lüdenscheid", "Bocholt", "Aschaffenburg", "Celle", "Kempten (Allgäu)", "Fulda",
    "Aalen", "Lippstadt", "Dinslaken", "Herford", "Rüsselsheim am Main", "Kerpen",
    "Weimar", "Neuwied", "Sindelfingen", "Dormagen", "Plauen", "Grevenbroich",
    "Rosenheim", "Neubrandenburg", "Herten", "Bergheim", "Friedrichshafen",
    "Schwäbisch Gmünd", "Garbsen", "Wesel", "Hürth", "Unna", "Offenburg", "Greifswald",
    "Stralsund", "Göppingen", "Euskirchen", "Hameln", "Frankfurt (Oder)", "Görlitz",
    "Meerbusch", "Sankt Augustin", "Waiblingen", "Pulheim", "Baden-Baden", "Eschweiler",
    "Bad Homburg vor der Höhe", "Nordhorn", "Langenhagen", "Bad Salzuflen", "Menden",
    "Gummersbach", "Hattingen", "Wetzlar", "Speyer", "Kleve", "Erftstadt", "Passau",
    "Rastatt", "Lörrach", "Peine", "Emden", "Wolfenbüttel", "Bad Kreuznach", "Ahlen",
    "Elmshorn", "Freising", "Straubing",
)  # fmt: skip

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


@lru_cache(maxsize=1)
def _static() -> tuple[str, ...]:
    seen, out = set(), []
    for name in (*REGION, *GERMANY, *AUSTRIA_SWITZERLAND):
        if _key(name) not in seen:
            seen.add(_key(name))
            out.append(name)
    return tuple(out)


def suggestions() -> list[str]:
    """Города порталов и реестра районов первыми, затем статический список; без дублей."""
    try:
        from apps.tenants.quickstart import known_cities

        live = known_cities()
    except Exception:  # noqa: BLE001 — подсказки не роняют форму
        live = []
    seen, out = set(), []
    for name in (*live, *_static()):
        k = _key(name)
        if k and k not in seen:
            seen.add(k)
            out.append(name)
    return out


def canonical(value: str) -> str:
    """Знакомый город → каноническое написание; незнакомый — как ввёл (пробелы сжаты)."""
    text = " ".join((value or "").split())
    if not text:
        return ""
    k = _key(text)
    for name in suggestions():
        if _key(name) == k:
            return name
    return text


class CityInput(forms.TextInput):
    """Текстовое поле города + `<datalist>` подсказок сразу за ним (шаблоны не трогаем)."""

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_attrs = context["widget"]["attrs"]
        widget_attrs.setdefault("autocomplete", "address-level2")
        widget_attrs["list"] = f"{widget_attrs.get('id') or name}-cities"
        return context

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        list_id = f"{(attrs or {}).get('id') or self.attrs.get('id') or name}-cities"
        options = format_html_join("", '<option value="{}">', ((c,) for c in suggestions()))
        return format_html('{}<datalist id="{}">{}</datalist>', html, list_id, options)
