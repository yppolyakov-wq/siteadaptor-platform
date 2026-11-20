"""FB-33 M2i-5 C2: вкладка «Felder» через черновик «Seitenaufbau» (`draft["form"]`).

Решения владельца (2026-11-20): правки — в черновик, «Abbrechen» откатывает (открыть → править
→ Abbrechen = черновик байт-в-байт, включая его отсутствие), на сайт — по «Speichern»;
право — `website.edit` (как окно); номера вопросов — в `commit` под блокировкой.
"""

import copy
import json

import pytest

from apps.core import aufbau_draft, block_window, form_spec, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2i5_before import CUSTOM
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
WOPEN = "openF1"


def _tenant(cfg=None, business_type="catering"):
    return TenantFactory(
        business_type=business_type,
        disabled_modules=[],
        site_config=copy.deepcopy(cfg if cfg is not None else CUSTOM),
    )


def _edit(b, **fields):
    data = {"seite": "anfrage", "ref": "form", "op": "update", "panel_present": "1"}
    data.setdefault("wopen", WOPEN)
    data.update({f"f_{k}": v for k, v in fields.items()})
    return b.post(**data)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _saved(tenant):
    return Tenant.objects.get(pk=tenant.pk).site_config


def test_form_row_opens_on_tab_felder():
    b = Browser(_tenant())
    html = b.get("?seite=anfrage&block=form&tab=felder")
    assert 'data-window-part="formfields"' in html
    assert 'id="schema-tab-felder"' in html
    assert block_window.PART_TAB["formfields"] == "felder"
    assert block_window.PANEL_KEYS[form_spec.PANEL_KEY] == "formfields"


def test_edit_goes_to_draft_not_to_the_site():
    tenant = _tenant()
    before = json.dumps(_saved(tenant), sort_keys=True)
    b = Browser(tenant)
    resp, msgs = _edit(b, mode_description="req")
    assert resp.status_code == 302 and "block=form" in resp["Location"]
    assert json.dumps(_saved(tenant), sort_keys=True) == before
    assert _drafts(b)["anfrage"]["form"]["mode"]["description"] == "req"
    assert (
        aufbau_draft.info(b._request("get"), siteconfig.normalize(tenant.site_config), "anfrage")[
            "count"
        ]
        == 1
    )
    assert msgs == []


def test_open_edit_cancel_leaves_no_draft():
    b = Browser(_tenant())
    b.get("?seite=anfrage&block=form&tab=felder")
    _edit(b, mode_description="req", do="add", new_label="Neu")
    assert _drafts(b)["anfrage"]["window"]
    resp, msgs = b.post(seite="anfrage", ref="form", op="revert", wopen=WOPEN)
    assert resp.status_code == 302 and msgs
    assert _drafts(b) == {}


def test_cancel_returns_existing_draft_byte_for_byte():
    b = Browser(_tenant())
    _edit(b, wopen="openA1", mode_photos="req")
    b.post(seite="anfrage", ref="form", op="window_done", wopen="openA1")
    before = _drafts(b)
    assert before["anfrage"]["form"]["mode"]["photos"] == "req"
    _edit(b, mode_photos="off", do="del:q2")
    _edit(b, event_types="X\nY")
    b.post(seite="anfrage", ref="form", op="revert", wopen=WOPEN)
    assert _drafts(b) == before


def test_returning_to_saved_values_removes_the_draft():
    b = Browser(_tenant())
    _edit(b, mode_description="req")
    _edit(b, mode_description="off")  # CUSTOM: description «off» — как сохранено
    b.post(seite="anfrage", ref="form", op="window_done", wopen=WOPEN)
    assert _drafts(b) == {}


def test_save_writes_through_put_with_ids_from_saved_counter():
    tenant = _tenant()
    b = Browser(tenant)
    _edit(b, do="del:q4")
    _edit(b, do="add", new_label="Allergien", new_type="textarea", new_req="1")
    draft_ids = [q["id"] for q in _drafts(b)["anfrage"]["form"]["custom"]]
    assert draft_ids == ["q1", "q2", "n1"]  # в черновике — временный id
    resp, msgs = b.post(seite="anfrage", op="save")
    assert resp.status_code == 302 and msgs
    stored = siteconfig.normalize(_saved(tenant))["form_fields"]["anfrage"]
    assert [q["id"] for q in stored["custom"]] == ["q1", "q2", "q6"]  # q4/q5 не переиспользованы
    assert stored["custom"][-1] == {
        "id": "q6",
        "type": "textarea",
        "label": "Allergien",
        "mode": "req",
    }
    assert stored["next_id"] == 6
    assert _drafts(b) == {}


