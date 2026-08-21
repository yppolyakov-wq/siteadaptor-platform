"""MX-2c: сводный учёт ДОП-ПРОДАЖ — проданные опции по всем направлениям.

Требование владельца (v4 §6.2): отдельный пункт в разделе продаж, где видны ВСЕ
проданные доп-услуги («сколько завтраков завтра», «сколько аренд байка на заезд»),
при этом опция остаётся видимой в карточке своей сделки. Стало возможным после
MX-0: снимки несут id опции — немецкая метка перестала быть учётным ключом.

Сбор — Python-скан снимков за окно ИСПОЛНЕНИЯ (arrival/start/дата события/слот
выдачи): SME-объёмы, JSON-поля; отменённые сделки отфильтрованы через реестр
статусов (кастом-cancel тоже). Заказы без слота выдачи датируются днём создания.
"""

from django.apps import apps as django_apps
from django.urls import reverse

from apps.core import status_registry, transactions


def _cancelled(kind, tenant):
    return status_registry.cancelled_statuses_for(kind, tenant)


def has_any_options() -> bool:
    """Гейт входа: есть ли вообще опции у тенанта (для ссылки в Verkäufe)."""
    from apps.core.models import Extra

    return Extra.objects.filter(is_active=True).exists()


def sold_options(tenant, von, bis) -> list[dict]:
    """Строки проданных опций с днём исполнения в [von, bis].

    Строка: {option_id, label, amount_cents, kind, deal_ref, deal_url, day,
    status}. Опции без id (легаси-снимки до MX-0) агрегируются по метке с
    option_id="" — честно показываем, не теряем.
    """
    rows = []

    def _emit(kind, obj, snap_rows, day, ref, url):
        status = getattr(obj, "status", "")
        for e in snap_rows or []:
            if not isinstance(e, dict):
                continue
            label = e.get("label") or "—"
            cents = e.get("price_cents")
            if cents is None:
                # модификатор заказа: delta в евро-строке
                try:
                    cents = round(float(e.get("delta", "0")) * 100)
                except (TypeError, ValueError):
                    cents = 0
            rows.append(
                {
                    "option_id": str(e.get("id") or ""),
                    "label": label,
                    "amount_cents": int(cents or 0),
                    "amount_eur": int(cents or 0) / 100,
                    "kind": kind,
                    "kind_label": transactions.KIND_LABEL.get(kind, kind),
                    "deal_ref": ref,
                    "deal_url": url,
                    "day": day,
                    "status": status,
                }
            )

    if tenant.is_module_active("stays"):
        StayBooking = django_apps.get_model("stays", "StayBooking")
        qs = (
            StayBooking.objects.filter(arrival__gte=von, arrival__lte=bis)
            .exclude(status__in=_cancelled("stay", tenant))
            .exclude(extras=[])
        )
        for b in qs:
            _emit(
                "stay",
                b,
                b.extras,
                b.arrival,
                b.reference_code,
                reverse("stays:booking-detail", args=[b.pk]),
            )

    if tenant.is_module_active("booking"):
        Booking = django_apps.get_model("booking", "Booking")
        qs = (
            Booking.objects.filter(start__date__gte=von, start__date__lte=bis)
            .exclude(status__in=_cancelled("booking", tenant))
            .exclude(extras=[])
        )
        for b in qs:
            _emit(
                "booking",
                b,
                b.extras,
                b.start.date(),
                b.reference_code,
                reverse("booking:booking-detail", args=[b.pk]),
            )

    if tenant.is_module_active("events"):
        Ticket = django_apps.get_model("events", "Ticket")
        qs = (
            Ticket.objects.filter(event__starts_at__date__gte=von, event__starts_at__date__lte=bis)
            .exclude(status__in=_cancelled("ticket", tenant))
            .exclude(extras=[])
            .select_related("event")
        )
        for t in qs:
            _emit(
                "ticket",
                t,
                t.extras,
                t.event.starts_at.date(),
                t.reference_code,
                reverse("events:detail", args=[t.event_id]),
            )

    if tenant.is_module_active("orders"):
        from django.db.models import Q

        Order = django_apps.get_model("orders", "Order")
        qs = (
            Order.objects.exclude(status__in=_cancelled("order", tenant))
            .filter(
                Q(pickup_slot__date__gte=von, pickup_slot__date__lte=bis)
                | Q(pickup_slot__isnull=True, created_at__date__gte=von, created_at__date__lte=bis)
            )
            .prefetch_related("items")
        )
        for o in qs:
            day = o.pickup_slot.date() if o.pickup_slot else o.created_at.date()
            url = reverse("orders:order-detail", args=[o.pk])
            for item in o.items.all():
                mods = [m for m in (item.modifiers or []) if isinstance(m, dict) and m.get("id")]
                if mods:
                    _emit("order", o, mods, day, o.reference_code, url)

    rows.sort(key=lambda r: (r["day"], r["label"]))
    return rows


def summary(rows) -> list[dict]:
    """Σ по опциям: [{label, count, total_cents}] — «Frühstück × 12»."""
    agg = {}
    for r in rows:
        key = r["option_id"] or f"label:{r['label']}"
        entry = agg.setdefault(key, {"label": r["label"], "count": 0, "total_cents": 0})
        entry["count"] += 1
        entry["total_cents"] += r["amount_cents"]
    for entry in agg.values():
        entry["total_eur"] = entry["total_cents"] / 100
    return sorted(agg.values(), key=lambda e: (-e["count"], e["label"]))


KIND_LABELS = transactions.KIND_LABEL
