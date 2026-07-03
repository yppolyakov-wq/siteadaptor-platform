"""UE1 + UE4-1: промо-БЛОК на канве главной (D2=LIVE promo_pk, fail-safe) —
санитизация, рендер, round-trip save, блок-шаблон."""

from decimal import Decimal

import pytest
from django.template.loader import render_to_string

from apps.promotions.tests.factories import PromotionFactory
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def test_promo_cblock_sanitized_and_legacy_untouched():
    """normalize: promo-блок — пресеты по белым спискам, мусор → дефолты,
    неизвестные ключи отброшены; discount_style в блоке НЕ живёт."""
    cfg = siteconfig.normalize(
        {
            "sections": [
                {
                    "key": "promo",
                    "id": "p1",
                    "enabled": True,
                    "data": {
                        "promo_pk": "x" * 99,
                        "align": "diagonal",
                        "badge_pos": "middle",
                        "show_button": "on",
                        "button_label": "B" * 99,
                        "discount_style": "hack",
                        "junk": 1,
                    },
                }
            ]
        }
    )
    block = next(s for s in cfg["sections"] if s.get("key") == "promo")
    d = block["data"]
    assert len(d["promo_pk"]) == 36  # кламп UUID-длины
    assert d["align"] == "left" and d["badge_pos"] == "top-left"
    assert d["show_button"] is True and len(d["button_label"]) == 40
    assert "discount_style" not in d and "junk" not in d


def _render(block_data, is_preview=False):
    return render_to_string(
        "storefront/sections/_block_promo.html",
        {"block": block_data, "is_preview": is_preview},
    )


def test_promo_block_renders_live_promotion():
    promo = PromotionFactory(
        status="active",
        title={"de": "Herbst-Deal"},
        compare_at_price=Decimal("10.00"),
        price_override=Decimal("7.50"),
        discount_percent=None,
    )
    body = _render(
        {
            "promo_pk": str(promo.pk),
            "align": "center",
            "badge_pos": "top-right",
            "show_button": True,
            "button_label": "Schnapp dir das",
        }
    )
    assert "Herbst-Deal" in body
    assert "top-3 right-3" in body  # позиция бейджа из пресета
    assert "Schnapp dir das" in body and f"/p/{promo.pk}/" in body
    assert "7,50" in body  # LIVE-цена из БД (DE-локаль)


def test_promo_block_fail_safe_hidden():
    """Мусорный pk / неактивная промо → блок пуст (public), плейсхолдер в превью."""
    inactive = PromotionFactory(status="draft", title={"de": "Später"})
    assert _render({"promo_pk": "not-a-uuid"}).strip() == ""
    assert _render({"promo_pk": str(inactive.pk)}).strip() == ""
    assert "Aktion wählen" in _render({"promo_pk": ""}, is_preview=True)


def test_promo_block_badge_none_hides_badge():
    promo = PromotionFactory(status="active", discount_percent=30)
    body = _render({"promo_pk": str(promo.pk), "badge_pos": "none"})
    assert "rounded-full shadow" not in body  # бейдж скрыт пресетом


def test_promo_block_save_roundtrip():
    """Round-trip: POST формы билдера сохраняет промо-блок с данными (save-путь
    _read_cblock_data → normalize)."""
    from apps.core import views
    from apps.core.tests.test_home_builder import _request
    from apps.tenants.tests.factories import TenantFactory

    promo = PromotionFactory(status="active", title={"de": "Deal"})
    tenant = TenantFactory(
        schema_name="public",
        slug="ue1rt",
        name="UE1RT",
        site_config={"sections": [{"key": "promo", "id": "pb1", "enabled": True, "data": {}}]},
    )
    data = {
        "cb_id": "pb1",
        "cb_type_pb1": "promo",
        "order_cb_pb1": "1",
        "enabled_cb_pb1": "on",
        "cb_pb1_promo_pk": str(promo.pk),
        "cb_pb1_align": "right",
        "cb_pb1_badge_pos": "bottom-left",
        "cb_pb1_show_button": "on",
        "cb_pb1_button_label": "Los!",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    block = next(
        s for s in siteconfig.normalize(tenant.site_config)["sections"] if s.get("key") == "promo"
    )
    assert block["data"] == {
        "promo_pk": str(promo.pk),
        "align": "right",
        "badge_pos": "bottom-left",
        "show_button": True,
        "button_label": "Los!",
    }


def test_promo_block_template_save_and_insert():
    """UE4-1: промо-блок сохраняется как block_template и вставляется копией."""
    from apps.core import views
    from apps.core.tests.test_home_builder import _request
    from apps.tenants.tests.factories import TenantFactory

    promo = PromotionFactory(status="active", title={"de": "Deal"})
    tenant = TenantFactory(
        schema_name="public",
        slug="ue1bt",
        name="UE1BT",
        site_config={"sections": [{"key": "promo", "id": "pb2", "enabled": True, "data": {}}]},
    )
    views.home_builder_view(
        _request(
            "post",
            "/dashboard/site/home/",
            {
                "action": "save_block_template:pb2",
                "cb_type_pb2": "promo",
                "cb_pb2_promo_pk": str(promo.pk),
                "cb_pb2_badge_pos": "top-right",
                "tpl_label_pb2": "Herbst-Banner",
            },
            tenant,
        )
    )
    bt = siteconfig.normalize(tenant.site_config)["block_templates"]
    tpl_id, tpl = next(iter(bt.items()))
    assert tpl["key"] == "promo" and tpl["data"]["promo_pk"] == str(promo.pk)

    views.home_builder_view(
        _request(
            "post",
            "/dashboard/site/home/",
            {"action": f"use_block_template:{tpl_id}"},
            tenant,
        )
    )
    blocks = [
        s for s in siteconfig.normalize(tenant.site_config)["sections"] if s.get("key") == "promo"
    ]
    assert len(blocks) == 2  # исходный + вставленная копия
    assert blocks[-1]["data"]["promo_pk"] == str(promo.pk)