def _old_panel_post(tenant, data):
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.jobs import views

    req = RequestFactory().post("/dashboard/auftraege/anfrage-formular/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    tenant.refresh_from_db()
    req.tenant = tenant
    return views.anfrage_form_settings(req)


@pytest.mark.parametrize("force", ["", "1"])
def test_old_panel_meanwhile_merges_three_way(settings, force):
    """Ревью H2: черновик меняет поле A (описание), старая панель — поле B (варианты, дата);
    «Speichern» (и «Trotzdem speichern») — A из черновика, B со старой панели, без конфликта."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    b = Browser(tenant)
    _edit(b, mode_description="req")
    _old_panel_post(tenant, {"af_guests": "on", "af_event_types": "Anders\nNeu"})
    resp, msgs = b.post(seite="anfrage", op="save", force=force)
    assert not any("anderer Stelle" in m for m in msgs), msgs
    site = siteconfig.normalize(_saved(tenant))
    assert form_spec.mode_of(site, "anfrage", "description") == "req"  # A — черновик
    assert site["anfrage"]["event_types"] == ["Anders", "Neu"]  # B — старая панель
    assert site["anfrage"]["fields"] == ["guests"]
    assert form_spec.mode_of(site, "anfrage", "event_date") == "off"
    assert [q["id"] for q in site["form_fields"]["anfrage"]["custom"]] == ["q1", "q2", "q4"]


def test_window_shows_old_panel_change_under_the_draft(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    b = Browser(tenant)
    _edit(b, mode_description="req")
    _old_panel_post(tenant, {"af_guests": "on", "af_event_types": "Anders"})
    html = b.get("?seite=anfrage&block=form&tab=felder")
    assert "Anders" in html
    assert 'name="f_mode_description" value="req" checked' in html


def test_event_types_survive_all_event_fields_off():
    """Ревью H1: выключил все событийные поля → сохранил → включил «Art» — варианты на месте."""
    tenant = _tenant()
    b = Browser(tenant)
    _edit(b, mode_event_date="off", mode_guest_count="off", mode_event_type="off")
    b.post(seite="anfrage", op="save")
    stored = siteconfig.normalize(_saved(tenant))
    assert stored["anfrage"] == {"event_types": ["Hochzeit", "Firmenfeier"]}
    assert not form_spec.view(stored, "anfrage")["any_event"]  # витрина без событийных полей
    _edit(b, mode_event_type="opt")
    b.post(seite="anfrage", op="save")
    stored = siteconfig.normalize(_saved(tenant))
    assert stored["anfrage"]["event_types"] == ["Hochzeit", "Firmenfeier"]
    assert form_spec.view(stored, "anfrage")["event_type"].on


def test_commit_tells_when_contact_rule_applies():
    tenant = _tenant({})
    b = Browser(tenant)
    _edit(b, mode_description="req")
    drafts = b.session[aufbau_draft.SESSION_KEY]
    drafts["anfrage"]["form"]["mode"].update({"email": "off", "phone": "off"})  # устаревший
    b.session.modified = True
    _resp, msgs = b.post(seite="anfrage", op="save")
    assert any("Telefon" in m for m in msgs), msgs
    assert form_spec.mode_of(siteconfig.normalize(_saved(tenant)), "anfrage", "phone") == "opt"


def test_overlay_output_is_never_stored():
    tenant = _tenant()
    b = Browser(tenant)
    _edit(b, do="add", new_label="Neu")
    b.get("?seite=anfrage&block=form&tab=felder")
    b.post(seite="anfrage", op="save")
    raw = json.dumps(_saved(tenant))
    assert form_spec.EDIT_KEY not in raw and form_spec.FORM_ERROR_KEY not in raw
    assert "n1" not in raw


def test_draft_beyond_ids_shows_saved_with_a_note(caplog):
    cfg = copy.deepcopy(CUSTOM)
    cfg["form_fields"]["anfrage"]["next_id"] = 9999
    tenant = _tenant(cfg)
    b = Browser(tenant)
    drafts_state = form_spec.edit_state(siteconfig.normalize(cfg))
    new = copy.deepcopy(drafts_state)
    new["custom"].append({"id": "n1", "type": "text", "label": "Zu viel"})
    b.get("?seite=anfrage")
    b.session[aufbau_draft.SESSION_KEY] = {
        "anfrage": {
            **aufbau_draft._saved_state(siteconfig.normalize(cfg), False, "anfrage"),
            "base": aufbau_draft._fingerprint(
                aufbau_draft._saved_state(siteconfig.normalize(cfg), False, "anfrage")
            ),
            "home": False,
            "host": "anfrage",
            "form": new,
            "form_base": drafts_state,
        }
    }
    b.session.modified = True
    caplog.set_level("WARNING")
    html = b.get("?seite=anfrage&block=form&tab=felder")
    assert "Nummern für eigene Fragen" in html
    assert "form tab draft not shown" in caplog.text


def test_notes_are_shown_contact_and_pinned():
    tenant = _tenant({})
    b = Browser(tenant)
    _resp, msgs = _edit(b, mode_email="off", mode_phone="off", mode_title="off")
    assert any("Telefon" in m for m in msgs)
    state = _drafts(b)["anfrage"]["form"]
    assert state["mode"]["phone"] == "opt" and "title" not in state["mode"]


def test_foreign_question_ids_are_ignored():
    b = Browser(_tenant())
    _edit(b, do="del:q3", q_q9_label="fremd", q_q9_type="text")
    # ничего не изменилось — черновика для экрана нет (держится только снимок окна)
    assert aufbau_draft.get(b._request("get"), "anfrage") is None


def test_preset_goes_to_draft_only():
    tenant = _tenant({"form_fields": {"anfrage": {"mode": {"phone": "req"}}}})
    b = Browser(tenant)
    _resp, msgs = _edit(b, do="preset")
    assert msgs
    assert "anfrage" not in _saved(tenant)
    state = _drafts(b)["anfrage"]["form"]
    assert state["mode"]["event_type"] == "opt" and "Hochzeit" in state["event_types"]


def test_preview_overlay_shows_draft_form():
    tenant = _tenant()
    b = Browser(tenant)
    _edit(b, do="add", new_label="Allergien")
    draft = aufbau_draft.get(b._request("get"), "anfrage")
    shown = aufbau_draft.overlay(siteconfig.normalize(tenant.site_config), draft)
    labels = [q["label"] for q in form_spec.questions(siteconfig.normalize(shown), "anfrage")]
    assert labels[-1] == "Allergien"
    assert form_spec.EDIT_KEY not in siteconfig.normalize(shown)  # на сайт ключ не попадает
    rows = site_schema.blocks_for(shown, "anfrage", "anfrage")
    panel = next(r for r in rows if r["ref"] == "form")[form_spec.PANEL_KEY]
    assert panel["custom"][-1]["id"] == "n1" and panel["custom"][-1]["new"]


def test_staff_without_website_edit_gets_403(settings):
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _user

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    before = json.dumps(_saved(tenant), sort_keys=True)
    user = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=user).update(permissions={"remove": ["website.edit"]})
    data = {
        "seite": "anfrage",
        "ref": "form",
        "op": "update",
        "panel_present": "1",
        "f_mode_phone": "req",
    }
    resp = _open("/dashboard/site/aufbau/", tenant, user, "post", data)
    assert resp.status_code == 403
    data["op"] = "save"
    assert _open("/dashboard/site/aufbau/", tenant, user, "post", data).status_code == 403
    assert json.dumps(_saved(tenant), sort_keys=True) == before
    owner = _user(Membership.ROLE_OWNER)  # контроль: с правом запрос доходит до вьюхи
    data["op"] = "update"
    assert _open("/dashboard/site/aufbau/", tenant, owner, "post", data).status_code == 302
