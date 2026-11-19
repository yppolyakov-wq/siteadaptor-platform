"""FB-33 M2i-1: «Поля форм» — реестр полей, нормализация, проверка сервера, полоса заявки.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i». Без настроек формы прежние (снимки
`test_fb33_m2i_before`); здесь — что меняют настройки и что нельзя обойти POST-ом мимо формы.
"""

import pytest
from django.http import QueryDict
from django.utils import translation

from apps.core import form_answers, form_spec
from apps.core.tests.test_fb33_m2i_before import EVENT_CFG, _post_anfrage, band_html
from apps.tenants import siteconfig


def _ff(**modes):
    return {"form_fields": {"anfrage": {"mode": modes}}}


# --- ядро своих вопросов ------------------------------------------------------------


def test_questions_are_capped_typed_and_keep_monotonic_ids():
    raw = [
        {"id": "q3", "type": "choice", "label": " Anlass ", "options": ["A", "A", "", "B"]},
        {"id": "q1", "type": "weird", "label": "Frei"},
        {"id": "q3", "type": "text", "label": "Dublette"},  # тот же id — прочь
        {"id": "x", "type": "text", "label": "Kein id"},
        {"id": "q4", "type": "choice", "label": "Ohne Optionen", "options": []},
        {"id": "q5", "type": "text", "label": "", "mode": "req"},
    ]
    questions, next_id = form_answers.normalize_questions(raw, next_id=7)
    assert questions == [
        {"id": "q3", "type": "choice", "label": "Anlass", "options": ["A", "B"]},
        {"id": "q1", "type": "text", "label": "Frei"},
    ]
    assert next_id == 7  # номер удалённых вопросов не возвращается
    assert form_answers.new_id(next_id) == "q8"
    many = [{"id": f"q{i}", "type": "text", "label": f"F{i}"} for i in range(1, 15)]
    assert len(form_answers.normalize_questions(many)[0]) == form_answers.MAX_QUESTIONS


def test_answers_are_collected_validated_and_snapshotted():
    questions = [
        {"id": "q1", "type": "choice", "label": "Anlass", "options": ["Hochzeit"], "mode": "req"},
        {"id": "q2", "type": "number", "label": "Personen"},
        {"id": "q3", "type": "date", "label": "Datum", "mode": "req"},
        {"id": "q4", "type": "bool", "label": "Vegan"},
    ]
    post = QueryDict("q1=Geburtstag&q2=12,5&q3=2027-02-30&q4=on&q9=fremd")
    answers = form_answers.collect(questions, post)
    assert answers == {"q2": 12.5, "q4": True}  # выбор не из списка и битая дата — нет ответа
    assert form_answers.validate(questions, answers) == ["q1", "q3"]
    snap = form_answers.snapshot(questions, {"q1": "Hochzeit"})
    assert snap == {"q1": {"label": "Anlass", "value": "Hochzeit"}}


# --- нормализация -------------------------------------------------------------------


def test_no_settings_no_key():
    assert "form_fields" not in siteconfig.normalize({})
    assert "form_fields" not in siteconfig.normalize({"form_fields": {"anfrage": {"mode": {}}}})


def test_only_differences_from_the_default_are_kept_and_pinned_cannot_change():
    cfg = siteconfig.normalize(
        _ff(description="opt", phone="req", title="off", name="opt", email="bogus", zzz="req")
    )
    assert cfg["form_fields"] == {"anfrage": {"mode": {"phone": "req"}}}
    assert form_spec.mode_of(cfg, "anfrage", "title") == "req"
    assert form_spec.mode_of(cfg, "anfrage", "name") == "req"


def test_event_fields_default_comes_from_the_old_anfrage_fields():
    old = siteconfig.normalize(EVENT_CFG)
    assert form_spec.mode_of(old, "anfrage", "event_date") == "opt"
    # выключить включённое там поле — явный «off» (иначе старое включение ожило бы)
    off = siteconfig.normalize({**EVENT_CFG, **_ff(event_date="off", guest_count="opt")})
    assert off["form_fields"]["anfrage"]["mode"] == {"event_date": "off"}
    assert form_spec.mode_of(off, "anfrage", "event_date") == "off"


