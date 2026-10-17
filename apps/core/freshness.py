"""Г3: «срок свежести» товаров и услуг в каталоге города.

План — docs/g3-g4-freshness-digest-plan-2026-10-17.md §2. Позиция, которую владелец
не подтверждал `CITY_FRESHNESS_DAYS` дней, уходит из каталога города (на собственном
сайте бизнеса она остаётся). Подтверждают ТОЛЬКО явные действия владельца: Save
формы, «Bestätigen» импорта, CSV-импорт, включение позиции, кнопка «Alles noch
aktuell». Поэтому штамп отдельный (`confirmed_at`), а не `updated_at` — тот сдвигает
каждая продажа и фоновая подгрузка фото.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def days() -> int:
    """Срок в днях; 0 — механизм выключен."""
    return int(getattr(settings, "CITY_FRESHNESS_DAYS", 60) or 0)


def warn_days() -> int:
    return int(getattr(settings, "CITY_FRESHNESS_WARN_DAYS", 7) or 0)


def stamp(obj) -> None:
    """Пометить объект подтверждённым ДО его сохранения (форма, импорт)."""
    obj.confirmed_at = timezone.now()


def confirm(obj) -> None:
    """Подтвердить сохранённый объект. Через save с `updated_at`: хук синка каталога
    города получает новый штамп и возвращает позицию, если она уже ушла."""
    obj.confirmed_at = timezone.now()
    obj.save(update_fields=["confirmed_at", "updated_at"])


def confirm_all(schema: str) -> int:
    """«Alles noch aktuell»: подтвердить все годные к показу товары и услуги схемы,
    затем реконсиляция каталога (`.update()` сигналов не шлёт — без неё ушедшие
    позиции вернулись бы только следующей ночью)."""
    from django.db import transaction

    from apps.aggregator.tasks import reconcile_city_catalog
    from apps.booking.models import Service
    from apps.catalog.models import Product

    now = timezone.now()
    n = Product.objects.filter(is_active=True, hide_in_city=False).update(confirmed_at=now)
    n += Service.objects.filter(is_active=True, hide_in_city=False).update(confirmed_at=now)
    stamp_key = int(now.timestamp())
    transaction.on_commit(
        lambda: reconcile_city_catalog.delay(
            dedupe_key=f"city-fresh-confirm:{schema}:{stamp_key}", tenant_schema=schema
        )
    )
    return n


def is_stale(tenant, confirmed_at) -> bool:
    """Позиция протухла для каталога города? Демо и выключенный механизм — никогда."""
    limit = days()
    if limit <= 0 or confirmed_at is None or getattr(tenant, "is_demo", False):
        return False
    return confirmed_at < timezone.now() - timedelta(days=limit)


def expiring(tenant) -> dict:
    """Счётчики для плашки и письма: скоро уйдут / уже ушли (только годные к показу)."""
    from apps.booking.models import Service
    from apps.catalog.models import Product

    empty = {"soon": 0, "gone": 0, "first_expiry": None}
    limit = days()
    if limit <= 0 or getattr(tenant, "is_demo", False):
        return empty
    now = timezone.now()
    gone_before = now - timedelta(days=limit)
    soon_before = now - timedelta(days=max(0, limit - warn_days()))
    result = dict(empty)
    first = None
    for model in (Product, Service):
        live = model.objects.filter(is_active=True, hide_in_city=False)
        result["gone"] += live.filter(confirmed_at__lt=gone_before).count()
        soon = live.filter(confirmed_at__gte=gone_before, confirmed_at__lt=soon_before)
        result["soon"] += soon.count()
        oldest = soon.order_by("confirmed_at").values_list("confirmed_at", flat=True).first()
        if oldest and (first is None or oldest < first):
            first = oldest
    if first is not None:
        result["first_expiry"] = timezone.localdate(first + timedelta(days=limit))
    return result


def banner(tenant) -> dict | None:
    """Плашка кабинета: что-то скоро уйдёт или уже ушло (только бизнесу из каталога)."""
    from apps.aggregator.visibility import listable

    try:
        if not listable(tenant):
            return None
        info = expiring(tenant)
    except Exception:  # noqa: BLE001 — плашка не роняет главную кабинета
        return None
    return info if (info["soon"] or info["gone"]) else None
