"""G6 / F3: публичная заявка /anfrage/ + публичное Angebot /angebot/<token>/
(онлайн-принятие/отклонение) + письмо клиенту со сметой."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.jobs import public_views, services
from apps.jobs.models import Job
from apps.jobs.state_machine import JobSM
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kwargs):
    kwargs.setdefault("disabled_modules", [])  # jobs активен
    return TenantFactory.build(**kwargs)


def _req(method="get", path="/anfrage/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else _tenant()
    return request


def _quoted_job(email="kunde@test.de"):
    job = services.create_job(title="Bad streichen", name="Kunde", email=email)
    services.set_lines(job, [{"text": "Arbeit", "qty": 4, "unit_price": "50.00"}])
    return JobSM().apply(job, "quoted")


# --- заявка -----------------------------------------------------------------------


def test_anfrage_gating_404():
    request = _req(tenant=_tenant(disabled_modules=["jobs"]))
    with pytest.raises(Http404):
        public_views.anfrage(request)


def test_anfrage_creates_job():
    request = _req("post", data={"title": "Zaun bauen", "name": "Herr Meyer", "email": "m@t.de"})
    resp = public_views.anfrage(request)
    assert resp.status_code == 302
    job = Job.objects.get(title="Zaun bauen")
    assert job.status == "new"


def test_anfrage_requires_title_and_name():
    request = _req("post", data={"title": "", "name": ""})
    public_views.anfrage(request)
    assert not Job.objects.exists()


def test_anfrage_form_renders():
    body = public_views.anfrage(_req()).content.decode()
    assert "Request a quote" in body or "Anfrage" in body


# --- публичное Angebot ------------------------------------------------------------


def test_quoted_sends_customer_email():
    job = _quoted_job()
    assert Notification.objects.filter(dedupe_key=f"job:{job.id}:quoted:customer").exists()


def test_angebot_renders_with_lines():
    job = _quoted_job()
    body = public_views.angebot(_req(), token=job.public_token).content.decode()
    assert job.reference_code in body and "Arbeit" in body


def test_angebot_accept():
    job = _quoted_job()
    request = _req("post", path=f"/angebot/{job.public_token}/", data={"action": "accept"})
    resp = public_views.angebot(request, token=job.public_token)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.status == "accepted" and job.accepted_at is not None


def test_angebot_decline():
    job = _quoted_job()
    request = _req("post", path=f"/angebot/{job.public_token}/", data={"action": "decline"})
    public_views.angebot(request, token=job.public_token)
    job.refresh_from_db()
    assert job.status == "declined"


def test_angebot_accept_only_from_quoted():
    job = _quoted_job()
    JobSM().apply(job, "accepted")  # уже принято
    request = _req("post", path=f"/angebot/{job.public_token}/", data={"action": "decline"})
    public_views.angebot(request, token=job.public_token)
    job.refresh_from_db()
    assert job.status == "accepted"  # повторное решение игнорируется
