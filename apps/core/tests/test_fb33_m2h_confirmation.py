"""FB-33 M2h-2..4: подтверждение — один хост блоков `confirmation`; свои блоки над карточкой и
под ней с ЧИСТЫМ контекстом (без сделки и клиента), формы-блоки не рисуются; «Was passiert jetzt»
— только при своём тексте; «Empfehlungen» — по умолчанию выключены."""

import re
from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.core import confirmation_page, detail_parts
from apps.orders import public_views, services
from apps.orders.tests.test_orders import _req
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

EMAIL = "geheim.kunde@example.org"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _block(bid, body, key="text"):
    return {"key": key, "id": bid, "enabled": True, "data": {"title": "", "body": body}}


def _order():
    item = ProductFactory(base_price=Decimal("4.50"), name={"de": "Bauernbrot"})
    return services.create_order(items=[(item, 1)], name="Kunde K", email=EMAIL, phone="+49 1")


def _html(cfg, order=None):
    order = order or _order()
    tenant = TenantFactory.build(
        name="Laden X", schema_name="laden_x", site_config=cfg, disabled_modules=[]
    )
    req = _req(path=f"/bestellung/{order.reference_code}/", tenant=tenant)
    return public_views.order_confirmation(req, code=order.reference_code).content.decode()


def test_without_own_settings_the_page_is_unchanged():
    order = _order()
    html = _html({}, order)
    assert "data-confirm-next" not in html and "data-confirm-recommend" not in html
    same = _html({"confirmation_next": ""}, order)
    assert re.sub(r"tenant-\d+", "T", same) == re.sub(r"tenant-\d+", "T", html)


def test_blocks_above_and_below_the_card():
    rows = [_block("a", "OBEN"), {"key": "summary"}, _block("b", "UNTEN")]
    html = _html({"page_blocks": {"confirmation": rows}})
    assert html.index("OBEN") < html.index("Bauernbrot") < html.index("UNTEN")
    html = _html({"page_blocks": {"confirmation": [_block("c", "OHNE ANKER")]}})
    assert html.index("Bauernbrot") < html.index("OHNE ANKER"), "без строк — под карточкой"


def test_blocks_get_no_deal_data():
    """ПДн: блок не видит сделку и клиента — даже шаблон, который их спросил бы."""
    from django.template import engines

    from apps.tenants.templatetags import siteui

    order = _order()
    tenant = TenantFactory.build(
        site_config={"page_blocks": {"confirmation": [_block("a", "X")]}}, disabled_modules=[]
    )
    req = _req(tenant=tenant)
    seen = {}
    real = siteui.render_to_string

    def spy(name, ctx=None, request=None):
        if name == "storefront/_page_blocks.html":
            seen.update(ctx)
        return real(name, ctx, request=request)

    siteui.render_to_string = spy
    try:
        tpl = engines["django"].from_string("{% load siteui %}{% confirmation_after %}")
        tpl.render({"order": order, "customer": order.customer}, request=req)
    finally:
        siteui.render_to_string = real
    assert seen and "order" not in seen and "customer" not in seen
    assert EMAIL not in str(seen)


def test_form_blocks_are_not_drawn_on_the_confirmation():
    rows = [{"key": "newsletter", "id": "n1", "enabled": True, "data": {"title": "NEWS"}}]
    rows.append(_block("t", "TEXT-OK"))
    html = _html({"page_blocks": {"confirmation": rows}})
    assert "TEXT-OK" in html and 'name="email"' not in html.split("TEXT-OK")[0][-3000:]


def test_next_text_only_when_set():
    html = _html({"confirmation_next": "Wir rufen Sie in 1 Stunde an."})
    assert "data-confirm-next" in html and "Wir rufen Sie in 1 Stunde an." in html
    assert html.count("<h1") == 1


def test_recommendations_are_off_by_default_and_skip_the_deal_items():
    for i in range(3):
        ProductFactory(name={"de": f"Empfohlen {i}"})
    order = _order()
    assert "data-confirm-recommend" not in _html({}, order)
    html = _html({"confirm_show_recommend": True}, order)
    assert "data-confirm-recommend" in html and "Empfohlen 0" in html
    section = html.split("data-confirm-recommend")[1]
    assert "Bauernbrot" not in section, "позиции сделки не рекомендуются"


def test_recommend_flag_stored_only_as_true():
    assert "confirm_show_recommend" not in siteconfig.normalize({})
    assert "confirm_show_recommend" not in siteconfig.normalize({"confirm_show_recommend": 1})
    assert siteconfig.detail_section_hidden({}, "confirmation") == {"recommend"}
    assert siteconfig.detail_section_hidden({"confirm_show_recommend": True}, "confirmation") == (
        set()
    )
    cfg: dict = {}
    items = [{"key": "summary"}, {"key": "next"}, {"key": "recommend", "enabled": True}]
    detail_parts.lift(cfg, "confirmation", items)
    assert cfg["confirm_show_recommend"] is True
    detail_parts.lift(cfg, "confirmation", [{"key": "recommend", "enabled": False}])
    assert "confirm_show_recommend" not in cfg


def test_recommend_failure_does_not_break_the_page(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("apps.promotions.price_layer.attach_promos", boom)
    assert confirmation_page.recommend_products([]) == []


def test_quote_order_has_no_recommendations():
    ProductFactory(name={"de": "Empfohlen X"})
    order = _order()
    order.source_channel = "quote"
    order.save(update_fields=["source_channel"])
    assert "data-confirm-recommend" not in _html({"confirm_show_recommend": True}, order)
