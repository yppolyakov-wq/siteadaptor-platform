"""Кросс-tenant данные клиентского аккаунта (P2.3c).

Брони живут в TENANT-схемах (Reservation + Customer), клиент портала — в
public (PortalUser). Связка — по email: обходим схемы арендаторов и собираем
брони клиента. Тенантов на платформе немного, обход дешёвый; результат
кэшируется на минуту (страница /konto/ — не realtime). `tenants` инжектится в
тестах (там физических схем нет, всё лежит в public — как в reconcile_schema).
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

CACHE_TTL = 60


def reservations_for_email(email: str, *, tenants=None, limit: int = 20) -> list[dict]:
    """Последние брони клиента по всем бизнесам (новые сверху)."""
    email = email.strip().lower()
    cache_key = f"konto_resv:{hashlib.sha256(email.encode()).hexdigest()}"
    try:
        cached = cache.get(cache_key)
    except Exception:  # noqa: BLE001 — кэш недоступен: собираем заново
        cached = None
    if cached is not None:
        return cached

    if tenants is None:
        tenants = get_tenant_model().objects.exclude(schema_name=get_public_schema_name())
    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    scheme = "http" if getattr(settings, "DEBUG", False) else "https"

    rows = []
    for tenant in tenants:
        with schema_context(tenant.schema_name):
            from apps.promotions.models import Reservation

            reservations = (
                Reservation.objects.filter(customer__email__iexact=email)
                .select_related("promotion")
                .order_by("-created_at")[:limit]
            )
            for r in reservations:
                rows.append(
                    {
                        "business": tenant.name,
                        "title": r.promotion.title_text,
                        "code": r.reference_code,
                        "quantity": r.quantity,
                        "status": r.status,
                        "created_at": r.created_at,
                        "url": f"{scheme}://{tenant.slug}.{base}/r/{r.reference_code}/",
                    }
                )

    rows.sort(key=lambda row: row["created_at"], reverse=True)
    rows = rows[:limit]
    try:
        cache.set(cache_key, rows, CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return rows
