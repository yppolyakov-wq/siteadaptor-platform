"""FB-33 M2g-2: деталь акции — «Teilen» (WhatsApp, ссылка, QR) и визитка «So finden Sie uns»
строками схемы, которые скрываются на месте внутри колонки «Angebot» (цена — в строке `offer`)."""

import pytest

from apps.core import detail_parts, site_schema
from apps.core.tests import test_fb33_m2g_before as before
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db
frozen_now = before.frozen_now
B1 = {"key": "text", "id": "b1", "data": {"title": "Zwischen", "body": "x"}}


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_schema_rows_stand_in_the_offer_column_and_only_hide():
    rows = site_schema.blocks_for(siteconfig.normalize({}), "promo")
    keys = [r["key"] for r in rows]
    assert keys[:4] == ["offer", "share", "card", "related"]
    by = {r["key"]: r for r in rows}
    assert by["share"]["fixed"] and by["card"]["fixed"] and not by["share"]["pinned"]
    items = detail_parts.edit_rows({}, "promo_detail", [])
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "promo", "down", "share")


def test_hiding_writes_flags_only_as_false_and_keeps_no_rows():
    cfg: dict = {}
    items = detail_parts.edit_rows(cfg, "promo_detail", [B1])
    for it in items:
        if it.get("key") in ("share", "card"):
            it["enabled"] = False
    rows = detail_parts.lift(cfg, "promo_detail", items)
    assert cfg["promo_show_share"] is False and cfg["promo_show_card"] is False
    assert all(r.get("key") not in ("share", "card") for r in rows)
    norm = siteconfig.normalize({"promo_show_share": True, "promo_show_card": False})
    assert "promo_show_share" not in norm and norm["promo_show_card"] is False
    assert siteconfig.detail_section_hidden(norm, "promo") == {"card"}


def test_block_after_share_or_card_renders_in_the_mid_slot():
    rows = [{"key": "offer"}, {"key": "share"}, {"key": "card"}, B1, {"key": "related"}]
    slots = detail_parts.promo_slots({"page_blocks": {"promo_detail": rows}})
    assert slots["mid"] == "ids:b1"


def test_hidden_share_drops_whatsapp_and_qr_but_keeps_the_card():
    html = before.promo_html({"promo_show_share": False})
    assert "wa.me" not in html and "data-copy=" not in html and "sf-qr" not in html
    assert "So finden Sie uns" in html, "визитка на месте"
    full = before.promo_html({})
    assert "data-copy=" in full


def test_hidden_card_respected_unless_the_promo_only_shows():
    cfg = {"promo_show_card": False}
    assert "So finden Sie uns" not in before.promo_html(cfg)
    assert "So finden Sie uns" in before.promo_html(cfg, metadata={"response": "show"}), (
        "«Nur zeigen» — единственный путь к бизнесу"
    )


def test_offer_cannot_be_hidden():
    items = detail_parts.edit_rows({}, "promo_detail", [])
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "promo", "toggle", "offer")
