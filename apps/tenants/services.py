"""Сервис онбординга: создание бизнеса (Tenant + Domain + первый владелец-User).

Выполняется в публичной схеме. User создаётся ВНУТРИ схемы арендатора, т.к.
django.contrib.auth — это TENANT_APP (у каждого бизнеса свои пользователи).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django_tenants.utils import schema_context, tenant_context

from .models import Domain, Tenant


def _base_domain() -> str:
    # В dev — siteadaptor.de:8000, в prod — siteadaptor.de. Берём из настроек,
    # с безопасным дефолтом.
    return getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")


@transaction.atomic
def create_business(*, business_name, slug, business_type, city, email, password):
    """Создаёт Tenant (+ его PG-схему), Domain и первого пользователя-владельца.

    Возвращает (tenant, login_url).
    """
    schema_name = slug.replace("-", "_")

    tenant = Tenant(
        schema_name=schema_name,
        name=business_name,
        slug=slug,
        business_type=business_type,
        city=city,
        owner_email=email,
        subscription_status="trial",
        enabled_modules=["catalog", "promotions", "publishing"],
        enabled_locales=["de", "en"],
    )
    tenant.save()  # auto_create_schema=True → создаётся схема + миграции TENANT_APPS

    base = _base_domain()
    domain_host = f"{slug}.{base.split(':')[0]}"  # без порта в самой записи Domain
    Domain.objects.create(domain=domain_host, tenant=tenant, is_primary=True)

    # Первый пользователь — внутри схемы арендатора.
    User = get_user_model()
    with tenant_context(tenant):
        User.objects.create_user(username=email, email=email, password=password)

    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    login_url = f"{scheme}://{slug}.{base}/accounts/login/"
    return tenant, login_url


def schema_exists(schema_name: str) -> bool:
    with schema_context("public"):
        return Tenant.objects.filter(schema_name=schema_name).exists()
