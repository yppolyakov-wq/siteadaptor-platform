"""FB-26: «Was verkaufen Sie?» при регистрации — направления обязательны, ниша — нет.

Решения владельца 2026-11-08 (`docs/fb26-simple-site-creation-plan-2026-11-07.md` §4):
1. Первый вопрос — направления (мультивыбор), второй — ниша, необязательно.
2. Направления выбрать ОБЯЗАТЕЛЬНО: без них не понять, отель это или магазин.
3. У ниши остаётся «Demo ansehen».

Направления регистрации — шесть чипов поверх реестра `apps.core.directions`
(«Speisen & Getränke» = Speisekarte + Tisch). Ниша — данные (тексты, образцы, вид);
модули включают направления. Пустая ниша выводится из направлений только там, где
вывод однозначен (гастро → ресторан, только номера → отель, только билеты → события),
иначе `other`.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.utils.translation import gettext_lazy as _

#: (ключ, иконка, подпись, подсказка) — порядок чипов на странице.
CHOICES: tuple[tuple[str, str, str, str], ...] = (
    ("waren", "🛍️", _("Produkte"), _("Zum Abholen, Liefern oder Versenden.")),
    ("termine", "📅", _("Termine & Dienstleistungen"), _("Kunden buchen eine Uhrzeit.")),
    ("zimmer", "🛏️", _("Zimmer & Übernachtung"), _("Gäste buchen Nächte.")),
    ("tickets", "🎟️", _("Tickets & Touren"), _("Plätze für Termine mit Datum.")),
    ("anfragen", "📝", _("Anfragen & Aufträge"), _("Kunden fragen an, Sie schicken ein Angebot.")),
    ("gastro", "🍽️", _("Speisen & Getränke"), _("Speisekarte und Tischreservierung.")),
)
KEYS: tuple[str, ...] = tuple(c[0] for c in CHOICES)

#: Чип регистрации → направления реестра.
_EXPAND = {"gastro": ("speisekarte", "tisch")}

#: Ниша по единственному направлению, когда её не выбрали (однозначные случаи).
_INFER = {"zimmer": "hotel", "tickets": "events"}

#: Направления, чьи модули выключаются, если их НЕ отметили. «Waren» не трогаем:
#: онлайн-продажу открывает шаг «Verkauf öffnen», каталог — базовый.
_SWITCHABLE = ("termine", "tisch", "zimmer", "tickets", "anfragen")


def clean(keys) -> list[str]:
    """Только известные чипы, без дублей, в порядке страницы."""
    picked = {k for k in keys or () if isinstance(k, str)}
    return [k for k in KEYS if k in picked]


def resolve_type(niche: str, chips) -> str:
    """Тип бизнеса: выбранная ниша, иначе вывод из направлений, иначе `other`."""
    if niche and niche != "other":
        return niche
    chips = clean(chips)
    if "gastro" in chips:
        return "restaurant"
    if len(chips) == 1 and chips[0] in _INFER:
        return _INFER[chips[0]]
    return niche or "other"


def directions_for(business_type: str, chips) -> list[str]:
    """Ключи реестра для типа: «gastro» раскрыт, неуместные типу отброшены (Tisch у кафе)."""
    from apps.core import directions

    allowed = {d.key for d in directions.choices_for(SimpleNamespace(business_type=business_type))}
    out: list[str] = []
    for chip in clean(chips):
        for key in _EXPAND.get(chip, (chip,)):
            if key in allowed and key not in out:
                out.append(key)
    return out


def disabled_modules(business_type: str, chosen: list[str]) -> list[str]:
    """Стартовый `disabled_modules`: дефолт типа, модули отмеченных направлений включены,
    неотмеченных — выключены (общий модуль держит отмеченное направление)."""
    from apps.core import directions, modules

    disabled = set(modules.default_disabled_for(business_type))
    keep = set()
    for key in chosen:
        d = directions.get(key)
        if d and key != "waren":
            keep.update(d.modules)
    for key in _SWITCHABLE:
        d = directions.get(key)
        if d and key not in chosen:
            disabled.update(m for m in d.modules if m not in keep)
    disabled -= keep
    return sorted(disabled)


def initial_for(business_type: str) -> list[str]:
    """Предвыбор чипов по нише (пришли с Branchen-страницы `?type=`)."""
    from apps.core import directions

    out = []
    for key in directions.defaults_for(business_type):
        chip = "gastro" if key in ("speisekarte", "tisch") else key
        if chip not in out:
            out.append(chip)
    return clean(out)


def niche_chips(business_type: str) -> str:
    """Чипы, которые подходят нише, — пробелами (атрибут карточки для фильтра на странице)."""
    return " ".join(initial_for(business_type))