def test_contact_cannot_be_switched_off_entirely():
    cfg = siteconfig.normalize(_ff(email="off", phone="off"))
    assert form_spec.mode_of(cfg, "anfrage", "email") == "off"
    assert form_spec.mode_of(cfg, "anfrage", "phone") == "opt"


def test_every_form_keeps_its_pinned_fields():
    """Замок: закреплённые поля нельзя выключить — форма без них не работает."""
    pinned = {form: {f.key for f in fields if f.pinned} for form, fields in form_spec.FORMS.items()}
    assert pinned == {"anfrage": {"title", "name"}, "checkout": {"name"}}
    for form, keys in pinned.items():
        raw = {"form_fields": {form: {"mode": dict.fromkeys(keys, "off")}}}
        cfg = siteconfig.normalize(raw)
        assert all(form_spec.mode_of(cfg, form, k) == "req" for k in keys)


def test_labels_are_owner_text_trimmed():
    cfg = siteconfig.normalize(
        {"form_fields": {"anfrage": {"labels": {"phone": "  Handy   bitte ", "x": "y"}}}}
    )
    assert cfg["form_fields"]["anfrage"] == {"labels": {"phone": "Handy bitte"}}
    assert form_spec.view(cfg, "anfrage")["phone"].label == "Handy bitte"


# --- проверка сервера (POST мимо формы) ---------------------------------------------

pytestmark = pytest.mark.django_db


def test_required_field_missing_creates_no_job():
    from apps.jobs.models import Job

    _post_anfrage({"title": "Zaun", "name": "Meyer"}, _ff(phone="req"))
    assert not Job.objects.exists()
    _post_anfrage({"title": "Zaun", "name": "Meyer", "phone": "0171"}, _ff(phone="req"))
    assert Job.objects.get().customer.phone == "0171"


def test_required_event_value_must_be_valid():
    from apps.jobs.models import Job

    cfg = {**EVENT_CFG, **_ff(event_date="req", event_type="req")}
    bad = {"title": "Fest", "name": "A", "phone": "1", "event_date": "2027-13-01"}
    bad["event_type"] = "Hochzeit"
    _post_anfrage(bad, cfg)
    _post_anfrage({**bad, "event_date": "2027-05-01", "event_type": "Party"}, cfg)
    assert not Job.objects.exists()
    _post_anfrage({**bad, "event_date": "2027-05-01"}, cfg)
    job = Job.objects.get()
    assert job.event_type == "Hochzeit" and str(job.event_date) == "2027-05-01"


def test_switched_off_fields_are_dropped_even_if_posted():
    from apps.jobs.models import Job

    cfg = _ff(description="off", site_address="off", email="off")
    data = {
        "title": "Zaun",
        "name": "A",
        "phone": "1",
        "description": "x",
        "site_address": "y",
        "email": "m@t.de",
    }
    _post_anfrage(data, cfg)
    job = Job.objects.get()
    assert job.description == "" and job.site_address == ""
    assert job.customer.email == ""


def test_owner_enabled_event_field_is_parsed_without_old_settings():
    from apps.jobs.models import Job

    data = {"title": "Fest", "name": "A", "phone": "1", "guest_count": "40"}
    _post_anfrage(data, _ff(guest_count="opt"))
    assert Job.objects.get().guest_count == 40


# --- ревью M2i: края ввода, способ связи, один писатель ----------------------------------


def test_odd_digits_in_guests_do_not_crash_the_check():
    from apps.jobs.models import Job

    cfg = {**EVENT_CFG, **_ff(guest_count="req")}
    for value in ("²", "①", "٣", "1e3", "-4"):
        resp = _post_anfrage({"title": "F", "name": "A", "phone": "1", "guest_count": value}, cfg)
        assert resp.status_code == 302
    assert not Job.objects.exists()


def test_invisible_characters_are_not_an_answer():
    assert form_answers.clean_text("​⁠ ﻿", 50) == ""
    questions = [{"id": "q1", "type": "text", "label": "X", "mode": "req"}]
    answers = form_answers.collect(questions, QueryDict("q1=%E2%80%8B"))
    assert form_answers.validate(questions, answers) == ["q1"]
    cfg = siteconfig.normalize({"form_fields": {"anfrage": {"labels": {"phone": "​"}}}})
    assert "form_fields" not in cfg


