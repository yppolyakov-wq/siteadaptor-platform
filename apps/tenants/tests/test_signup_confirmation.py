"""AB5.1: double-opt-in регистрации бизнеса (план signup-confirm-wizard-plan-2026-07-17).

POST /registrieren/ создаёт ТОЛЬКО SignupRequest + письмо; Tenant/Domain появляются
после клика по ссылке подтверждения. Вьюхи — через RequestFactory (конвенция);
urlconf public (reverse 'business-signup-confirm' живёт в urls_public).
"""

from importlib import import_module

import pytest
from django.conf import settings
from django.core import mail
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.tenants import views
from apps.tenants.models import Domain, SignupRequest, Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_public")]

FORM = {
    "business_name": "Blitz Bäckerei",
    "slug": "blitz-doi",
    "business_type": "bakery",
    "city": "Hilden",
    "email": "owner@blitz-doi.test",
    "password1": "s3cretpass",
    "password2": "s3cretpass",
}
_ip = iter(range(1, 250))


def _post_signup(data=None, **extra):
    # Уникальный REMOTE_ADDR на запрос — rate-limit (5/ч/IP) не флейкает между тестами.
    rf = RequestFactory()
    request = rf.post("/registrieren/", data or FORM, REMOTE_ADDR=f"10.9.8.{next(_ip)}", **extra)
    engine = import_module(settings.SESSION_ENGINE)
    request.session = engine.SessionStore()
    return views.BusinessSignupView.as_view()(request)


def _confirm(token):
    request = RequestFactory().get(f"/registrieren/bestaetigen/{token}/")
    return views.signup_confirm(request, token=token)


def _cleanup_tenant(slug):
    tenant = Tenant.objects.filter(slug=slug).first()
    if tenant:
        Domain.objects.filter(tenant=tenant).delete()
        Tenant.objects.filter(pk=tenant.pk).delete()


def test_post_creates_request_and_email_not_tenant():
    response = _post_signup()
    assert response.status_code == 200
    req = SignupRequest.objects.get(email=FORM["email"])
    assert not Tenant.objects.filter(slug=FORM["slug"]).exists()
    assert req.password_hash and not req.password_hash.startswith("s3cret")  # только хэш
    assert len(mail.outbox) == 1
    assert req.token in mail.outbox[0].body and "best" in mail.outbox[0].subject.lower()
    assert mail.outbox[0].to == [FORM["email"]]
    html = response.content.decode()
    assert FORM["email"] in html and req.token in html  # адрес + resend-форма


def test_confirm_provisions_and_is_idempotent():
    _post_signup()
    req = SignupRequest.objects.get(email=FORM["email"])
    try:
        response = _confirm(req.token)
        assert response.status_code == 302 and f"/anmeldung/{FORM['slug']}/" in response.url
        tenant = Tenant.objects.get(slug=FORM["slug"])
        assert tenant.provisioning_status == Tenant.PROVISIONING_PENDING
        assert Domain.objects.filter(tenant=tenant, is_primary=True).exists()
        req.refresh_from_db()
        assert req.is_confirmed and req.tenant_id == tenant.pk

        # Повторный клик — идемпотентно: тот же редирект, второго тенанта нет.
        again = _confirm(req.token)
        assert again.status_code == 302 and f"/anmeldung/{FORM['slug']}/" in again.url
        assert Tenant.objects.filter(slug=FORM["slug"]).count() == 1
    finally:
        _cleanup_tenant(FORM["slug"])


def test_confirm_invalid_and_expired_token():
    assert _confirm("kein-solcher-token").status_code == 404

    _post_signup()
    req = SignupRequest.objects.get(email=FORM["email"])
    SignupRequest.objects.filter(pk=req.pk).update(
        created_at=timezone.now() - SignupRequest.CONFIRM_TTL * 2
    )
    response = _confirm(req.token)
    assert response.status_code == 410
    assert "abgelaufen" in response.content.decode()
    assert not Tenant.objects.filter(slug=FORM["slug"]).exists()


def test_confirm_when_slug_taken_meanwhile():
    _post_signup()
    req = SignupRequest.objects.get(email=FORM["email"])
    # Кто-то занял slug между POST и кликом (заявка его не резервирует).
    rival = Tenant(schema_name=FORM["slug"].replace("-", "_"), name="Rival", slug=FORM["slug"])
    rival.auto_create_schema = False
    rival.save()
    try:
        response = _confirm(req.token)
        assert response.status_code == 409
        assert "vergeben" in response.content.decode()
        req.refresh_from_db()
        assert not req.is_confirmed  # заявка не сожжена — можно зарегистрироваться заново
    finally:
        Tenant.objects.filter(pk=rival.pk).delete()


def test_resend_sends_again_and_rate_limits():
    _post_signup()
    req = SignupRequest.objects.get(email=FORM["email"])
    mail.outbox.clear()

    def resend():
        request = RequestFactory().post("/registrieren/erneut-senden/", {"token": req.token})
        return views.signup_resend(request)

    for _ in range(3):
        assert resend().status_code == 200
    assert len(mail.outbox) == 3
    blocked = resend()  # 4-я за 10 минут — лимит
    assert len(mail.outbox) == 3 and "Zu viele" in blocked.content.decode()

    # Битый токен → тихий редирект на регистрацию (без утечки существования).
    request = RequestFactory().post("/registrieren/erneut-senden/", {"token": "nope"})
    assert views.signup_resend(request).status_code == 302


def test_honeypot_fakes_success_without_side_effects():
    response = _post_signup({**FORM, "website": "https://spam.example"})
    assert response.status_code == 200
    assert not SignupRequest.objects.filter(email=FORM["email"]).exists()
    assert not Tenant.objects.filter(slug=FORM["slug"]).exists()
    assert len(mail.outbox) == 0


def test_duplicate_email_replaces_pending_request():
    _post_signup()
    first = SignupRequest.objects.get(email=FORM["email"])
    _post_signup({**FORM, "slug": "blitz-doi-2"})
    pending = SignupRequest.objects.filter(email=FORM["email"])
    assert pending.count() == 1  # старая заявка заменена
    assert pending.get().token != first.token


@override_settings(SIGNUP_EMAIL_CONFIRMATION=False)
def test_flag_off_keeps_direct_flow():
    response = _post_signup()
    try:
        assert response.status_code == 302 and f"/anmeldung/{FORM['slug']}/" in response.url
        assert Tenant.objects.filter(slug=FORM["slug"]).exists()
        assert not SignupRequest.objects.filter(email=FORM["email"]).exists()
    finally:
        _cleanup_tenant(FORM["slug"])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
def test_console_backend_shows_direct_link():
    """Без Resend/SMTP письмо не уходит — ссылка видна прямо на странице."""
    response = _post_signup()
    req = SignupRequest.objects.get(email=FORM["email"])
    assert f"/registrieren/bestaetigen/{req.token}/" in response.content.decode()
