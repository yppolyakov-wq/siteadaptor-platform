"""DL-20: реестр шаблонов СТРАНИЦЫ ГРУППЫ АКЦИЙ (`/aktionen/?gruppe=<группа>`).

До этой волны страницы группы фактически не было: фильтр по группе отдавал плоскую
сетку под общим заголовком «Aktuelle Angebote», и посетитель, пришедший по ссылке из
меню, не видел даже названия того, что открыл.

Механика — копия DL-19/DL-20 для товарной категории, но хранение другое: **модели
группы не существует**, `Promotion.group` — свободный текст. Поэтому выбор «только
для этой группы» живёт в `site_config["promo_groups"] = {<группа>: <стиль>}`
(ключ = то же плоское значение, что и у фасета `?gruppe=`), а общий дефолт — в
`site_defaults["promo_group_style"]`. Оба presence-minimal → golden-эталоны целы,
миграций нет.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# (код, метка, подсказка «когда уместно»). Порядок = порядок плиток выбора.
GROUP_PAGE_STYLES = [
    ("", _("Standard (grid)"), _("As before: a plain grid of all offers in the group.")),
    (
        "schaufenster",
        _("Showcase"),
        _("Group header and the main deal as a wide card, the rest as a grid."),
    ),
    (
        "prospekt",
        _("Flyer"),
        _("Coloured header with the validity period and a dense grid — like a leaflet."),
    ),
    (
        "magazin",
        _("Magazine"),
        _("Cover, two offers per row, conditions right on the card."),
    ),
    (
        "countdown",
        _("Countdown"),
        _("One timer for the whole campaign, offers sorted by time left."),
    ),
    (
        "vergleich",
        _("Comparison"),
        _("Offers side by side as columns — for packages and tariffs."),
    ),
]
VALID_GROUP_STYLES = frozenset(code for code, _l, _h in GROUP_PAGE_STYLES)


def group_style(group: str, per_group=None, site_default: str = "") -> str:
    """Эффективный шаблон страницы группы: свой у группы → дефолт сайта → Standard.

    Правило приоритета то же, что у форм карточки и шаблона категории. Неизвестный
    ключ в любом слое → "" (прежняя плоская сетка), а не 500: имя группы —
    свободный текст, и переименование в форме акции осиротит запись словаря.
    """
    own = ((per_group or {}).get(group or "") or "").strip()
    if own in VALID_GROUP_STYLES and own:
        return own
    site_default = (site_default or "").strip()
    return site_default if site_default in VALID_GROUP_STYLES else ""


# ── DL-21.2: ОБЗОРНАЯ страница `/aktionen/` ────────────────────────────────────
# Шесть стилей категории ложатся на акции именно здесь: «подкатегории» обзора —
# группы, «товары» — акции. У страницы группы (выше) под-сущностей нет — там DL-20.
# Без «sets» (у акций нет наборов) и без «mosaik» (бенто режет цену/срок на малых
# плитках — честнее не обещать).
PROMO_PAGE_STYLES = [
    ("", _("Standard (grid)"), _("As before: groups as sections, offers as a grid.")),
    ("kopfbild", _("Mit Kopfbild"), _("Banner with photo and counts above the sections.")),
    (
        "preisliste",
        _("Preisliste"),
        _("Offers as a table by default — visitors can switch to cards."),
    ),
    (
        "regale",
        _("Regale (Unterkategorien als Leisten)"),
        _("Every group as a strip with arrows, no minimum size."),
    ),
    (
        "tabs",
        _("Tabs (Unterkategorien als Reiter)"),
        _("«All» plus one tab per group above the offers."),
    ),
    (
        "schaufenster",
        _("Showcase"),
        _("The main deal as a wide card, then the sections."),
    ),
    (
        "navigator",
        _("Navigator"),
        _("Groups, filters and search in a side column, offers on the right."),
    ),
    ("magazin", _("Magazine"), _("Two offers per row with their conditions.")),
    ("kompakt", _("Compact"), _("Group index in columns and a dense grid without sections.")),
]
VALID_PROMO_PAGE_STYLES = frozenset(code for code, _l, _h in PROMO_PAGE_STYLES)


def promo_page_style(raw) -> str:
    """Шаблон обзорной страницы акций (`site_config["promo_page_style"]`); мусор → ""."""
    code = (raw or "").strip() if isinstance(raw, str) else ""
    return code if code in VALID_PROMO_PAGE_STYLES and code else ""
