"""Выдача событий витрины — общая для листинга `/veranstaltung/` и блока «Liste» (LB-3d).

До LB-3d свёртка серий, отсчёт до старта и места жили инлайном во вьюхе листинга:
блок с событиями повторял бы их копией, и две выдачи разъехались бы при первой правке.
Здесь — ровно тот же порядок шагов, что у листинга:

1. `upcoming_events()` — опубликованные с будущим стартом, ближайшие первыми;
2. фасеты и сортировка — провайдером (`core.facets.provider_for("event")`), у вызывающего;
3. `group_dates()` — серия и заезды тура одной карточкой «+N Termine» (MX-6c);
4. `annotate_countdown()` — пилюля «Heute / Morgen / In N Tagen» у ближайших (RV3);
5. `attach_seat_counts()` — проданные места одним запросом на всю выдачу.
"""

from __future__ import annotations

from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

SOON_DAYS = 14  # «скоро» — две недели (RV3; фильтр блока «In den nächsten 14 Tagen»)


def upcoming_events() -> list:
    """Опубликованные события с будущим стартом, ближайшие первыми (база листинга)."""
    from .models import Event

    return list(
        Event.objects.filter(status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now())
        .prefetch_related("teachers")
        .order_by("starts_at")
    )


def group_dates(events) -> list:
    """Серия и заезды тура — ОДНОЙ карточкой (MX-6c, владелец: «одинаковые, разные
    даты — группируем»).

    Представитель группы — первый в ТЕКУЩЕМ порядке (по умолчанию по дате → ближайший;
    сортировка посетителя уважается), остальные даты — счётчик `more_dates` для бейджа
    «+N Termine». Обычные события (без тура и серии) не тронуты.
    """
    grouped, seen = [], {}
    for event in events:
        if event.tour_id:
            key = ("tour", event.tour_id)
        elif event.series_id:
            key = ("series", event.series_id)
        else:
            grouped.append(event)
            continue
        if key in seen:
            seen[key].more_dates += 1
        else:
            event.more_dates = 0
            seen[key] = event
            grouped.append(event)
    return grouped


def annotate_countdown(events) -> None:
    """RV3: компактный отсчёт до старта — конверсионный сигнал у ближайших (≤14 дней)."""
    today = timezone.localtime(timezone.now()).date()
    for event in events:
        days = (timezone.localtime(event.starts_at).date() - today).days
        event.starts_soon = 0 <= days <= SOON_DAYS
        event.countdown_label = (
            _("Today")
            if days <= 0
            else _("Tomorrow")
            if days == 1
            else _("In %(n)d days") % {"n": days}
        )


def starts_within(event, days: int = SOON_DAYS) -> bool:
    """Начинается ли событие в ближайшие `days` дней (фильтр блока «скоро»)."""
    today = timezone.localtime(timezone.now()).date()
    return 0 <= (timezone.localtime(event.starts_at).date() - today).days <= days


def attach_seat_counts(events) -> None:
    """Проданные места — одним запросом на всю выдачу.

    Карточка спрашивает «распродано» и «осталось мест» (`is_sold_out` дважды,
    `seats_left` раз), и каждое свойство — отдельный агрегат по билетам: 3–5 запросов
    на карточку. Подсказка `_tier_sold_hint` / `_seats_sold_hint` — те же числа,
    посчитанные заранее; модель читает их, если они есть. Только для показа: покупка
    берёт свой свежий экземпляр под блокировкой.
    """
    from apps.core import status_registry

    from .models import Ticket

    events = [e for e in events if e is not None]
    if not events:
        return
    rows = (
        Ticket.objects.filter(
            event_id__in=[e.pk for e in events],
            status__in=status_registry.active_statuses_for("ticket"),
        )
        .values("event_id", "tier_label")
        .annotate(n=Sum("quantity"))
    )
    by_event: dict = {}
    for row in rows:
        tiers = by_event.setdefault(row["event_id"], {})
        tiers[row["tier_label"]] = row["n"] or 0
    for event in events:
        tiers = by_event.get(event.pk, {})
        event._tier_sold_hint = tiers
        event._seats_sold_hint = sum(tiers.values())
