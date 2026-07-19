"""ST-2: реестр пресетов НЕ-home страниц (page_presets) + пикер в билдере.

Замки: каждый блок каждого пресета проходит normalize_page_blocks (Save не
теряет), применение идемпотентно и не трогает блоки владельца, плоские ключи
существуют в normalize, POST-приёмник use_page_preset применяет/игнорирует
неизвестное, пикеры рендерятся в панели билдера.
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import page_presets, views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # reverse("site-home") в редиректе


def _request(method, data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)  # обойти login_required
    req.tenant = tenant
    return req


def test_all_preset_blocks_survive_normalize():
    """Адверсариальный замок ВСЕХ хостов реестра (обобщение about-замка):
    посеянные блоки валидны для normalize_page_blocks — Save их не теряет."""
    for host, reg in page_presets.PAGE_PRESETS.items():
        for preset in reg["presets"]:
            raw = {
                host: [
                    {
                        "key": kind,
                        "id": f"{reg['prefix']}{preset['key']}-{i}",
                        "data": dict(data),
                    }
                    for i, (kind, data) in enumerate(preset["blocks"], start=1)
                ]
            }
            cleaned = siteconfig.normalize_page_blocks(raw)
            assert len(cleaned.get(host, [])) == len(preset["blocks"]), (host, preset["key"])


def test_flat_keys_belong_to_normalize():
    """Плоские ключи пресетов существуют в нормализованном конфиге —
    иначе normalize молча дропнет применённое."""
    normalized = siteconfig.normalize({})
    for host, reg in page_presets.PAGE_PRESETS.items():
        for preset in reg["presets"]:
            for key in preset.get("flat") or {}:
                assert key in normalized, (host, preset["key"], key)


def test_apply_idempotent_and_keeps_owner_blocks():
    cfg = {"page_blocks": {"cart": [{"key": "text", "id": "own1", "data": {"body": "meins"}}]}}
    assert page_presets.apply_page_preset(cfg, "cart", "vertrauen")
    once = siteconfig.normalize(cfg)
    ids = [b["id"] for b in once["page_blocks"]["cart"]]
    assert "own1" in ids and any(i.startswith("pb-cart-vertrauen-") for i in ids)
    assert once["cart_show_upsell"] is True
    # Повторное применение + смена пресета: семейство заменяется, своё цело.
    assert page_presets.apply_page_preset(once, "cart", "vertrauen")
    assert page_presets.apply_page_preset(once, "cart", "schlicht")
    twice = siteconfig.normalize(once)
    assert [b["id"] for b in twice["page_blocks"]["cart"]] == ["own1"]
    assert twice["cart_show_upsell"] is False


def test_apply_unknown_host_or_preset_noop():
    cfg = {"x": 1}
    assert not page_presets.apply_page_preset(cfg, "cart", "nope")
    assert not page_presets.apply_page_preset(cfg, "unknown", "schlicht")
    assert cfg == {"x": 1}


def test_current_preset_detection():
    cfg = siteconfig.normalize({})
    assert page_presets.current_preset(cfg, "info") == "text"
    assert page_presets.current_preset(cfg, "cart") == "empfehlung"  # дефолт upsell=True
    page_presets.apply_page_preset(cfg, "cart", "schlicht")
    cfg = siteconfig.normalize(cfg)
    assert page_presets.current_preset(cfg, "cart") == "schlicht"
    page_presets.apply_page_preset(cfg, "info", "geschichte")
    cfg = siteconfig.normalize(cfg)
    assert page_presets.current_preset(cfg, "info") == "geschichte"


def test_presets_for_recommended_first():
    cards = page_presets.presets_for("cart", "bakery")
    assert cards[0]["key"] == "vertrauen" and cards[0]["recommended"]
    neutral = page_presets.presets_for("cart", "hotel")
    assert [c["key"] for c in neutral] == ["schlicht", "empfehlung", "vertrauen"]
    assert page_presets.presets_for("unknown", "bakery") == []


def test_builder_action_applies_preset_and_redirects_back():
    tenant = TenantFactory(schema_name="public", slug="stp1", name="STP1", site_config={})
    resp = views.home_builder_view(
        _request(
            "post",
            {"action": "use_page_preset:cart:vertrauen", "page_path": "/warenkorb/"},
            tenant,
        )
    )
    assert resp.status_code == 302 and "page=" in resp["Location"]
    cfg = siteconfig.normalize(tenant.site_config)
    assert any(b["id"].startswith("pb-cart-vertrauen-") for b in cfg["page_blocks"]["cart"])
    assert cfg["cart_show_upsell"] is True


def test_builder_action_unknown_preset_keeps_config():
    tenant = TenantFactory(
        schema_name="public", slug="stp2", name="STP2", site_config={"hero_title": "X"}
    )
    before = siteconfig.normalize(tenant.site_config)
    resp = views.home_builder_view(
        _request("post", {"action": "use_page_preset:cart:nope"}, tenant)
    )
    assert resp.status_code == 302
    assert siteconfig.normalize(tenant.site_config) == before


def test_builder_renders_preset_pickers():
    tenant = TenantFactory(schema_name="public", slug="stp3", name="STP3", site_config={})
    body = views.home_builder_view(_request("get", tenant=tenant)).content.decode()
    assert "use_page_preset:info:geschichte" in body  # «Über uns» — у всех
    if tenant.is_module_active("catalog"):
        assert "use_page_preset:cart:vertrauen" in body
