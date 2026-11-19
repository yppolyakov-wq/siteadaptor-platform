"""FB-33 M2d-1/2: «Seitentitel» — свой заголовок, вступление и вид страниц-списков и форм."""

import pytest
from django.utils import translation

from apps.core import aufbau_draft, page_title, site_schema
from apps.core.tests.test_fb33_m2d_page_title_before import PAGES, _anchor, _head, _render
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_normalize_keeps_only_known_pages_and_filled_fields():
    raw = {
        "services": {"title": "  Termine  ", "intro": "", "align": "center"},
        "events": {"title": "", "intro": ""},
        "evil": {"title": "x"},
        "blog": {"align": "right"},
    }
    assert siteconfig.normalize({"page_titles": raw})["page_titles"] == {
        "services": {"title": "Termine", "align": "center"}
    }
    assert "page_titles" not in siteconfig.normalize({})  # presence-minimal


def test_text_is_capped():
    out = page_title.clean_one({"title": "x" * 500, "intro": "y" * 900})
    assert len(out["title"]) == page_title.TITLE_MAX and len(out["intro"]) == page_title.INTRO_MAX


def test_every_page_with_a_title_is_characterized():
    assert set(page_title.HEAD_HOSTS) == set(PAGES)


@pytest.mark.parametrize("host", sorted(PAGES))
def test_own_title_and_intro_replace_the_default_and_h1_stays_single(host, monkeypatch):
    cfg = {"page_titles": {host: {"title": "Mein Titel", "intro": "Mein Text", "align": "center"}}}
    with translation.override("de"):
        html = _render(host, cfg, monkeypatch=monkeypatch)
    assert html.count("<h1") == 1
    head = _head(html) + html[html.find("</h1>") : html.find("</h1>") + 900]
    assert "Mein Titel" in head
    if host != "services":  # у /termin/ без ресурсов вступление — отдельной строкой
        assert "Mein Text" in html
    assert "text-center" in head or host == "promos"  # у prospekt-вида центра нет


@pytest.mark.parametrize("host", ("services", "anfrage", "team"))
def test_public_page_has_no_edit_hooks(host, monkeypatch):
    cfg = {"page_titles": {host: {"title": "Mein Titel"}}}
    html = _render(host, cfg, monkeypatch=monkeypatch)
    assert 'data-edit="page_titles' not in html


def test_translation_overlay_wins_in_its_language():
    cfg = siteconfig.normalize({"page_titles": {"services": {"title": "Termine"}}})
    siteconfig.set_overlay_value(cfg, "ru", ("page_titles", "services", "title"), "Запись")
    cfg = siteconfig.normalize(cfg)
    assert siteconfig.localize(cfg, "ru")["page_titles"]["services"]["title"] == "Запись"
    assert siteconfig.localize(cfg, "de")["page_titles"]["services"]["title"] == "Termine"


@pytest.mark.parametrize("host", ("events", "services", "anfrage", "message"))
def test_schema_shows_the_title_row_where_the_page_draws_h1(host):
    from apps.core import studio_pages

    code = next(pt.code for pt in studio_pages.PAGE_TYPES if site_schema.host_for(pt.code) == host)
    cfg = siteconfig.normalize({"page_blocks": {host: [
        {"key": "text", "id": "t1", "enabled": True, "data": {"title": "x"}}, _anchor(host)
    ]}})  # fmt: skip
    rows = site_schema.blocks_for(cfg, code)
    refs = [r["ref"] for r in rows]
    assert refs.count(page_title.TITLE_REF) == 1
    at = refs.index(page_title.TITLE_REF)
    if host in page_title.H1_FIRST:
        # первая строка (или сразу под фото-шапкой страницы, если она есть)
        assert refs[:at] in ([], ["page_head"])
    else:
        assert refs[at - 1] == "t1"  # свой блок «сверху» стоит над заголовком


def test_title_op_patches_and_refuses_other_ops():
    draft = {"title": {"title": "Alt"}}
    site_schema.title_op("services", draft, "update", {"intro": "Neu", "align": "center"})
    assert draft["title"] == {"title": "Alt", "intro": "Neu", "align": "center"}
    site_schema.title_op("services", draft, "update", {"title": ""})
    assert draft["title"] == {"intro": "Neu", "align": "center"}
    for op in ("toggle", "delete", "up", "move"):
        with pytest.raises(site_schema.SchemaError):
            site_schema.title_op("services", draft, op, None)
    with pytest.raises(site_schema.SchemaError):
        site_schema.title_op("services", draft, "update", {"align": "right"})
    with pytest.raises(site_schema.SchemaError):
        site_schema.title_op("catalog", draft, "update", {"title": "x"})


def test_apply_writes_the_title_directly():
    from apps.core import studio_pages
    from apps.tenants.models import Tenant
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(business_type="friseur", disabled_modules=[])
    code = next(
        pt.code for pt in studio_pages.PAGE_TYPES if site_schema.host_for(pt.code) == "services"
    )
    site_schema.apply(tenant, code, "update", ref=page_title.TITLE_REF, fields={"title": "Termine"})
    cfg = Tenant.objects.get(pk=tenant.pk).site_config
    assert cfg["page_titles"] == {"services": {"title": "Termine"}}


