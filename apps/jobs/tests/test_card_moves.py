"""CARD-1/CARD-2: перестановки карточки по фидбэку владельца 2026-08-26.

«Поле Gültig bis и Angebot schicken перенеси в поле Dokumente. Nachrichten
перенеси в правую колонку под кнопку написать клиенту.»

Главный риск переноса — класс W0: поле уехало из формы, а приёмник продолжает
читать его из POST и на каждом сохранении затирает. Здесь это закреплено замком.
"""

import uuid
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.jobs import services, views
from apps.jobs.models import Job
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/auftraege/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    request.tenant = TenantFactory.build()
    return request


def _job():
    return services.create_job(title="Fingerfood", name="Anna Bauer", email="anna@example.de")


def test_valid_until_is_saved_by_its_own_form():
    job = _job()

    resp = views.job_detail(
        _req("post", {"action": "valid_until", "valid_until": "2026-09-30"}), pk=job.pk
    )

    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.valid_until == date(2026, 9, 30)


def test_saving_the_quote_does_not_wipe_the_deadline():
    """W0: поле уехало в «Dokumente» — сохранение состава его больше не трогает."""
    job = _job()
    job.valid_until = date(2026, 9, 30)
    job.save(update_fields=["valid_until"])

    views.job_detail(
        _req(
            "post",
            {
                "action": "save_lines",
                "line_text_1": "Arbeit",
                "line_qty_1": "1",
                "line_price_1": "100,00",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )

    job.refresh_from_db()
    assert job.valid_until == date(2026, 9, 30)


def test_documents_block_holds_deadline_and_send_button():
    job = _job()

    body = views.job_detail(_req(), pk=job.pk).content.decode()
    documents = body.split('data-deal-block="documents"', 1)[1]

    assert 'name="valid_until"' in documents
    assert 'value="quoted"' in documents  # кнопка «Angebot senden»


def test_send_button_disappears_once_the_quote_went_out():
    job = _job()
    job.status = Job.STATUS_QUOTED
    job.save(update_fields=["status"])

    body = views.job_detail(_req(), pk=job.pk).content.decode()
    documents = body.split('data-deal-block="documents"', 1)[1].split("</section>", 1)[0]

    assert 'value="quoted"' not in documents


def test_deadline_is_no_longer_in_the_quote_form():
    """Поле не должно остаться в обоих местах — иначе два источника правды."""
    job = _job()

    body = views.job_detail(_req(), pk=job.pk).content.decode()
    quote_form = body.split('data-deal-block="items"', 1)[1].split(
        'data-deal-block="documents"', 1
    )[0]

    assert 'name="valid_until"' not in quote_form


def test_thread_sits_in_the_rail_after_the_customer_card():
    """CARD-2: переписка — в правой колонке, а не в первой."""
    job = _job()

    body = views.job_detail(_req(), pk=job.pk).content.decode()
    main, _sep, rail = body.partition("data-deal-rail")

    assert 'data-deal-block="thread"' in rail
    assert 'data-deal-block="thread"' not in main