def test_broken_next_id_starts_from_zero_and_is_capped():
    assert form_answers.normalize_questions([], float("inf"))[1] == 0
    assert form_answers.normalize_questions([], "nan")[1] == 0
    assert form_answers.normalize_questions([], 10**9)[1] == form_answers.ID_MAX


def test_error_names_the_missing_fields():
    from django.contrib.messages import get_messages

    from apps.core.tests.test_fb33_m2i_before import _anfrage_request
    from apps.jobs import public_views

    with translation.override("de"):
        req = _anfrage_request({"title": "Zaun", "name": "A"}, _ff(description="req"))
        public_views.anfrage(req)
        text = " ".join(str(m) for m in get_messages(req))
    assert "Details" in text and "E-Mail oder Telefon" in text


def test_old_panel_is_the_one_writer_of_event_fields():
    """Панель «Anfrage-Formular» сняла «date» — «обязательно» из «Поля форм» не держит поле."""
    cfg = {**EVENT_CFG, **_ff(event_date="req", guest_count="req")}
    form_spec.sync_legacy_panel(cfg, ["guests", "event_type"])
    site = siteconfig.normalize({**cfg, "anfrage": {"fields": ["guests", "event_type"]}})
    assert form_spec.mode_of(site, "anfrage", "event_date") == "off"
    assert form_spec.mode_of(site, "anfrage", "guest_count") == "req"
    off = _ff(event_date="off")
    form_spec.sync_legacy_panel(off, ["date"])  # отметили снова — явный «off» снят
    assert "form_fields" not in off


def test_old_panel_view_writes_both_settings():
    from apps.jobs import views
    from apps.jobs.tests.test_cabinet import _req as cabinet_req
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(disabled_modules=[], site_config={**EVENT_CFG, **_ff(event_date="req")})
    data = {"af_guests": "on", "af_event_types": "Hochzeit"}
    path = "/dashboard/auftraege/anfrage-formular/"
    views.anfrage_form_settings(cabinet_req("post", path=path, data=data, tenant=tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["anfrage"]["fields"] == ["guests"]
    assert "form_fields" not in tenant.site_config


def test_band_asks_for_email_when_it_is_the_only_contact():
    with translation.override("de"):
        html = band_html({})
    assert 'name="email" required' in html
    with translation.override("de"):
        html = band_html(_ff(email="off"))
    assert 'name="email"' not in html and 'name="phone" required' in html


def test_form_tag_normalizes_once_per_request():
    from unittest import mock

    from django.template import Context, Template

    from apps.core.tests.test_fb33_m2i_before import _req

    req = _req("/", {})
    tpl = Template(
        '{% load siteui %}{% form_field_modes "anfrage" as a %}{% form_field_modes "anfrage" as b %}'
    )
    with mock.patch.object(siteconfig, "normalize", wraps=siteconfig.normalize) as spy:
        tpl.render(Context({"request": req}))
    assert spy.call_count == 1


# --- рендер -------------------------------------------------------------------------


def test_full_form_marks_required_and_hides_switched_off():
    from apps.core.tests.test_fb33_m2i_before import anfrage_html

    with translation.override("de"):
        html = anfrage_html(_ff(phone="req", description="off", photos="req"))
    assert 'name="description"' not in html
    assert 'name="phone" type="tel" required' in html
    assert 'name="photos" type="file" accept="image/*" multiple required' in html
    assert "Fotos (bis zu 5) *" in html


def test_band_draws_up_to_three_required_fields():
    with translation.override("de"):
        html = band_html(_ff(phone="req", site_address="req", email="req"))
    assert 'name="phone" required' in html and 'name="site_address" required' in html
    assert 'name="email" required' in html
    assert "<form" in html


def test_band_sends_to_the_full_form_when_it_cannot_draw_a_required_field():
    with translation.override("de"):
        html = band_html(_ff(photos="req"))
    assert "<form" not in html and 'href="/anfrage/"' in html
