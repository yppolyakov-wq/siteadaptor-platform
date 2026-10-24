"""KA-12 E6.4a: неявки клиента — считаются из статусов записей, не хранятся.

Один источник истины — `Booking.status`. Хранимый счётчик пришлось бы держать в FSM,
кастом-статусах, переносе и DSGVO-анонимизации (класс расхождений MX-2e). Считаем
только буквальный `no_show`: по роли реестра (cancelled) неявку от отмены не отличить.
"""

from django.db.models import Count, Max, Q

NO_SHOW_STATUSES = ("no_show",)


def summary(customer) -> dict:
    """{n: неявок, last: дата последней, visits: состоявшихся визитов}. Один запрос."""
    from .models import Booking

    if customer is None or getattr(customer, "pk", None) is None:
        return {"n": 0, "last": None, "visits": 0}
    agg = (
        Booking.objects.filter(customer_id=customer.pk)
        .order_by()
        .aggregate(
            n=Count("id", filter=Q(status__in=NO_SHOW_STATUSES)),
            last=Max("start", filter=Q(status__in=NO_SHOW_STATUSES)),
            visits=Count("id", filter=Q(status="fulfilled")),
        )
    )
    return {"n": agg["n"] or 0, "last": agg["last"], "visits": agg["visits"] or 0}


def counts_for(customer_ids) -> dict:
    """{customer_pk: неявок} одним агрегатом (Tagesplan, списки). `.order_by()` —
    иначе `Meta.ordering = ["start"]` попадёт в GROUP BY и развалит счёт (VS-2c)."""
    from .models import Booking

    ids = {pk for pk in customer_ids if pk}
    if not ids:
        return {}
    rows = (
        Booking.objects.filter(customer_id__in=ids, status__in=NO_SHOW_STATUSES)
        .values("customer_id")
        .annotate(n=Count("id"))
        .order_by()
    )
    return {r["customer_id"]: r["n"] for r in rows}
