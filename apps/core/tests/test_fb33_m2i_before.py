"""FB-33 M2i-0: характеризация форм заявки и оформления ДО «Поля форм».

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i». Снимки сняты до кода M2i: без своих
настроек полей (`site_config["form_fields"]`) формы `/anfrage/`, блок-полоса («band»), модалка
и письма владельцу рисуются байт-в-байт как раньше. Корзина — снимки M2h (`golden_fb33m2h`).
Обход HTML-валидации (POST мимо формы) — поведение сервера закреплено тестами ниже.

Обновить (осознанно): FB33M2I_GOLDEN=update uv run pytest <этот файл>
"""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.utils import translation

from apps.core.tests import test_fb31p5_detail_golden as _p5

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2i"
UPDATE = os.environ.get("FB33M2I_GOLDEN") == "update"
frozen_now = _p5.frozen_now

EVENT_CFG = {"anfrage": {"fields": ["date", "guests", "event_type"], "event_types": ["Hochzeit"]}}


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def check(name, got, ext="html"):
    path = GOLDEN / f"{name}.{ext}"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2I_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"форма изменилась: {path.name}"


def _req(path, cfg, **tenant):
    req = _p5._req(path, cfg)
    for k, v in tenant.items():
        setattr(req.tenant, k, v)
    return req


def anfrage_html(cfg, **tenant):
    from apps.jobs import public_views

    return _p5._normalize(public_views.anfrage(_req("/anfrage/", cfg, **tenant)).content.decode())


def modal_html(cfg):
    from apps.jobs import public_views

    req = _req("/anfrage/modal/", cfg)
    return _p5._normalize(public_views.anfrage_modal(req).content.decode())


def band_html(cfg):
    from django.template import Context, Template

    from apps.tenants import siteconfig

    req = _req("/", cfg)
    tpl = Template('{% include "storefront/sections/_anfrage.html" %}')
    ctx = Context(
        {
            "request": req,
            "site": siteconfig.normalize(cfg),
            "storefront_jobs_enabled": True,
            "section_row": {"style": "band"},
        }
    )
    return _p5._normalize(tpl.render(ctx))


ANFRAGE = {
    "bare": ({}, {}),
    "events": (EVENT_CFG, {}),
    "vehicle": ({"jobs_vehicle": True}, {}),
    "workshop": ({}, {"business_type": "werkstatt"}),
}


@pytest.mark.parametrize("name", sorted(ANFRAGE))
def test_anfrage_page_before(name):
    cfg, tenant = ANFRAGE[name]
    with translation.override("de"):
        check(f"anfrage-{name}", anfrage_html(cfg, **tenant))


def test_anfrage_page_before_ru():
    with translation.override("ru"):
        check("anfrage-events-ru", anfrage_html(EVENT_CFG))


@pytest.mark.parametrize("name", ["bare", "events"])
def test_anfrage_band_and_modal_before(name):
    cfg = ANFRAGE[name][0]
    with translation.override("de"):
        check(f"band-{name}", band_html(cfg))
        check(f"modal-{name}", modal_html(cfg))


def test_owner_emails_before():
    """Письма владельцу — до своих вопросов (M2i-2 добавит ответы только при их наличии)."""
    job = SimpleNamespace(
        title="Zaun bauen",
        site_address="Hauptstr. 1",
        event_date=None,
        guest_count=12,
        event_type="Hochzeit",
        description="Bitte bis Mai.",
        reference_code="J-ABC",
    )
    customer = SimpleNamespace(name="Herr Meyer", phone="0171", email="m@t.de")
    order = SimpleNamespace(
        total="12.00",
        currency="EUR",
        reference_code="O-XYZ",
        pickup_slot=None,
        is_delivery=False,
        table_number="",
        pickup_location="",
        note="Ohne Zwiebeln",
    )
    item = SimpleNamespace(
        qty=2, title_snapshot="Brot", sku="", modifiers_label="", line_total="6.00"
    )
    with translation.override("de"):
        check(
            "mail-job-new",
            render_to_string("emails/job_new.txt", {"job": job, "customer": customer}),
            "txt",
        )
        check(
            "mail-order-owner",
            render_to_string(
                "emails/order_owner.txt", {"order": order, "customer": customer, "items": [item]}
            ),
            "txt",
        )


# --- обход HTML-валидации: сервер на нынешнем поведении ---------------------------------


def _post_anfrage(data, cfg=None):
    import uuid

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.jobs import public_views
    from apps.tenants.tests.factories import TenantFactory

    req = RequestFactory().post("/anfrage/", data)
    req.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[], site_config=cfg or {})
    return public_views.anfrage(req)


def test_post_without_title_or_name_creates_nothing():
    from apps.jobs.models import Job

    for data in ({"title": "", "name": "A"}, {"title": "X", "name": " "}):
        assert _post_anfrage(data).status_code == 302
    assert not Job.objects.exists()


def test_post_with_only_title_and_name_is_accepted():
    """Сейчас контакт не обязателен: имя + «что нужно» — уже заявка."""
    from apps.jobs.models import Job

    _post_anfrage({"title": "Zaun", "name": "Meyer"})
    assert Job.objects.filter(title="Zaun").exists()


def test_post_fields_the_form_did_not_show_are_dropped():
    from apps.jobs.models import Job

    data = {"title": "Fest", "name": "A", "event_date": "2027-05-01", "guest_count": "40"}
    _post_anfrage(data)  # событийные поля не настроены — форма их не показывала
    job = Job.objects.get(title="Fest")
    assert job.event_date is None and job.guest_count is None


def test_post_event_type_outside_the_owner_list_is_dropped():
    from apps.jobs.models import Job

    _post_anfrage({"title": "Fest", "name": "A", "event_type": "<b>x</b>"}, EVENT_CFG)
    assert Job.objects.get(title="Fest").event_type == ""
