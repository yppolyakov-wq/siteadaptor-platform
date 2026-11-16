"""FB-31 P3: три страницы акций — оси блоков вместо кода шаблона (`apps/core/page_parts.py`).

Карта кодов — `docs/fb31-p3-promotions-plan-2026-11-16.md` §1:

* обзор `/aktionen/` (`promo_page_style`): шапка `page_head`, навигация групп `groups`,
  вид ★ (`main.style`) и группировка ★ (`main.grouping` = «ohne» — без тематических секций);
* страница группы (`promo_group_style`): шапка `page_head` (Prospekt-лента, Countdown) и вид ★;
* деталь акции (`promo_detail_style`): вид закреплённой строки «Angebot» (`offer`).
"""

from __future__ import annotations

from apps.core import page_parts as pp

HEAD_KEY = "page_head"
GROUPS_KEY = "groups"
OFFER_KEY = "offer"
#: «как обычно» записано в строке явно (как «aus»/«auto» у каталога)
HEAD_OFF = "aus"
GROUPS_AUTO = "auto"
STANDARD = "standard"
FLAT = "ohne"
#: явное «как обычно» у полей ★ — сильнее кода шаблона (как «Raster» у каталога)
RASTER = "raster"
GROUPED = "auto"

PROMOS = pp.surface(
    "promos",
    axes=(
        pp.Axis("head", HEAD_KEY, ("titelbild",), off=HEAD_OFF),
        pp.Axis("groups", GROUPS_KEY, ("regale", "tabs", "index", "side"), off=GROUPS_AUTO),
        pp.Axis(
            "view", pp.MAIN_KEY, ("preisliste", "schaufenster", "magazin", "prospekt"), off=RASTER
        ),
        pp.Axis("grouping", pp.MAIN_KEY, (FLAT,), off=GROUPED, field="grouping"),
    ),
    codes={
        "": {},
        "kopfbild": {"head": "titelbild"},
        "preisliste": {"view": "preisliste"},
        "regale": {"groups": "regale"},
        "tabs": {"groups": "tabs"},
        "schaufenster": {"view": "schaufenster"},
        "navigator": {"groups": "side", "grouping": FLAT},
        "magazin": {"view": "magazin", "grouping": FLAT},
        "kompakt": {"groups": "index", "view": "prospekt", "grouping": FLAT},
    },
    # навигация первой: колонка «Navigator» держится на CSS по коду (`data-promo-page`)
    priority=("groups", "view", "head"),
)

PROMO_GROUP = pp.surface(
    "promo_group",
    axes=(
        pp.Axis("head", HEAD_KEY, ("prospekt", "countdown"), off=STANDARD),
        pp.Axis(
            "view",
            pp.MAIN_KEY,
            ("schaufenster", "prospekt", "magazin", "vergleich", "countdown"),
            off=RASTER,
        ),
    ),
    codes={
        "": {},
        "schaufenster": {"view": "schaufenster"},
        "prospekt": {"head": "prospekt", "view": "prospekt"},
        "magazin": {"view": "magazin"},
        "countdown": {"head": "countdown", "view": "countdown"},
        "vergleich": {"view": "vergleich"},
    },
    priority=("view", "head"),
)

PROMO_DETAIL = pp.surface(
    "promo",
    axes=(pp.Axis("offer", OFFER_KEY, ("plakat", "prospekt", "kompakt", "magazin"), off=STANDARD),),
    codes={
        "": {},
        "plakat": {"offer": "plakat"},
        "prospekt": {"offer": "prospekt"},
        "kompakt": {"offer": "kompakt"},
        "magazin": {"offer": "magazin"},
    },
    priority=("offer",),
)

SURFACES = {s.name: s for s in (PROMOS, PROMO_GROUP, PROMO_DETAIL)}
