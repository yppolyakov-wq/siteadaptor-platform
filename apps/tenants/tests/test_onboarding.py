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
        # D0b: стартовый набор блоков по вертикали — ровно формула реестра
        # (точные наборы по вертикалям проверяет apps/core/tests/test_modules.py).
        from apps.core import modules

        assert sorted(tenant.disabled_modules) == sorted(modules.default_disabled_for("bakery"))
        assert "promotions" not in tenant.disabled_modules  # рекомендованное включено
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


# --- AB4: чек-лист готовности сайта ------------------------------------------------
@pytest.mark.django_db
def test_completeness_empty_tenant_low_and_structured():
    from apps.tenants import onboarding
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(address="", opening_hours="", site_config={})
    r = onboarding.completeness(tenant)
    assert r["total"] == 5
    keys = {i["key"] for i in r["items"]}
    assert keys == {"banner", "hours", "contact", "offer", "legal"}
    assert {i["key"]: i["done"] for i in r["items"]}["hours"] is False
    assert r["percent"] <= 40  # почти ничего не заполнено


@pytest.mark.django_db
def test_completeness_marks_filled_items_done():
    from apps.tenants import onboarding
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(
        address="Hauptstr. 1, Hilden",
        opening_hours="Mo–Fr 9–18",
        site_config={"hero_image": "/m/banner.jpg"},
    )
    done = {i["key"]: i["done"] for i in onboarding.completeness(tenant)["items"]}
    assert done["banner"] and done["hours"] and done["contact"] and done["legal"]
    # offer зависит от каталога (в пустой схеме — нет)
    assert done["offer"] is False
