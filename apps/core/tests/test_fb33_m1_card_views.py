"""FB-33 M1: вид списка решает, какие формы карточки у него есть.

У сетки и ленты (и у Spotlight/баннера акций, решение владельца 2026-11-19) — плитки
и строки; у прайс-листов и строк акций своей карточки нет — поля «Kartenform» нет.
"""

import inspect

import pytest
from django.test import RequestFactory

from apps.core import card_forms, list_panel
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

CARD_SOURCES = [s for s, spec in siteconfig.LIST_SOURCES.items() if spec["card"]]


def test_every_style_of_a_card_source_is_classified():
    """Новый вид у источника с карточкой без строки в VIEW_SHAPES — тихо «сетка»."""
    styles = (
        {style for src in CARD_SOURCES for style in siteconfig.list_styles(src)}
        | set(siteconfig.SECTION_STYLES["products"])
        | set(siteconfig.SECTION_STYLES["promotions"])
    )
    assert styles <= set(card_forms.VIEW_SHAPES)


def test_every_form_has_a_shape_and_row_forms_exist():
    keys = {key for key, *_rest in card_forms.CARD_FORMS}
    assert card_forms.ROW_FORMS <= keys
    assert {card_forms.shape_of(k) for k in keys} == {card_forms.SHAPE_TILE, card_forms.SHAPE_ROW}


def test_card_forms_does_not_import_siteconfig():
    assert "import siteconfig" not in inspect.getsource(card_forms)


@pytest.mark.parametrize("kind", (card_forms.PRODUCT, card_forms.PROMO))
@pytest.mark.parametrize("style", sorted(card_forms.VIEW_SHAPES))
def test_forms_for_view_is_a_subset(kind, style):
    allowed = card_forms.forms_for_view(style, kind)
    assert set(allowed) <= set(card_forms.forms_for(kind))
    assert bool(allowed) == card_forms.view_has_card(style)


def test_grid_slider_spotlight_banner_keep_rows():
    for style in ("", "spotlight", "banner", None, "unknown"):
        keys = {k for k, *_ in card_forms.forms_for_view(style, card_forms.PROMO)}
        assert "deal" in keys and "" in keys


@pytest.mark.parametrize("style", ("rows", "preisliste", "preisliste_buch"))
def test_cardless_views(style):
    assert not card_forms.view_has_card(style)
    assert card_forms.normalize_for_view(style, card_forms.PRODUCT, "deal") == ""


@pytest.mark.parametrize(
    ("style", "kind", "card", "expected"),
    (
        ("", card_forms.PRODUCT, "deal", "deal"),
        ("", card_forms.PRODUCT, "compact", "compact"),
        ("", card_forms.PROMO, "compact", ""),  # не форма акций
        ("spotlight", card_forms.PROMO, "coupon", "coupon"),
        ("", card_forms.PRODUCT, "garbage", ""),
        ("rows", card_forms.PROMO, "deal", ""),
    ),
)
def test_normalize_for_view(style, kind, card, expected):
    got = card_forms.normalize_for_view(style, kind, card)
    assert got == expected
    assert card_forms.normalize_for_view(style, kind, got) == got  # идемпотентно


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("source", "style", "has_card"),
    (
        ("products", "", True),
        ("products", "preisliste_foto_2sp", False),
        ("promotions", "", True),
        ("promotions", "spotlight", True),
        ("promotions", "banner", True),
        ("promotions", "rows", False),
        ("categories", "", False),
    ),
)
def test_panel_shows_card_form_only_where_it_works(source, style, has_card):
    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build(business_type="retail", site_config={})
    groups = list_panel.groups(request, {}, {"source": source, "style": style})
    names = {f["name"] for g in groups for f in g["fields"]}
    assert ("card" in names) is has_card


def test_studio_row_hides_card_form_on_cardless_view():
    """Строка «Liste» в Студии: подпись видов без карточки приходит в подсказке, строка
    «Kartenform» скрыта сразу (сервер) и при смене вида (JS, стенд m1_js_stand)."""
    import pathlib

    from apps.core import list_blocks

    hint = list_blocks.view_hint({}, {"source": "products"})
    assert {"rows", "preisliste"} <= set(hint["cardless_styles"].split())
    assert "spotlight" not in hint["cardless_styles"].split()
    row = pathlib.Path("templates/tenant/_cb_row.html").read_text(encoding="utf-8")
    assert 'data-lb-cardless="{{ lh.cardless_styles }}"' in row and "data-lb-style" in row
    js = pathlib.Path("templates/tenant/site_home.html").read_text(encoding="utf-8")
    assert 't.matches("[data-lb-style]")' in js and "[data-lb-cardless]" in js


@pytest.mark.parametrize(
    ("data", "card"),
    (
        ({"source": "products", "style": "preisliste", "card": "deal"}, None),
        ({"source": "promotions", "style": "rows", "card": "coupon"}, None),
        ({"source": "promotions", "style": "spotlight", "card": "coupon"}, "coupon"),
        ({"source": "promotions", "style": "banner", "card": "deal"}, "deal"),
        ({"source": "products", "card": "deal", "out": "slider"}, "deal"),
        ({"source": "products", "style": "bogus", "card": "compact"}, "compact"),
        ({"source": "categories", "card": "deal"}, None),
    ),
)
def test_saving_drops_a_form_the_view_does_not_have(data, card):
    """M1c: вид побеждает — у прайс-листа и строк акций форма не хранится."""
    cleaned = siteconfig._clean_list_block(data)
    assert cleaned.get("card") == card
    assert siteconfig._clean_list_block(cleaned) == cleaned  # идемпотентно


def test_price_list_with_old_deal_form_keeps_its_columns():
    """Раньше «deal» у прайс-листа ужимал колонки до двух — теперь формы нет, колонки свои."""
    from apps.core import list_blocks

    data = siteconfig._clean_list_block(
        {"source": "products", "style": "preisliste_foto_3sp", "card": "deal", "cols": 3}
    )
    assert list_blocks.effective_view({}, data)["layout"]["cols"] == 3
