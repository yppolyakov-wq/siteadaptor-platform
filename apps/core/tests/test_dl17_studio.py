"""DL-17.3: полнота Studio — визуальные ключи правятся из конструктора.

Разведка плана `docs/dl17-feedback-plan-2026-09-02.md` §17.3: часть ключей
site_config нельзя было настроить из билдера вообще (promo_layout,
promo_grouping, site_defaults.card_chrome/page_bg, layout.tail == "fill"), а
часть имела контрол, но не ехала в live-draft (правка была видна только после
Save). Замки ниже держат все три звена каждой опции: контрол → save → черновик.
"""

import json
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # reverse("site-home") в редиректе


def _request(method, path, data=None, tenant=None, **kwargs):
    req = getattr(RequestFactory(), method)(path, data or {}, **kwargs)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)  # обойти login_required
    req.tenant = tenant
    return req


def _builder_body(tenant):
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def _save(tenant, data):
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


# --- A. контролы отрисованы -------------------------------------------------


def test_builder_renders_missing_visual_controls():
    """Каждый ключ из карты разведки имеет СВОЙ контрол в билдере."""
    tenant = TenantFactory(schema_name="public", slug="dl17a", name="DL17A")
    body = _builder_body(tenant)
    # страница акций: режим группировки. LAY-7c (решение владельца 2026-09-10):
    # контрол «Darstellung der Gruppen» (`promo_layout`) СНЯТ — «сетка или лента»
    # это общая ось вывода, а два переключателя на одно и то же и были той «кашей»,
    # ради которой затевалась волна LAY. Ключ остаётся в хранении (легаси-конфиги,
    # демо-киты, композиция «Regale»), но панель его больше не пишет.
    assert 'name="promo_grouping"' in body
    assert 'value="time"' in body
    # STU-19f-2 (осознанно): ось вывода обзора акций (вкл. «добить плиткой») — в кабинете
    assert 'name="promo_index_preset_mode"' not in body
    from apps.core.page_settings import schema

    ts = {t.code: t for t in schema(tenant, ("promos",))}
    assert any(s.code == "promo_index_layout" for s in ts["promos"].settings)
    axis = open("templates/tenant/_pt_output.html", encoding="utf-8").read()
    assert 'value="fill"' in axis


def test_builder_no_longer_ships_hidden_only_design_keys():
    """Замена hidden → видимый контрол: скрытых полей фона/хрома больше нет
    (иначе в POST ушли бы ДВА значения одного имени)."""
    tenant = TenantFactory(schema_name="public", slug="dl17h", name="DL17H")
    body = _builder_body(tenant)
    assert '<input type="hidden" name="sd_page_bg"' not in body
    assert '<input type="hidden" name="sd_card_chrome"' not in body


# --- B. Save ----------------------------------------------------------------


def test_save_promo_page_keys():
    tenant = TenantFactory(schema_name="public", slug="dl17p", name="DL17P")
    cfg = _save(tenant, {"promo_grouping": "time", "font": "system"})
    assert cfg["promo_grouping"] == "time"
    # "" законно снимает ключ (presence-minimal)
    cfg = _save(tenant, {"promo_grouping": "", "font": "system"})
    assert "promo_grouping" not in cfg


def test_save_ignores_the_removed_promo_layout_control():
    """LAY-7c: контрола нет — Save его и не пишет (ветка приёмника удалена).

    Ключ живёт в хранении и читается витриной; что он ПЕРЕЖИВАЕТ чужой Save,
    держит `test_foreign_save_keeps_studio_keys` (инвариант W0/W6).
    """
    tenant = TenantFactory(schema_name="public", slug="dl17pl", name="DL17PL")
    cfg = _save(tenant, {"promo_layout": "slider", "font": "system"})
    assert "promo_layout" not in cfg


# STU-12g: сохранение хрома/фона страницы проверяется на экране «Design des Shops»
# (test_stu12_design_screen) — его контролы Студия больше не несёт.


def test_save_layout_tail_fill():
    tenant = TenantFactory(schema_name="public", slug="dl17t", name="DL17T")
    cfg = _save(
        tenant,
        {"order_products": "1", "enabled_products": "on", "tail_products": "fill"},
    )
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["layout"]["tail"] == "fill"


