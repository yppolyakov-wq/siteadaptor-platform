"""FB-33 M2h-5: тип страницы «Bestätigung» в «Seitenaufbau» — строки подтверждения, текст
«Was passiert jetzt» через черновик, «Empfehlungen» глазом строки (хранится только включение),
«+ Block» без форм, превью на примере без сделки и только команде; «Passt dazu»/«Empfehlungen»
— только то, что можно положить в корзину."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connections
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.core import (
    aufbau_draft,
    confirmation_page,
    confirmation_views,
    page_settings,
    site_schema,
    studio_pages,
)
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CODE = "confirmation"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    return TenantFactory(business_type="friseur", disabled_modules=[], **kw)


def _req(rf, tenant=None):
    req = rf.post("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return req


def test_type_is_registered_with_its_preview_and_group():
    pt = studio_pages.page_type(CODE)
    assert pt.block_host == confirmation_page.HOST
    assert site_schema._preview_url(pt) == reverse("storefront-bestaetigung-vorschau")
    assert any(CODE in codes for _k, _l, _m, codes in site_schema._TYPE_GROUPS)


def test_type_is_offered_only_with_a_deal_module(monkeypatch):
    tenant = _tenant()
    assert page_settings.type_active(tenant, CODE)
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: False)
    assert not page_settings.type_active(tenant, CODE)


def test_schema_rows_summary_next_recommend_and_recommend_off_by_default():
    blocks = site_schema.blocks_for(siteconfig.normalize({}), CODE)
    keys = [b["key"] for b in blocks if not b["cblock"]]
    assert keys == ["summary", "next", "recommend"]
    by_key = {b["key"]: b for b in blocks}
    assert by_key["summary"]["pinned"] and by_key["next"]["pinned"]
    assert by_key["recommend"]["enabled"] is False  # K3: по умолчанию выключены
    field = by_key["next"]["fields"][0]
    assert (field["name"], field["kind"], field["value"]) == ("text", "area", "")


def test_add_menu_has_no_form_blocks_and_mutate_refuses_them():
    offered = {k for k, _lab in site_schema.add_options(CODE)}
    assert offered and not offered & confirmation_page.FORM_BLOCKS
    assert {"newsletter", "anfrage_ref"} <= {k for k, _lab in site_schema.add_options("text")}
    items = site_schema.load_items(siteconfig.normalize({}), False, confirmation_page.HOST)
    for key in confirmation_page.FORM_BLOCKS:
        with pytest.raises(site_schema.SchemaError):
            site_schema.mutate(items, CODE, "add", block_type=key)


def test_next_text_goes_through_the_draft_and_empty_is_not_stored(rf):
    tenant = _tenant()
    req = _req(rf, tenant)
    aufbau_draft.op(req, tenant, CODE, "update", ref="next", fields={"text": "  Wir rufen an.  "})
    assert confirmation_page.NEXT_KEY not in (Tenant.objects.get(pk=tenant.pk).site_config or {})
    draft = aufbau_draft.get(req, CODE)
    shown = aufbau_draft.overlay(siteconfig.normalize(tenant.site_config), draft)
    assert shown[confirmation_page.NEXT_KEY] == "Wir rufen an."
    saved = aufbau_draft._saved_state(
        siteconfig.normalize(tenant.site_config), False, "confirmation"
    )
    assert aufbau_draft.changes(saved, draft) == 1
    assert aufbau_draft.commit(req, tenant, CODE)
    cfg = Tenant.objects.get(pk=tenant.pk).site_config
    assert cfg[confirmation_page.NEXT_KEY] == "Wir rufen an."
    # текст правится, строка остаётся на месте; пустой — ключа нет
    aufbau_draft.op(req, tenant, CODE, "update", ref="next", fields={"text": ""})
    assert aufbau_draft.commit(req, tenant, CODE)
    assert confirmation_page.NEXT_KEY not in Tenant.objects.get(pk=tenant.pk).site_config
    with pytest.raises(site_schema.SchemaError):
        aufbau_draft.op(req, tenant, CODE, "toggle", ref="next")


def test_next_text_back_to_saved_leaves_no_draft(rf):
    tenant = _tenant(site_config={confirmation_page.NEXT_KEY: "Alt"})
    req = _req(rf, tenant)
    aufbau_draft.op(req, tenant, CODE, "update", ref="next", fields={"text": "Neu"})
    aufbau_draft.op(req, tenant, CODE, "update", ref="next", fields={"text": "Alt"})
    assert aufbau_draft.get(req, CODE) is None


def test_direct_apply_writes_the_next_text():
    tenant = _tenant()
    site_schema.apply(tenant, CODE, "update", ref="next", fields={"text": "Abholung ab 10 Uhr"})
    cfg = Tenant.objects.get(pk=tenant.pk).site_config
    assert cfg[confirmation_page.NEXT_KEY] == "Abholung ab 10 Uhr"


def test_draft_started_before_the_next_row_is_not_a_conflict():
    cfg = siteconfig.normalize({})
    saved = aufbau_draft._saved_state(cfg, False, "confirmation")
    old = {k: v for k, v in saved.items() if k != "next"}
    draft = {**old, "base": aufbau_draft._fingerprint(old), "home": False, "host": "confirmation"}
    assert aufbau_draft._base_fingerprint(saved, cfg, draft) == draft["base"]


def test_recommend_eye_stores_only_the_switch_on(rf):
    tenant = _tenant()
    req = _req(rf, tenant)
    aufbau_draft.op(req, tenant, CODE, "toggle", ref="recommend")
    assert aufbau_draft.commit(req, tenant, CODE)
    cfg = Tenant.objects.get(pk=tenant.pk).site_config
    assert cfg.get(confirmation_page.RECOMMEND_FLAG) is True
    tenant.refresh_from_db()
    aufbau_draft.op(req, tenant, CODE, "toggle", ref="recommend")
    assert aufbau_draft.commit(req, tenant, CODE)
    assert confirmation_page.RECOMMEND_FLAG not in Tenant.objects.get(pk=tenant.pk).site_config


# ── превью ──────────────────────────────────────────────────────────────────────

#: таблицы сделок: превью не читает ни одной их строки (EXISTS шапки витрины — не сделка)
DEAL_TABLES = (
    "orders_order",
    "orders_orderitem",
    "booking_booking",
    "stays_staybooking",
    "events_ticket",
    "promotions_reservation",
)


def _preview(rf, tenant, monkeypatch, allowed=True, query=""):
    monkeypatch.setattr(page_settings, "_may_preview", lambda request: allowed)
    req = rf.get("/bestaetigung/vorschau/" + query)
    SessionMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=allowed)
    req.tenant = tenant
    return confirmation_views.confirmation_preview(req)


def test_preview_is_only_for_the_team(rf, monkeypatch):
    from django.http import Http404

    with pytest.raises(Http404):
        _preview(rf, _tenant(), monkeypatch, allowed=False)


def test_preview_shows_a_sample_without_touching_deals(rf, monkeypatch):
    tenant = _tenant(
        site_config={
            confirmation_page.NEXT_KEY: "Wir melden uns.",
            "page_blocks": {
                "confirmation": [
                    {"key": "text", "id": "o", "enabled": True, "data": {"body": "OBEN"}},
                    {"key": "summary"},
                ]
            },
        }
    )
    with CaptureQueriesContext(connections["default"]) as ctx:
        resp = _preview(rf, tenant, monkeypatch)
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Robots-Tag"] == "noindex, nofollow"
    assert confirmation_views.SAMPLE_CODE in html and "noindex" in html
    assert html.index("OBEN") < html.index(confirmation_views.SAMPLE_CODE)
    assert html.index(confirmation_views.SAMPLE_CODE) < html.index("Wir melden uns.")
    rows_read = [
        q["sql"]
        for q in ctx.captured_queries
        if not q["sql"].startswith('SELECT 1 AS "a"')
        and any(f'FROM "{t}"' in q["sql"] for t in DEAL_TABLES)
    ]
    assert rows_read == []


# ── «Passt dazu» / «Empfehlungen» — только то, что можно положить в корзину ───────────


def test_upsell_skips_request_only_sold_out_and_inactive_products():
    from apps.catalog.upsell import upsell_products

    ok = ProductFactory(base_price=Decimal("3"), name={"de": "Brezel"})
    req = ProductFactory(base_price=Decimal("0"), primary_action="request", name={"de": "Torte"})
    gone = ProductFactory(
        base_price=Decimal("2"), sold_out_until=timezone.localdate() + timedelta(days=1)
    )
    off = ProductFactory(base_price=Decimal("2"), is_active=False)
    got = {p.pk for p in upsell_products([], 10)}
    assert ok.pk in got and not got & {req.pk, gone.pk, off.pk}
    # корзина-смета (MEN-9): «nur auf Anfrage» уместен
    assert req.pk in {p.pk for p in upsell_products([], 10, with_requests=True)}


def test_upsell_fills_the_limit_past_sold_out_products():
    from apps.catalog.upsell import upsell_products

    for _i in range(3):
        ProductFactory(sold_out_until=timezone.localdate(), is_featured=True)
    fresh = [ProductFactory() for _i in range(2)]
    assert {p.pk for p in upsell_products([], 2)} == {p.pk for p in fresh}


def test_seitenaufbau_offers_the_page_and_edits_next_through_the_panel():
    from apps.core.tests.test_fb27_r2_draft import Browser

    b = Browser(_tenant())
    html = b.get("?seite=confirmation")
    assert "Bestätigung" in html and "Was passiert jetzt" in html
    panel = b.get("?seite=confirmation&block=next")
    assert 'name="f_text"' in panel
    resp, _msgs = b.post(seite=CODE, op="update", ref="next", panel_present="1", f_text="Danke!")
    assert resp.status_code == 302
    assert confirmation_page.NEXT_KEY not in (Tenant.objects.get(pk=b.tenant.pk).site_config or {})
    b.post(seite=CODE, op="save")
    assert Tenant.objects.get(pk=b.tenant.pk).site_config[confirmation_page.NEXT_KEY] == "Danke!"
