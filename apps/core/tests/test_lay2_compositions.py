"""LAY-2 — единый реестр композиций («шаблонов страницы»).

Решение владельца 2026-09-09: полная унификация видов вывода. Первый шаг —
свести ЧЕТЫРЕ реестра шаблонов страницы (товарная категория, корень каталога,
обзор акций, группа акций, деталь акции) к одному источнику; прежние реестры
остаются как ПРОИЗВОДНЫЕ представления, чтобы витрина и формы не менялись
(прецедент — HUB_TABS, производные от `nav_registry`, волна W8).

Эти замки — характеризационные: они фиксируют СЕГОДНЯШНИЙ состав и порядок
кодов и краснеют, если слияние что-то потеряет или переставит. План —
`docs/lay-unified-output-plan-2026-09-09.md §10`.
"""

import pytest

# Снимок ДО слияния: коды в том порядке, в каком их видит владелец в плитках.
CATEGORY_CODES = [
    "",
    "kopfbild",
    "sets",
    "preisliste",
    "regale",
    "tabs",
    "schaufenster",
    "navigator",
    "magazin",
    "mosaik",
    "kompakt",
]
ROOT_CODES = [c for c in CATEGORY_CODES if c != "preisliste"]
PROMO_PAGE_CODES = [
    "",
    "kopfbild",
    "preisliste",
    "regale",
    "tabs",
    "schaufenster",
    "navigator",
    "magazin",
    "kompakt",
]
GROUP_CODES = ["", "schaufenster", "prospekt", "magazin", "countdown", "vergleich"]
PROMO_DETAIL_CODES = ["", "plakat", "prospekt", "kompakt", "magazin"]


def _codes(registry):
    return [entry[0] for entry in registry]


def test_category_registry_keeps_its_codes_and_order():
    from apps.catalog import category_styles

    assert _codes(category_styles.CATEGORY_PAGE_STYLES) == CATEGORY_CODES


def test_root_registry_keeps_its_codes_and_order():
    from apps.catalog import category_styles

    assert _codes(category_styles.root_styles()) == ROOT_CODES


def test_promo_overview_registry_keeps_its_codes_and_order():
    from apps.promotions import group_styles

    assert _codes(group_styles.PROMO_PAGE_STYLES) == PROMO_PAGE_CODES


def test_promo_group_registry_keeps_its_codes_and_order():
    from apps.promotions import group_styles

    assert _codes(group_styles.GROUP_PAGE_STYLES) == GROUP_CODES


def test_promo_detail_registry_keeps_its_codes_and_order():
    from apps.promotions import group_styles

    assert _codes(group_styles.PROMOTION_DETAIL_STYLES) == PROMO_DETAIL_CODES


@pytest.mark.parametrize(
    "getter",
    [
        lambda: __import__("apps.catalog.category_styles", fromlist=["x"]).CATEGORY_PAGE_STYLES,
        lambda: __import__("apps.catalog.category_styles", fromlist=["x"]).root_styles(),
        lambda: __import__("apps.promotions.group_styles", fromlist=["x"]).PROMO_PAGE_STYLES,
        lambda: __import__("apps.promotions.group_styles", fromlist=["x"]).GROUP_PAGE_STYLES,
        lambda: __import__("apps.promotions.group_styles", fromlist=["x"]).PROMOTION_DETAIL_STYLES,
    ],
)
def test_every_entry_is_a_triple_with_label_and_hint(getter):
    """Форма записи — та же тройка (код, метка, подсказка): её читают шаблоны плиток."""
    for entry in getter():
        assert len(entry) == 3, entry
        code, label, hint = entry
        assert isinstance(code, str)
        assert str(label).strip(), f"пустая метка у кода {code!r}"
        assert str(hint).strip(), f"пустая подсказка у кода {code!r}"


# ── Единый реестр: то, ради чего волна ───────────────────────────────────────


def test_single_registry_exists_and_covers_every_code():
    """Один источник композиций; каждый живой код обязан быть в нём."""
    from apps.core import compositions

    known = set(compositions.COMPOSITIONS)
    for codes in (CATEGORY_CODES, PROMO_PAGE_CODES, GROUP_CODES, PROMO_DETAIL_CODES):
        for code in codes:
            assert code in known, f"код {code!r} не описан в едином реестре"


def test_registry_declares_where_each_composition_applies():
    """`applies_to` — гейт доступности: он и заменяет четыре отдельных списка."""
    from apps.core import compositions

    for code, spec in compositions.COMPOSITIONS.items():
        assert spec.applies_to, f"у композиции {code!r} не сказано, где она применима"
        assert spec.applies_to <= compositions.SURFACES, f"чужая поверхность у {code!r}"


def test_shelves_and_tabs_declare_that_they_need_children():
    """Полки и вкладки бессмысленны без под-сущностей — это свойство реестра,
    а не пяти отдельных `if` по шаблонам (правило STU-9)."""
    from apps.core import compositions

    assert compositions.COMPOSITIONS["regale"].needs_children
    assert compositions.COMPOSITIONS["tabs"].needs_children
    assert not compositions.COMPOSITIONS[""].needs_children


def test_derived_views_are_built_from_the_single_registry():
    """Прежние реестры — производные: тот же состав, тот же порядок."""
    from apps.catalog import category_styles
    from apps.core import compositions
    from apps.promotions import group_styles

    assert _codes(compositions.styles_for("category")) == _codes(
        category_styles.CATEGORY_PAGE_STYLES
    )
    assert _codes(compositions.styles_for("catalog")) == _codes(category_styles.root_styles())
    assert _codes(compositions.styles_for("promos")) == _codes(group_styles.PROMO_PAGE_STYLES)
    assert _codes(compositions.styles_for("promo_group")) == _codes(group_styles.GROUP_PAGE_STYLES)
    assert _codes(compositions.styles_for("promo")) == _codes(group_styles.PROMOTION_DETAIL_STYLES)
