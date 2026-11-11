"""FB-27 R2: черновик «Seitenaufbau» — правки попадают на сайт только по «Speichern»."""

from types import SimpleNamespace

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import aufbau_draft, page_settings, site_schema
from apps.core.modules import default_disabled_for
from apps.core.site_schema_views import site_schema_view
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )


class Browser:
    """Один владелец в одной вкладке: сессия живёт между запросами."""

    def __init__(self, tenant):
        self.tenant = tenant
        self.session = None

    def _request(self, method, data=None, query=""):
        req = getattr(RequestFactory(), method)("/dashboard/site/aufbau/" + query, data or {})
        SessionMiddleware(lambda r: None).process_request(req)
        if self.session is not None:
            req.session = self.session
        self.session = req.session
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = SimpleNamespace(is_authenticated=True)
        self.tenant.refresh_from_db()
        req.tenant = self.tenant
        return req

    def get(self, query=""):
        return site_schema_view(self._request("get", query=query)).content.decode()

    def post(self, **data):
        req = self._request("post", data)
        resp = site_schema_view(req)
        return resp, [str(m) for m in get_messages(req)]


def _saved_refs(tenant, host="info"):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return [b.get("id") for b in (cfg.get("page_blocks") or {}).get(host, []) if b.get("id")]


def test_action_goes_to_draft_not_to_the_site():
    b = Browser(_tenant())
    resp, _msgs = b.post(seite="text", op="add", type="text")
    assert resp.status_code == 302
    assert _saved_refs(b.tenant) == []  # на сайте ничего
    html = b.get("?seite=text")
    assert "data-schema-draft" in html and 'value="save"' in html and 'value="discard"' in html
    assert html.count("data-schema-block=") == 2  # карточка контактов + новый блок


def test_save_publishes_and_clears_the_draft():
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    resp, msgs = b.post(seite="text", op="save")
    assert resp.status_code == 302 and any("Gespeichert" in m for m in msgs)
    assert len(_saved_refs(b.tenant)) == 1
    assert "data-schema-draft" not in b.get("?seite=text")


def test_discard_restores_the_saved_state():
    b = Browser(_tenant())
    site_schema.apply(b.tenant, "text", "add", block_type="text")
    ref = _saved_refs(b.tenant)[0]
    b.post(seite="text", op="delete", ref=ref)
    assert _saved_refs(b.tenant) == [ref]
    b.post(seite="text", op="discard")
    html = b.get("?seite=text")
    assert f'data-schema-block="{ref}"' in html and "data-schema-draft" not in html


def test_undoing_a_change_leaves_no_draft():
    b = Browser(_tenant())
    site_schema.apply(b.tenant, "text", "add", block_type="text")
    ref = _saved_refs(b.tenant)[0]
    b.post(seite="text", op="toggle", ref=ref)
    assert "data-schema-draft" in b.get("?seite=text")
    b.post(seite="text", op="toggle", ref=ref)
    assert "data-schema-draft" not in b.get("?seite=text")


def test_change_counter():
    b = Browser(_tenant())
    for _ in range(2):
        site_schema.apply(b.tenant, "text", "add", block_type="text")
    first, second = _saved_refs(b.tenant)
    b.post(seite="text", op="toggle", ref=first)  # 1: скрыт
    b.post(seite="text", op="add", type="text")  # 2: добавлен
    b.post(seite="text", op="toggle", ref=site_schema.CONTACT_REF)  # 3: карточка контактов
    b.tenant.refresh_from_db()
    cfg = siteconfig.normalize(b.tenant.site_config)
    req = b._request("get")
    assert aufbau_draft.info(req, cfg, "text")["count"] == 3


def test_drafts_are_per_page():
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    b.post(seite="catalog", op="add", type="text")
    b.post(seite="text", op="save")
    assert len(_saved_refs(b.tenant, "info")) == 1
    assert _saved_refs(b.tenant, "catalog") == []  # каталог остался черновиком
    html = b.get("?seite=text")
    assert "data-schema-other-drafts" in html and "seite=catalog" in html


def test_conflict_is_reported_and_never_overwrites_silently():
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    other = site_schema.apply(b.tenant, "text", "add", block_type="banner")  # другая вкладка
    resp, msgs = b.post(seite="text", op="save")
    assert resp.status_code == 302
    assert _saved_refs(b.tenant) == [other]  # чужое цело, наше не записано
    assert any("inzwischen" in m for m in msgs)
    html = b.get("?seite=text")
    assert "data-schema-conflict" in html and 'name="force"' in html
    b.post(seite="text", op="save", force="1")  # осознанно поверх
    assert other not in _saved_refs(b.tenant) and len(_saved_refs(b.tenant)) == 1