def test_draft_keeps_the_title_until_save_and_counts_as_a_change(rf):
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core import studio_pages
    from apps.tenants.models import Tenant
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(business_type="friseur", disabled_modules=[])
    code = next(
        pt.code for pt in studio_pages.PAGE_TYPES if site_schema.host_for(pt.code) == "services"
    )
    req = rf.post("/")
    SessionMiddleware(lambda r: None).process_request(req)
    aufbau_draft.op(req, tenant, code, "update", ref=page_title.TITLE_REF, fields={"title": "Neu"})
    assert "page_titles" not in (Tenant.objects.get(pk=tenant.pk).site_config or {})
    draft = aufbau_draft.get(req, code)
    shown = aufbau_draft.overlay(siteconfig.normalize(tenant.site_config), draft)
    assert shown["page_titles"]["services"]["title"] == "Neu"
    saved = aufbau_draft._saved_state(siteconfig.normalize(tenant.site_config), False, "services")
    assert aufbau_draft.changes(saved, draft) == 1
    assert aufbau_draft.commit(req, tenant, code)
    assert Tenant.objects.get(pk=tenant.pk).site_config["page_titles"]["services"]["title"] == "Neu"
    # вернули прежний текст — черновика нет
    aufbau_draft.op(req, tenant, code, "update", ref=page_title.TITLE_REF, fields={"title": "X"})
    aufbau_draft.op(req, tenant, code, "update", ref=page_title.TITLE_REF, fields={"title": "Neu"})
    assert aufbau_draft.get(req, code) is None


def test_inline_edit_accepts_known_pages_only(rf):
    import json

    from django.contrib.auth import get_user_model

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(business_type="friseur")
    user = get_user_model().objects.create_user("o", "o@x.de", "pw12345678")

    def post(field):
        req = rf.post(
            "/",
            data=json.dumps({"field": field, "value": "Hallo"}),
            content_type="application/json",
        )
        req.user, req.tenant = user, tenant
        return views.site_inline_edit.__wrapped__.__wrapped__(req)

    assert post("page_titles.services.title").status_code == 204
    assert tenant.site_config["page_titles"]["services"]["title"] == "Hallo"
    assert post("page_titles.evil.title").status_code == 400
    assert post("page_titles.services.style").status_code == 400


def test_seitenaufbau_panel_edits_the_title_through_the_draft(settings):
    """Сквозь экран: строка «Seitentitel» видна в схеме, её панель — поля, «Speichern» пишет."""
    from apps.core import studio_pages
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        business_type="friseur", disabled_modules=list(default_disabled_for("friseur"))
    )
    code = next(
        pt.code for pt in studio_pages.PAGE_TYPES if site_schema.host_for(pt.code) == "services"
    )
    b = Browser(tenant)
    html = b.get(f"?seite={code}")
    assert "Seitentitel" in html
    panel = b.get(f"?seite={code}&block={page_title.TITLE_REF}")
    assert 'name="f_title"' in panel and 'name="f_intro"' in panel and 'value="center"' in panel
    assert "data-schema-confirm" not in panel  # удалять нечего


def test_draft_started_before_the_title_row_is_not_a_conflict():
    """Ревью M2d: черновик из сессии до деплоя (без ключа `title`) — не «изменено в другом месте»."""
    cfg = siteconfig.normalize({})
    saved = aufbau_draft._saved_state(cfg, False, "services")
    old = {k: v for k, v in saved.items() if k != "title"}
    draft = {**old, "base": aufbau_draft._fingerprint(old), "home": False, "host": "services"}
    assert aufbau_draft._base_fingerprint(saved, cfg, draft) == draft["base"]


def test_canvas_does_not_save_an_untouched_default_text():
    """Ревью M2d: клик в заголовок без правки не записывает текст по умолчанию как свой."""
    import pathlib

    for tpl in ("templates/tenant/site_home.html", "templates/tenant/site_preview.html"):
        src = pathlib.Path(tpl).read_text(encoding="utf-8")
        assert "el._sfBefore = el.innerText" in src and "el.innerText === el._sfBefore" in src, tpl


def test_promo_photo_head_shows_the_own_intro():
    from django.template.loader import render_to_string
    from django.test import RequestFactory

    req = RequestFactory().get("/aktionen/")
    html = render_to_string(
        "storefront/promo_page/_head.html",
        {"request": req, "storefront_page_titles": {"promos": {"title": "Deals", "intro": "Jede Woche neu"}},
         "promo_total": 3},
    )  # fmt: skip
    assert "Deals" in html and "Jede Woche neu" in html


def test_question_page_with_a_reference_has_no_intro_edit_hook():
    import pathlib

    src = pathlib.Path("templates/storefront/message_contact.html").read_text(encoding="utf-8")
    assert '{% if is_preview and not ref_label %} data-edit="page_titles.message.intro"' in src
