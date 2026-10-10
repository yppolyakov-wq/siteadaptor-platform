"""T-8.4 (решение владельца Р-5): лимит активных акций на бесплатной лёгкой ступени.

План — docs/t8-4-assistant-plan-2026-10-10.md §1. Одна точка истины для трёх путей
активации: кнопка перехода в кабинете, ассистент «Schnell-Aktion» и beat расписания.

Лимит проверяется ТОЛЬКО при переходе в ``active``: черновиков и запланированных
акций можно готовить сколько угодно. Платные тенанты, полная платформа и демо-витрины
лимита не получают.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import gettext as _

from .state_machine import PromotionSM


class ActivationLimit(Exception):
    """Активация упёрлась в лимит бесплатной ступени."""

    def __init__(self, limit: int):
        super().__init__(f"active promotions limit {limit}")
        self.limit = limit


def active_limit(tenant) -> int | None:
    """Сколько акций может быть активно одновременно; ``None`` — без ограничения."""
    if tenant is None:
        return None
    from apps.core import storefront_profile

    if getattr(tenant, "is_demo", False):
        return None  # витрина платформы: показывает возможности, а не тариф
    if getattr(tenant, "subscription_status", "") == "active":
        return None
    if not storefront_profile.is_aktionen(tenant):
        return None  # полная платформа — свой тариф, лимит лёгкой ступени не про неё
    limit = getattr(settings, "LITE_FREE_ACTIVE_PROMOS", 5)
    return limit if limit and limit > 0 else None


def active_count(exclude=None) -> int:
    from .models import Promotion

    qs = Promotion.objects.filter(status="active")
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.count()


def can_activate(promo, tenant) -> bool:
    limit = active_limit(tenant)
    if limit is None or getattr(promo, "status", "") == "active":
        return True
    return active_count(exclude=promo) < limit


def activate(promo, tenant, *, actor=None):
    """Активировать акцию с проверкой лимита; ``ActivationLimit`` при отказе."""
    limit = active_limit(tenant)
    if not can_activate(promo, tenant):
        raise ActivationLimit(limit)
    return PromotionSM().apply(promo, "active", actor=actor)


def usage(tenant) -> dict | None:
    """Для счётчика «3 von 5 aktiv» — только у ограниченных тенантов."""
    limit = active_limit(tenant)
    if limit is None:
        return None
    used = active_count()
    return {"used": used, "limit": limit, "full": used >= limit}


def limit_message(limit: int) -> str:
    return _(
        "Mit dem kostenlosen Start sind bis zu %(n)s Aktionen gleichzeitig aktiv. "
        "Mehr Aktionen? Schreiben Sie uns: %(contact)s"
    ) % {"n": limit, "contact": contact_email()}


def contact_email() -> str:
    return getattr(settings, "PLATFORM_CONTACT_EMAIL", "") or "kontakt@siteadaptor.de"


def tenant_for_current_schema():
    """Тенант текущей схемы (beat работает в schema_context с FakeTenant без полей)."""
    from django.db import connection

    schema = getattr(connection, "schema_name", "public")
    if not schema or schema == "public":
        return None
    from apps.tenants.models import Tenant

    return Tenant.objects.filter(schema_name=schema).first()