def test_preview_shows_the_draft_only_to_the_cabinet(monkeypatch):
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    req = RequestFactory().get("/ueber-uns/", {"preview": "1", "aufbau": "text"})
    req.tenant, req.session = b.tenant, b.session
    monkeypatch.setattr(page_settings, "_may_preview", lambda r: True)
    cfg = siteconfig.normalize(page_settings.raw_config(req))
    assert len([x for x in cfg["page_blocks"]["info"] if x.get("id")]) == 1
    anon = RequestFactory().get("/ueber-uns/", {"preview": "1", "aufbau": "text"})
    anon.tenant, anon.session = b.tenant, b.session
    monkeypatch.setattr(page_settings, "_may_preview", lambda r: False)
    cfg = siteconfig.normalize(page_settings.raw_config(anon))
    assert not [x for x in (cfg.get("page_blocks") or {}).get("info", []) if x.get("id")]


def test_draft_keeps_translations_aligned_on_save():
    tenant = _tenant()
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "info": [
                    {"id": "a1", "key": "text", "enabled": True, "data": {"title": "Eins"}},
                    {"id": "a2", "key": "text", "enabled": True, "data": {"title": "Zwei"}},
                ]
            },
            "i18n": {
                "en": {
                    "page_blocks": {
                        "info": [
                            {"id": "a1", "data": {"title": "One"}},
                            {"id": "a2", "data": {"title": "Two"}},
                        ]
                    }
                }
            },
        }
    )
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    b = Browser(tenant)
    b.post(seite="text", op="up", ref="a2")
    b.post(seite="text", op="save")
    stored = siteconfig.localize(
        siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config), "en"
    )
    titles = [x["data"]["title"] for x in stored["page_blocks"]["info"] if x.get("id")]
    assert titles == ["Two", "One"]


def test_session_holds_a_bounded_number_of_drafts():
    b = Browser(_tenant())
    req = b._request("get")
    for i in range(aufbau_draft.MAX_DRAFTS + 3):
        aufbau_draft._put(req, f"c{i}", {"items": [], "base": "x"})
    assert len(req.session[aufbau_draft.SESSION_KEY]) == aufbau_draft.MAX_DRAFTS


def test_save_without_a_draft_does_not_claim_success():
    """Двойная отправка или истёкшая сессия: записывать нечего — и «Gespeichert» нет."""
    b = Browser(_tenant())
    _resp, msgs = b.post(seite="text", op="save")
    assert not any("Gespeichert" in m for m in msgs)
    assert any("keinen Entwurf" in m for m in msgs)


def test_draft_of_a_vanished_page_is_dropped():
    from apps.core.models import ContentPage

    b = Browser(_tenant())
    page = ContentPage.objects.create(slug="weg", title="Weg", body="x", is_published=True)
    b.post(seite="text@seite:weg", op="add", type="text")
    assert "text@seite:weg" in b.session[aufbau_draft.SESSION_KEY]
    page.delete()
    b.get("?seite=home")
    assert aufbau_draft.SESSION_KEY not in b.session


def test_home_sections_go_through_the_draft_too():
    b = Browser(_tenant())
    cfg = siteconfig.normalize(b.tenant.site_config)
    row = cfg["sections"][0]
    b.post(seite="home", op="toggle", ref=row["key"])
    stored = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)["sections"][0]
    assert stored["enabled"] is row["enabled"]  # сайт не тронут
    b.post(seite="home", op="save")
    stored = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    saved_row = next(s for s in stored["sections"] if s["key"] == row["key"])
    assert saved_row["enabled"] is (not row["enabled"])


def test_draft_survives_a_real_session_round_trip():
    """Черновик лежит в сессии — он обязан сериализоваться её бэкендом."""
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="banner")
    b.post(
        seite="home",
        op="toggle",
        ref=siteconfig.normalize(b.tenant.site_config)["sections"][0]["key"],
    )
    b.session.save()
    from django.contrib.sessions.backends.cache import SessionStore

    loaded = SessionStore(session_key=b.session.session_key)
    assert set(loaded[aufbau_draft.SESSION_KEY]) == {"text", "home"}
