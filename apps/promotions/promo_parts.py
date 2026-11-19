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
OFFER_HOST = "promo_detail"  # общая схема страницы акции
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


def detail_parts(cfg, own_style: str, site_default: str, host: str = "") -> pp.Parts:
    """Вид строки «Angebot» детали акции (витрина и панель читают одно правило, план P3
    §4.3): свои блоки акции `host` («nur diese») → свой шаблон акции → строка общей схемы
    страницы акции → дефолт сайта. Без БД: объект передаёт свой `page_style`."""
    from . import group_styles

    blocks = (cfg.get("page_blocks") or {}) if isinstance(cfg, dict) else {}
    if not isinstance(blocks, dict):  # сырой конфиг черновика может быть битым
        blocks = {}
    from apps.core.page_axes_migration import is_objects_blind, read_old

    # FB-31.7 B1b-2: сверка переноса смотрит вид без своего кода акции (как после B3)
    own = "" if is_objects_blind() else group_styles.promotion_detail_style(own_style, "")
    if own:
        parts = pp.from_code(PROMO_DETAIL, own)
    else:
        # FB-31.7 B3b: дефолт сайта (старый ключ) не читается — вид держит строка «Angebot»
        site_code = group_styles.promotion_detail_style("", read_old(site_default))
        parts = pp.effective_rows(PROMO_DETAIL, blocks.get(OFFER_HOST), code=site_code)
    if host and blocks.get(host):
        parts = pp.effective_rows(
            PROMO_DETAIL, blocks[host], code=pp.legacy_code(PROMO_DETAIL, parts)
        )
    return parts


def group_parts(cfg, key: str) -> pp.Parts:
    """FB-31 P3 R6: вид страницы группы акций `key` — тем же правилом, что деталь акции:
    свои блоки группы («nur diese») → свой шаблон группы (`promo_groups[key].style`) →
    строки «Alle Angebotsgruppen» → дефолт сайта (`site_defaults.promo_group_style`)."""
    from apps.tenants import siteconfig

    from . import group_styles

    cfg = cfg if isinstance(cfg, dict) else {}
    blocks = cfg.get("page_blocks") or {}
    if not isinstance(blocks, dict):
        blocks = {}
    sd = cfg.get("site_defaults") or {}
    from apps.core.page_axes_migration import is_objects_blind, read_old

    own = "" if is_objects_blind() else group_styles.group_style(key, cfg.get("promo_groups"), "")
    if own:
        parts = pp.from_code(PROMO_GROUP, own)
    else:
        site_code = group_styles.group_style("", None, read_old(sd.get("promo_group_style", "")))
        parts = pp.effective_rows(PROMO_GROUP, blocks.get("promo_group"), code=site_code)
    host = siteconfig.promo_group_host(key)
    if host and blocks.get(host):
        parts = pp.effective_rows(
            PROMO_GROUP, blocks[host], code=pp.legacy_code(PROMO_GROUP, parts)
        )
    return parts
