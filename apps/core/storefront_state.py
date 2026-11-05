"""Почему витрина бизнеса сейчас закрыта для гостя («bald online», AIS-A A-0).

Единственный источник условия: `PendingStorefrontMiddleware` и помощник читают его, а не
повторяют проверки. Исключения (кабинет, вход, вебхуки, сам владелец) решает middleware."""

from __future__ import annotations


def hidden_reasons(tenant) -> list[str]:
    """Коды причин ([] — витрина открыта): `email_pending`, `unpublished`."""
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return []
    reasons = []
    if getattr(tenant, "email_pending", False):
        reasons.append("email_pending")
    if getattr(tenant, "published_at", True) is None:  # AIS-W W4-1
        reasons.append("unpublished")
    return reasons


def orders_active(tenant) -> bool:
    """Открыт ли онлайн-заказ на витрине (модуль заказов, с пакетом и зависимостями внутри
    `is_module_active`). Единственный источник для вьюх витрины и помощника (AIS-A A-0)."""
    return tenant is not None and tenant.is_module_active("orders")


def booking_active(tenant) -> bool:
    """Открыта ли онлайн-запись (услуги/столы)."""
    return tenant is not None and tenant.is_module_active("booking")


def stays_active(tenant) -> bool:
    """Открыта ли онлайн-бронь номеров."""
    return tenant is not None and tenant.is_module_active("stays")
