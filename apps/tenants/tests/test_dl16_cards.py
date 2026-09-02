"""DL-16.4 — карточки: AK1 «Preis zuerst» (дефолт дил-сборок), P1 «Etikett», P2 листание фото."""

from __future__ import annotations

import pytest
from django.template import Context, Template

from apps.catalog.tests.factories import ProductFactory
from apps.promotions.models import Promotion
from apps.tenants import siteconfig, sitetemplates

pytestmark = pytest.mark.django_db


def _render(tpl, ctx):
    return Template(tpl).render(Context(ctx))


def test_site_defaults_presence_minimal():
    sd = siteconfig.normalize(
        {"site_defaults": {"promo_card": "preis", "card_slider": "on", "card_style": "etikett"}}
    )["site_defaults"]
    assert (
        sd["promo_card"] == "preis" and sd["card_slider"] == "on" and sd["card_style"] == "etikett"
    )
    sd = siteconfig.normalize({"site_defaults": {"promo_card": "x", "card_slider": "off"}})[
        "site_defaults"
    ]
    assert "promo_card" not in sd and "card_slider" not in sd
    assert "promo_card" not in siteconfig.normalize({})["site_defaults"]


def test_deal_bundles_default_to_price_first_and_fokus_do_not():
    for spec in sitetemplates.BUNDLES:
        key = spec["key"]
        cfg = sitetemplates.apply_preview_bundle(siteconfig.normalize({}), key)
        sd = siteconfig.normalize(cfg)["site_defaults"]
        if key.startswith("deal_"):
            assert sd.get("promo_card") == "preis", key
        else:
            assert "promo_card" not in sd, key


def test_promo_card_default_unchanged_and_price_first_form():
    p = Promotion.objects.create(
        title={"de": "OJ"},
        status="active",
        group="Woche",
        discount_percent=20,
        compare_at_price="2.49",
    )
    tpl = '{% include "storefront/_promo_card.html" %}'
    html = _render(tpl, {"p": p, "storefront_promo_card": ""})
    assert "data-promo-price-first" not in html
    assert html.index("data-sf-media-box") < html.index("<h3")
    html = _render(tpl, {"p": p, "storefront_promo_card": "preis"})
    assert "data-promo-price-first" in html and "data-promo-price-block" in html
    # цена ВЫШЕ фото; бейдж — в блоке цены (не absolute); Sie sparen есть; группа видна вне секции
    assert (
        html.index("data-promo-price-block") < html.index("data-sf-media-box") < html.index("<h3")
    )
    assert "!static shrink-0" in html and "data-savings" in html and "data-promo-group" in html
    # широкая карточка «Endet bald» остаётся стандартной формы (CSS wide считает фото первым)
    html = _render(tpl, {"p": p, "storefront_promo_card": "preis", "wide": True})
    assert "data-promo-price-first" not in html and "sf-wide" in html


def test_product_card_etikett_and_default_parity():
    prod = ProductFactory(name={"de": "Saft"}, base_price="1.99", unit="l", content_amount="1")
    tpl = '{% include "storefront/_product_card.html" %}'
    base = _render(tpl, {"p": prod, "storefront_card_style": ""})
    assert "data-price-plate" not in base and 'class="font-bold leading-tight">' in base
    et = _render(tpl, {"p": prod, "storefront_card_style": "etikett"})
    assert "data-price-plate" in et and "1,99" in et
    assert 'class="font-bold leading-tight">' not in et  # строка цены внизу не дублируется


def test_product_card_photo_slider_marker_only_with_option_and_two_photos():
    tpl = '{% include "storefront/_product_card.html" %}'
    two = ProductFactory(
        name={"de": "Jacke"}, base_price="89", images=[{"url": "/a.jpg"}, {"url": "/b.jpg"}]
    )
    one = ProductFactory(name={"de": "Hut"}, base_price="19", images=[{"url": "/c.jpg"}])
    assert 'data-card-imgs="/a.jpg|/b.jpg"' in _render(
        tpl, {"p": two, "storefront_card_slider": "on"}
    )
    assert "data-card-imgs" not in _render(tpl, {"p": two, "storefront_card_slider": ""})
    assert "data-card-imgs" not in _render(tpl, {"p": one, "storefront_card_slider": "on"})


def test_slider_script_has_card_block_and_kits_carry_new_axes():
    from pathlib import Path

    from apps.tenants import demo_kits

    src = (
        Path(__file__).resolve().parents[3] / "templates/storefront/_slider_script.html"
    ).read_text(encoding="utf-8")
    assert "__sfCardImgsInit" in src and "data-card-imgs" in src
    assert demo_kits.AKTIONSMARKT.promo_card == "preis"
    assert demo_kits.CLOTHING.card_slider == "on"
