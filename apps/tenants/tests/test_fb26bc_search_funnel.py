"""FB-26b/c: поиск ниши на регистрации + воронка регистрации в `onboarding_report`.

Брошенная заявка не удаляется, а обезличивается: воронке нужен факт, личные данные уходят,
а по её старой ссылке ничего сделать нельзя."""

from datetime import timedelta
from importlib import import_module
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone

from apps.tenants import signup, views
from apps.tenants.models import SignupRequest
from apps.tenants.onboarding_metrics import signup_funnel

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_public")]


@pytest.fixture(autouse=True)
def _noon(monkeypatch):
    """CI #3850: прогон у полуночи по Берлину ронял тесты «сегодня»."""
    from apps.core.tests.clock import freeze_wednesday_noon

    freeze_wednesday_noon(monkeypatch)


FORM = {
    "business_name": "Bioladen Mitte",
    "slug": "fb26c-bio",
    "business_type": "",
    "directions": ["waren"],
    "city": "Hilden",
    "email": "owner@fb26c.test",
    "password1": "Wolke-Zimt-7x9q",
    "password2": "Wolke-Zimt-7x9q",
}


def _request(**kw):
    data = {**FORM, **kw}
    return SignupRequest.objects.create(
        email=data["email"],
        password_hash="x",
        business_name=data["business_name"],
        slug=data["slug"],
        business_type="retail",
        directions=data["directions"],
        city=data["city"],
    )


def test_page_has_niche_search_with_owner_words():
    request = RequestFactory().get("/registrieren/")
    request.session = {}
    html = views.BusinessSignupView.as_view()(request).content.decode()
    assert "data-niche-search" in html
    assert "Bioladen" in html and "Drogerie" in html  # слова владельца в data-terms


def test_stale_request_is_anonymized_not_deleted():
    old = _request()
    SignupRequest.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=7))
    signup.create_request(cleaned_data={**FORM, "email": "other@fb26c.test", "slug": "fb26c-x"})
    old.refresh_from_db()
    assert old.email == "" and old.password_hash == "" and old.business_name == ""
    assert old.directions == ["waren"] and old.business_type == "retail"


def test_replaced_request_is_anonymized_and_its_link_is_dead():
    first = _request()
    signup.create_request(cleaned_data={**FORM, "business_type": "retail"})
    first.refresh_from_db()
    assert first.email == ""
    response = views.signup_confirm(
        RequestFactory().get(f"/registrieren/bestaetigen/{first.token}/"), token=first.token
    )
    assert response.status_code == 404


def test_very_old_trace_is_deleted():
    old = _request()
    SignupRequest.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - signup.FUNNEL_RETENTION - timedelta(days=1)
    )
    signup.create_request(cleaned_data={**FORM, "email": "n@fb26c.test", "slug": "fb26c-n"})
    assert not SignupRequest.objects.filter(pk=old.pk).exists()


def test_funnel_counts_sent_confirmed_and_directions():
    _request()
    done = _request(email="b@fb26c.test", slug="fb26c-b", directions=["online"])
    SignupRequest.objects.filter(pk=done.pk).update(confirmed_at=timezone.now())
    data = signup_funnel(timezone.now() - timedelta(days=1))
    assert data["sent"] == 2 and data["confirmed"] == 1 and data["confirm_rate"] == 0.5
    assert data["directions"] == {"waren": 1, "online": 1}


def test_report_compares_before_and_after():
    _request()
    out = StringIO()
    tomorrow = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    call_command("onboarding_report", "--compare", tomorrow, stdout=out)
    text = out.getvalue()
    assert f"Registrierung vor {tomorrow}: 1 Anfragen" in text
    assert f"Registrierung ab {tomorrow}: 0 Anfragen" in text


def test_signup_still_works_after_anonymizing(settings):
    settings.SIGNUP_EMAIL_CONFIRMATION = True
    request = RequestFactory().post("/registrieren/", FORM, REMOTE_ADDR="10.26.3.1")
    request.session = import_module(settings.SESSION_ENGINE).SessionStore()
    views.BusinessSignupView.as_view()(request)
    assert SignupRequest.objects.filter(email=FORM["email"]).count() == 1
