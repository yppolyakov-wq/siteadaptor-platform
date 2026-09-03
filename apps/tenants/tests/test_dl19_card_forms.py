"""DL-19.1 — реестр форм карточки + приоритет «своя у объекта > дефолт сайта».

Замки написаны ДО веток разметки: сначала фиксируем правило выбора формы и
паритет («" " = прежняя карточка»), потом добавляем сами формы.
"""

from __future__ import annotations

import pytest
from django.template import Context, Template

from apps.catalog.tests.factories import ProductFactory
from apps.core import card_forms
from apps.promotions.models import Promotion
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _resolved(entity, kind, site_default):
    ctx_key = "storefront_promo_card" if kind == "promo" else "storefront_card_style"
    tpl = Template("{% load siteui %}{% card_form p kind as cs %}{{ cs }}")
    return tpl.render(Context({"p": entity, "kind": kind, ctx_key: site_default}))


# --- реестр --------------------------------------------------------------------
def test_registry_kinds_are_disjointly_gated():
    prod, promo = card_forms.keys_for("product"), card_forms.keys_for("promo")
    # общие формы канваса доступны обоим видам
    assert {"regal", "lookbook", "deal"} <= prod & promo
    # «купон» и «кольцо» держатся на данных акции (номинал, срок) — товару их нет
    assert {"coupon", "ring"} <= promo and not {"coupon", "ring"} & prod
    # прежние формы товара не переезжают в акцию (у неё своя ветка «preis»)
    assert {"overlay", "compact", "etikett"} <= prod and "preis" in promo
    assert "" not in prod and "" not in promo  # пустой ключ = «форма не задана»
    assert [k for k, *_ in card_forms.forms_for("promo")][0] == ""  # Standard первым


# --- приоритет -----------------------------------------------------------------
def test_own_form_beats_site_default():
    p = ProductFactory(card_style="regal")
    assert card_forms.card_form(p, "overlay", "product") == "regal"
    assert _resolved(p, "product", "overlay") == "regal"


def test_empty_own_falls_back_to_site_default():
    p = ProductFactory()
    assert card_forms.card_form(p, "compact", "product") == "compact"
    assert _resolved(p, "product", "compact") == "compact"
    assert card_forms.card_form(p, "", "product") == ""


def test_unknown_values_degrade_to_the_previous_form():
    """Мусор в любом слое → прежняя карточка, а не 500 (правило option_styles)."""
    p = ProductFactory(card_style="haha")
    assert card_forms.card_form(p, "regal", "product") == "regal"  # своё невалидно → сайт
    assert card_forms.card_form(p, "quatsch", "product") == ""
    # форма акции товару не подходит и наоборот — вид сущности гейтит
    assert card_forms.card_form(ProductFactory(card_style="coupon"), "", "product") == ""
    promo = Promotion.objects.create(
        title={"de": "X"}, status="active", promo_type="discount", card_style="overlay"
    )
    assert card_forms.card_form(promo, "", "promo") == ""
    assert _resolved(promo, "promo", "") == ""


def test_promo_own_form_beats_site_default():
    promo = Promotion.objects.create(
        title={"de": "X"}, status="active", promo_type="discount", card_style="coupon"
    )
    assert _resolved(promo, "promo", "preis") == "coupon"


def test_stub_entities_without_the_field_still_render():
    """Секции главной рендерят карточки стабами-SimpleNamespace — getattr с фолбэком."""
    from types import SimpleNamespace

    assert card_forms.card_form(SimpleNamespace(), "regal", "product") == "regal"


# --- конфиг сайта ---------------------------------------------------------------
def test_normalize_accepts_new_forms_and_stays_presence_minimal():
    sd = siteconfig.normalize({"site_defaults": {"card_style": "regal", "promo_card": "coupon"}})[
        "site_defaults"
    ]
    assert sd["card_style"] == "regal" and sd["promo_card"] == "coupon"
    # форма акции не принимается как форма товара (и наоборот) + мусор дропается
    sd = siteconfig.normalize({"site_defaults": {"card_style": "coupon", "promo_card": "overlay"}})[
        "site_defaults"
    ]
    assert "card_style" not in sd and "promo_card" not in sd
    assert "card_style" not in siteconfig.normalize({})["site_defaults"]
