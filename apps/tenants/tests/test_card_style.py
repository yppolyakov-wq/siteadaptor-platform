"""ST-7c: ось ФОРМЫ карточки site_defaults.card_style (""|overlay|compact).

Характеризационные замки "" написаны ДО веток (план st7 §4): дефолт обязан
рендерить прежнюю разметку — маркеры зафиксированы по состоянию до правки.
"""

from decimal import Decimal

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.booking.models import Service
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _product_html(card_style=""):
    p = ProductFactory(base_price=Decimal("4.50"), name={"de": "Brot"})
    return render_to_string(
        "storefront/_product_card.html",
        {
            "p": p,
            "storefront_quick_add": False,
            "storefront_card_style": card_style,
            "request": RequestFactory().get("/"),
        },
    )


def _service_html(card_style=""):
    from django.template import Context

    from apps.core.templatetags.sellable_ui import sellable_card

    svc = Service.objects.create(name="Haarschnitt", price_cents=3000, duration_minutes=30)
    ctx = Context({"request": RequestFactory().get("/"), "storefront_card_style": card_style})
    data = sellable_card(ctx, "service", svc)
    return render_to_string("storefront/_sellable_card.html", data)


def test_product_card_default_markers_unchanged():
    """Замок "": прежняя вертикальная карточка — маркеры до правки ST-7c."""
    html = _product_html("")
    assert "aspect-square" in html and "sf-card" in html
    assert "flex flex-col" in html and "rounded-2xl" in html
    assert 'data-edit-field="name"' in html and "Brot" in html
    assert "4,50" in html or "4.50" in html


def test_service_card_default_markers_unchanged():
    """Замок "": вертикальная sellable-карточка — маркеры до правки ST-7c."""
    html = _service_html("")
    assert "sf-card" in html and "block bg-white rounded-2xl" in html
    assert "Haarschnitt" in html and "30" in html


def test_product_card_overlay_and_compact():
    """ST-7c: overlay — текст поверх фото; compact — строка-прайс (фото слева)."""
    overlay = _product_html("overlay")
    assert "bg-gradient-to-t" in overlay and "text-white font-semibold" in overlay
    assert "flex flex-col" not in overlay  # вертикальное тело убрано
    assert 'data-edit-field="name"' in overlay  # инлайн-едит жив в оверлее
    compact = _product_html("compact")
    assert "flex items-center gap-3" in compact and "w-16 h-16" in compact
    assert "aspect-square" not in compact
    assert "Brot" in compact and ("4,50" in compact or "4.50" in compact)


def test_service_card_overlay_and_compact():
    """ST-7c: sellable — compact реюзает горизонтальную ветку, overlay — имя на фото."""
    compact = _service_html("compact")
    assert "flex items-center justify-between" in compact  # горизонтальная ветка
    overlay = _service_html("overlay")
    # услуга без фото → оверлей невозможен, имя остаётся в теле (fail-safe)
    assert "Haarschnitt" in overlay


def test_normalize_and_save_roundtrip():
    """card_style presence-minimal + защита от мусора."""
    from apps.tenants import siteconfig

    sd = siteconfig.normalize({"site_defaults": {"card_style": "overlay"}})["site_defaults"]
    assert sd["card_style"] == "overlay"
    sd2 = siteconfig.normalize({"site_defaults": {"card_style": "bogus"}})["site_defaults"]
    assert "card_style" not in sd2
    assert "card_style" not in siteconfig.normalize({})["site_defaults"]
