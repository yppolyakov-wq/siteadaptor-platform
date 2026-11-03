"""UX-D D1.4: главная отеля = сводка дня (макет «Kabinett aufräumen», артборд Home).

Одна функция `summary(request)` собирает всё, что нужно стойке утром: цифры дня,
списки «Heute» (заезды/выезды/уборка), «Braucht Aufmerksamkeit» и загрузку на 7 дней.
Источники — те же, что у экранов, куда ведут ссылки (front_desk.today_lists,
availability.occupancy_grid, money_contract), поэтому числа не расходятся. Каждый
блок fail-safe (`_safe`): упавший источник не роняет главную. Запросов — константа,
не зависит от числа броней (списки ограничены, загрузка — два запроса на окно).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.digest import _safe

LIST_LIMIT = 8  # строк в «Heute» на колонку — дальше ссылка «alle»
DAYS = 7


def _week(units, today) -> list[dict]:
    """Загрузка на 7 дней: занято из доступного (блокировки — не продаются)."""
    from . import availability

    if not units:
        return []
    days, rows = availability.occupancy_grid(units, today, DAYS)
    out = []
    for i, day in enumerate(days):
        total = occupied = 0
        for unit, cells in rows:
            cell = cells[i]
            if cell["blocked"]:
                continue
            total += unit.quantity
            occupied += max(unit.quantity - cell["free"], 0)
        pct = round(100 * occupied / total) if total else 0
        out.append({"day": day, "occupied": occupied, "total": total, "pct": pct})
    return out


def _unpaid(tenant) -> dict:
    """«Ждём денег» — РОВНО строки экрана Offene Posten по броням номеров
    (finance.bank.deal_open_items: оплата на месте — не долг, сделка со счётом —
    позиция счёта, платёжная книга — одним запросом на список)."""
    from apps.finance import bank

    rows = bank.deal_open_items(tenant, "stay")
    return {"count": len(rows), "amount": sum((r["amount"] for r in rows), Decimal("0"))}


def _gap(units) -> dict | None:
    """Первая короткая свободная «дыра» между бронями (кандидат на Lücken-Deal)."""
    from . import gaps

    found = gaps.short_gaps(units, max_nights=3, horizon=60, first_only=True)
    if not found:
        return None
    unit, first_night, nights = found[0]
    return {"unit": unit, "start": first_night, "end": first_night + timedelta(days=nights)}


def summary(request) -> dict:
    """Контекст `stays/_hotel_home.html`. Без побочных эффектов."""
    from apps.core import drawer
    from apps.core.permissions import has_perm
    from apps.core.templatetags.cabinet import can_open

    from . import front_desk
    from .models import Room, StayBooking, StaySettings, StayUnit

    tenant = request.tenant
    today = timezone.localdate()
    units = _safe(lambda: list(StayUnit.objects.filter(is_active=True).order_by("name")), [])
    lists = _safe(lambda: front_desk.today_lists(tenant, today), None)

    def _rows(key):
        if lists is None:
            return [], 0
        qs = lists[key]
        rows = list(qs[:LIST_LIMIT])
        allowed = front_desk.checkin_allowed_statuses(tenant)
        for b in rows:
            b.desk = front_desk.state(b, today=today, tenant=tenant, allowed=allowed)
        return rows, (qs.count() if len(rows) == LIST_LIMIT else len(rows))

    arrivals, arrivals_n = _safe(lambda: _rows("arrivals"), ([], 0))
    departures, departures_n = _safe(lambda: _rows("departures"), ([], 0))
    week = _safe(lambda: _week(units, today), [])
    dirty = _safe(
        lambda: list(
            Room.objects.filter(is_active=True, unit__is_active=True, housekeeping=Room.HK_DIRTY)
            .select_related("unit")
            .order_by("unit__name", "number")[:LIST_LIMIT]
        ),
        [],
    )
    units_with_rooms = _safe(
        lambda: set(Room.objects.filter(is_active=True).values_list("unit_id", flat=True)), set()
    )
    no_room = _safe(
        lambda: StayBooking.objects.filter(
            unit_id__in=units_with_rooms,
            room__isnull=True,
            departure__gt=today,
            status__in=front_desk.checkin_allowed_statuses(tenant),
        ).count(),
        0,
    )

    # «unbestätigt» — как у стойки (front_desk.state): активна, но ещё не допускает
    # Check-in (роль intake, вкл. свои статусы владельца), а не литерал "pending"
    def _unconfirmed():
        waiting = set(front_desk._active(tenant)) - set(front_desk.checkin_allowed_statuses(tenant))
        return StayBooking.objects.filter(status__in=waiting, departure__gt=today).count()

    unconfirmed = _safe(_unconfirmed, 0)
    unread = 0
    if tenant.is_module_active("inbox"):

        def _unread():
            from apps.inbox.models import Conversation

            return Conversation.objects.filter(unread_for_staff=True).count()

        unread = _safe(_unread, 0)
    gap = _safe(lambda: _gap(units), None) if units else None
    gap_deal_on = _safe(lambda: StaySettings.load().gap_max_nights > 0, True)
    attention = no_room or unconfirmed or unread or gap
    return {
        "hotel_home": True,
        "hh_today": today,
        "hh_units_total": sum(u.quantity for u in units),
        "hh_week": week,
        "hh_today_occ": week[0] if week else None,
        "hh_arrivals": arrivals,
        "hh_arrivals_n": arrivals_n,
        "hh_departures": departures,
        "hh_departures_n": departures_n,
        "hh_dirty": dirty,
        "hh_unpaid": _safe(lambda: _unpaid(tenant), {"count": 0, "amount": Decimal("0")}),
        "hh_finance": tenant.is_module_active("finance"),
        "hh_no_room": no_room,
        "hh_unconfirmed": unconfirmed,
        "hh_unread": unread,
        "hh_gap": gap,
        "hh_gap_deal_on": gap_deal_on,
        "hh_attention": bool(attention),
        "hh_can_new": can_open(request, "stays:stay-new"),
        # кнопки стойки — те же права, что у шторки брони (Check-in/out — «Rezeption»,
        # «Bestätigen»/«Sauber» — правка продаж)
        "hh_can_front_desk": has_perm(request.user, "rezeption.edit"),
        "hh_can_edit": has_perm(request.user, "verkaeufe.edit"),
        # после кнопки — обратно к спискам, без ?buchung= (иначе шторка открылась бы снова)
        "hh_next": drawer.without_params(request.get_full_path(), *drawer.DRAWER_PARAMS)
        + "#hh-today",
        "hh_autoopen": _autoopen(request),
    }


def _autoopen(request) -> str:
    """?buchung=<uuid> (ссылка из письма/уведомления, редирект без JS) — открыть шторку."""
    from django.urls import reverse

    from . import rate_plans
    from .models import StayBooking

    pk = rate_plans.parse_uuid(request.GET.get("buchung"))
    if pk is None or not StayBooking.objects.filter(pk=pk).exists():
        return ""
    return reverse("stays:booking-detail", args=[pk])
