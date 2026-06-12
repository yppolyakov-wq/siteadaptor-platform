"""Сервис онбординга: создание бизнеса (Tenant + Domain + первый владелец-User).

Выполняется в публичной схеме. User создаётся ВНУТРИ схемы арендатора, т.к.
django.contrib.auth — это TENANT_APP (у каждого бизнеса свои пользователи).
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context

from apps.core import modules

from .models import Domain, Tenant


def _base_domain() -> str:
    # В dev — siteadaptor.de:8000, в prod — siteadaptor.de. Берём из настроек,
    # с безопасным дефолтом.
    return getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")


def login_url_for(tenant) -> str:
    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    return f"{scheme}://{tenant.slug}.{_base_domain()}/accounts/login/"


def _new_tenant(*, business_name, slug, business_type, city, email) -> Tenant:
    return Tenant(
        schema_name=slug.replace("-", "_"),
        name=business_name,
        slug=slug,
        business_type=business_type,
        city=city,
        owner_email=email,
        subscription_status="trial",
        # Дедлайн триала — основа для beat-просрочки (trial→trial_expired→suspended).
        trial_ends_at=timezone.now() + timedelta(days=settings.BILLING_TRIAL_DAYS),
        enabled_modules=["catalog", "promotions", "publishing"],
        # Стартовый набор блоков по вертикали (Track D / D0b): нерекомендованные
        # опциональные модули выключены, владелец включает на /dashboard/modules/.
        disabled_modules=modules.default_disabled_for(business_type),
        enabled_locales=["de", "en"],
    )


@transaction.atomic
def start_business_provisioning(*, business_name, slug, business_type, city, email, password):
    """Мгновенная часть регистрации: Tenant (БЕЗ схемы) + Domain + фоновая задача.

    Создание схемы (~1 мин, миграции всех TENANT-приложений) уходит в Celery
    (tasks.provision_business) — пользователь сразу видит страницу ожидания.
    Пароль в брокер не попадает открытым — передаём хэш.
    """
    from django.contrib.auth.hashers import make_password

    tenant = _new_tenant(
        business_name=business_name,
        slug=slug,
        business_type=business_type,
        city=city,
        email=email,
    )
    tenant.provisioning_status = Tenant.PROVISIONING_PENDING
    tenant.auto_create_schema = False  # схему создаст фоновая задача
    tenant.save()

    base = _base_domain()
    Domain.objects.create(domain=f"{slug}.{base.split(':')[0]}", tenant=tenant, is_primary=True)

    password_hash = make_password(password)
    from .tasks import provision_business

    transaction.on_commit(lambda: provision_business.delay(str(tenant.pk), email, password_hash))
    return tenant


@transaction.atomic
def create_business(*, business_name, slug, business_type, city, email, password):
    """Синхронное создание бизнеса: Tenant + схема + Domain + владелец.

    Долгий путь (~1 мин: миграции всех TENANT-приложений) — для тестов и CLI.
    Публичная регистрация идёт через start_business_provisioning (фон).
    Возвращает (tenant, login_url).
    """
    tenant = _new_tenant(
        business_name=business_name,
        slug=slug,
        business_type=business_type,
        city=city,
        email=email,
    )
    tenant.save()  # auto_create_schema=True → создаётся схема + миграции TENANT_APPS

    base = _base_domain()
    domain_host = f"{slug}.{base.split(':')[0]}"  # без порта в самой записи Domain
    Domain.objects.create(domain=domain_host, tenant=tenant, is_primary=True)

    # Первый пользователь — внутри схемы арендатора.
    User = get_user_model()
    with tenant_context(tenant):
        User.objects.create_user(username=email, email=email, password=password)

    return tenant, login_url_for(tenant)


def schema_exists(schema_name: str) -> bool:
    with schema_context("public"):
        return Tenant.objects.filter(schema_name=schema_name).exists()
