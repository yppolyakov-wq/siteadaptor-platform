"""Тесты онбординга бизнеса: создание Tenant + Domain + первого User в схеме."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.utils import tenant_context

from apps.tenants.forms import BusinessSignupForm
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business


def _cleanup(tenant):
    with connection.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE')
    Domain.objects.filter(tenant=tenant).delete()
    Tenant.objects.filter(pk=tenant.pk).delete()


@pytest.mark.django_db(transaction=True)
def test_create_business_creates_tenant_domain_and_owner():
    tenant, login_url = create_business(
        business_name="Bäckerei Müller",
        slug="mueller",
        business_type="bakery",
        city="Hilden",
        email="owner@mueller.test",
        password="s3cretpass",
    )
    try:
        assert tenant.schema_name == "mueller"
        assert tenant.subscription_status == "trial"
        assert Domain.objects.filter(tenant=tenant, is_primary=True).exists()
        assert "mueller." in login_url and login_url.endswith("/accounts/login/")

        # Владелец создан ВНУТРИ схемы арендатора.
        User = get_user_model()
        with tenant_context(tenant):
            u = User.objects.get(email="owner@mueller.test")
            assert u.check_password("s3cretpass")
    finally:
        _cleanup(tenant)


@pytest.mark.django_db
def test_signup_form_rejects_reserved_and_bad_slug():
    base = {
        "business_name": "X",
        "business_type": "bakery",
        "city": "Y",
        "email": "a@b.test",
        "password1": "longenough1",
        "password2": "longenough1",
    }
    assert not BusinessSignupForm({**base, "slug": "admin"}).is_valid()  # reserved
    assert not BusinessSignupForm({**base, "slug": "Bad_Slug"}).is_valid()  # invalid chars


@pytest.mark.django_db
def test_signup_form_password_mismatch():
    form = BusinessSignupForm(
        {
            "business_name": "X",
            "slug": "shop",
            "business_type": "bakery",
            "city": "Y",
            "email": "a@b.test",
            "password1": "longenough1",
            "password2": "different2",
        }
    )
    assert not form.is_valid()
    assert "password2" in form.errors