def test_foreign_save_keeps_studio_keys():
    """W0/W6: форма билдера без этих полей не роняет уже сохранённый выбор
    (у promo_*-ключей есть второй писатель — панель на списке акций)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="dl17w",
        name="DL17W",
        site_config={
            "promo_layout": "slider",
            "promo_grouping": "time",
            "site_defaults": {"page_bg": "#faf6ef", "card_chrome": "hard"},
            "sections": [{"key": "products", "enabled": True, "layout": {"tail": "fill"}}],
        },
    )
    cfg = _save(tenant, {"font": "system"})  # чужая область билдера
    assert cfg["promo_layout"] == "slider"
    assert cfg["promo_grouping"] == "time"
    assert cfg["site_defaults"]["page_bg"] == "#faf6ef"
    assert cfg["site_defaults"]["card_chrome"] == "hard"


# --- C. live-draft ----------------------------------------------------------


def _draft(tenant, payload):
    req = _request(
        "post",
        "/dashboard/site/preview/draft/",
        json.dumps(payload),
        tenant,
        content_type="application/json",
    )
    resp = views.site_preview_draft(req)
    assert resp.status_code == 204
    return req.session["site_preview_draft"]


def test_draft_carries_new_visual_keys():
    tenant = TenantFactory(schema_name="public", slug="dl17d", name="DL17D")
    draft = _draft(
        tenant,
        {
            "sections": [{"key": "products", "enabled": True, "layout": {"tail": "fill"}}],
            "promo_grouping": "time",
            "product_detail": {"hidden": [], "layout": "tabs"},
            "site_defaults": {
                "promo_card": "preis",
                "card_slider": "on",
                "variant_style": "buttons",
                "card_chrome": "line",
                "page_bg": "#faf6ef",
            },
        },
    )
    products = next(s for s in draft["sections"] if s["key"] == "products")
    assert products["layout"]["tail"] == "fill"
    assert draft["promo_grouping"] == "time"
    # STU-19e-1 (deliberate): the detail layout is cabinet-owned — a Studio draft
    # cannot set it, the stored value (none here) stays
    assert siteconfig.product_detail_layout(draft) == ""
    sd = draft["site_defaults"]
    # STU-19f-3 (осознанно): форма карточки акции — в кабинете; черновик Студии её не меняет
    assert sd.get("promo_card", "") != "preis"
    assert sd["card_slider"] == "on"
    assert sd["variant_style"] == "buttons"
    assert sd["card_chrome"] == "line"
    assert sd["page_bg"] == "#faf6ef"
    # опубликованный конфиг не тронут — правки живут под `_draft`
    tenant.refresh_from_db()
    assert "promo_grouping" not in tenant.site_config


def test_draft_empty_promo_keys_clear_them():
    """Пустое значение селекта законно снимает ключ и в черновике (иначе
    «выключить слайдер» было бы видно только после Save)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="dl17dc",
        name="DL17DC",
        site_config={"promo_grouping": "time"},
    )
    draft = _draft(tenant, {"promo_grouping": ""})
    assert "promo_grouping" not in draft


def test_builder_payload_collects_new_keys():
    """Сборщик payload шлёт новые ключи (иначе серверная ветка черновика
    никогда бы их не увидела)."""
    tenant = TenantFactory(schema_name="public", slug="dl17j", name="DL17J")
    body = _builder_body(tenant)
    # LAY-7c: строка `payload.promo_layout` удалена вместе с контролом.
    assert "payload.promo_grouping = pgSel.value" in body
    assert "if (tailSel && tailSel.value) lay.tail = tailSel.value;" in body
    # STU-19f-3: card forms are cabinet-owned — the draft no longer carries them
    assert "promo_card:" not in body
    # STU-12g: card_slider/variant_style — глобальный дизайн, они уехали на экран
    # «Design des Shops» вместе со своими контролами; в черновике Студии остались
    # только настройки СТРАНИЦЫ (приёмник мерджит site_defaults, DL-17.3).
    assert "card_slider:" not in body and "variant_style:" not in body
    assert "card_style:" not in body
    # STU-19e-1: the Studio no longer sends the detail layout (cabinet-owned)
    assert "pdLay" not in body
