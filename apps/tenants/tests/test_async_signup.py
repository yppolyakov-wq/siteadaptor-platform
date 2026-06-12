"""Фоновая регистрация: мгновенный ответ + страница ожидания + провижининг в
Celery + письмо «сайт готов» (решение владельца 2026-06-12)."""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from apps.tenants import tasks, views
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import start_business_provisioning

EMAIL = "owner@blitz.test"


def _start(slug="blitz-baeck"):
    return start_business_provisioning(
        business_name="Blitz Bäckerei",
        slug=slug,
        business_type="bakery",
        city="Hilden",
        email=EMAIL,
        password="s3cretpass",
    )


def _cleanup(tenant):
    with connection.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE')
    Domain.objects.filter(tenant=tenant).delete()
    Tenant.objects.filter(pk=tenant.pk).delete()


@pytest.mark.django_db
def test_start_is_instant_and_pending():
    """Мгновенная часть: Tenant pending + Domain, БЕЗ создания схемы."""
    tenant = _start()
    try:
        assert tenant.provisioning_status == Tenant.PROVISIONING_PENDING
        assert Domain.objects.filter(tenant=tenant, is_primary=True).exists()
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                [tenant.schema_name],
            )
            assert cur.fetchone() is None  # схемы ещё нет — её создаст фон
    finally:
        Domain.objects.filter(tenant=tenant).delete()
        Tenant.objects.filter(pk=tenant.pk).delete()


@pytest.mark.django_db
def test_waiting_page_states():
    tenant = _start(slug="warte-baeck")
    try:
        request = RequestFactory().get(f"/anmeldung/{tenant.slug}/")
        body = views.signup_waiting(request, slug=tenant.slug)
        assert body.status_code == 200
        html = body.content.decode()
        assert "wird eingerichtet" in html and 'http-equiv="refresh"' in html

        Tenant.objects.filter(pk=tenant.pk).update(provisioning_status=Tenant.PROVISIONING_FAILED)
        html = views.signup_waiting(request, slug=tenant.slug).content.decode()
        assert "refresh" not in html  # при failed не крутимся вечно

        Tenant.objects.filter(pk=tenant.pk).update(provisioning_status=Tenant.PROVISIONING_READY)
        response = views.signup_waiting(request, slug=tenant.slug)
        assert response.status_code == 302
        assert response.url.endswith("/accounts/login/") and "warte-baeck." in response.url
    finally:
        Domain.objects.filter(tenant=tenant).delete()
        Tenant.objects.filter(pk=tenant.pk).delete()


@pytest.mark.django_db(transaction=True)
def test_provision_creates_schema_owner_and_emails():
    from django.contrib.auth.hashers import make_password

    tenant = _start(slug="voll-baeck")
    try:
        status = tasks.provision(tenant.pk, EMAIL, make_password("s3cretpass"))
        assert status == Tenant.PROVISIONING_READY
        tenant.refresh_from_db()
        assert tenant.provisioning_status == Tenant.PROVISIONING_READY

        User = get_user_model()
        with tenant_context(tenant):
            owner = User.objects.get(username=EMAIL)
            assert owner.check_password("s3cretpass")  # хэш доехал корректно

        ready = [m for m in mail.outbox if "bereit" in m.subject]
        assert ready and "/accounts/login/" in ready[0].body

        # идемпотентный повтор — no-op, второго письма нет
        sent_before = len(mail.outbox)
        assert tasks.provision(tenant.pk, EMAIL, "x") == Tenant.PROVISIONING_READY
        assert len(mail.outbox) == sent_before
    finally:
        _cleanup(tenant)
