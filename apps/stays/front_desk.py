"""KA-12 Zimmer Z-5d/e: стойка — заезд/выезд (О-7) и списки дня «Heute» (Р-9).

План — docs/ka-12-w4-z5-front-desk-heute-plan-2026-10-25.md Р-6/Р-9.

Check-in/out — ОТМЕТКИ времени, не статус FSM. Check-out = штатный переход в
``fulfilled`` через ``core_transactions.apply_action`` (единственная точка денег,
выручки и «комната → dirty»); отметку выезда ставит сам переход (кнопка «Abgereist»,
доска и Heute — одинаково). Ранний выезд запрещён: ночи и деньги меняются только
явной правкой дат (E4.7a), иначе «показано ≠ проведено».
"""

import logging

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from apps.core import status_registry

logger = logging.getLogger(__name__)

LIST_LIMIT = 50


class FrontDeskError(Exception):
    """Действие стойки не применимо — текст для сотрудника."""


def _active(tenant=None) -> tuple:
    return status_registry.active_statuses_for("stay", tenant)


def checkin_allowed_statuses(tenant=None) -> tuple:
    """Заселять можно подтверждённую бронь (и свой «активный» статус), но не
    неподтверждённую заявку — по РОЛИ: intake (pending и свои «входящие») — нет."""
    descs = status_registry.all_descriptors("stay", tenant)
    return tuple(c for c in _active(tenant) if descs[c].role != "intake")


def _audit(action, booking, actor):
    from apps.core.audit import audit_event

    # Свой savepoint: сбой записи журнала не должен откатить отметку стойки.
    with transaction.atomic():
        audit_event(
            action=f"stays.{action}",
            resource_type="stay_booking",
            resource_id=booking.pk,
            actor=actor,
            context={"code": booking.reference_code},
        )


def check_in(booking, *, actor=None, today=None, now=None, tenant=None):
    """Отметить заселение. Повтор — FrontDeskError «bereits» без второго штампа."""
    from .models import StayBooking

    now = now or timezone.now()
    today = today or timezone.localdate()
    allowed = checkin_allowed_statuses(tenant)
    if booking.checked_in_at:
        raise FrontDeskError(_("Bereits eingecheckt."))
    if booking.status not in allowed:
        raise FrontDeskError(_("Bitte die Buchung zuerst bestätigen."))
    if booking.arrival > today:
        raise FrontDeskError(
            _("Anreise ist erst am %(day)s.")
            % {"day": date_format(booking.arrival, "SHORT_DATE_FORMAT")}
        )
    if booking.departure <= today:
        raise FrontDeskError(_("Abreisedatum ist schon erreicht."))
    with transaction.atomic():
        done = StayBooking.objects.filter(
            pk=booking.pk, checked_in_at__isnull=True, status__in=allowed
        ).update(checked_in_at=now)
        if not done:
            booking.refresh_from_db(fields=["checked_in_at", "status"])
            if booking.checked_in_at:
                raise FrontDeskError(_("Bereits eingecheckt."))
            raise FrontDeskError(_("Bitte die Buchung zuerst bestätigen."))
        booking.checked_in_at = now
        _audit("checked_in", booking, actor)
    return booking


def undo_check_in(booking, *, actor=None, tenant=None):
    """Снять ошибочную отметку заселения — пока гость не выехал и бронь активна."""
    from .models import StayBooking

    with transaction.atomic():
        done = StayBooking.objects.filter(
            pk=booking.pk,
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
            status__in=checkin_allowed_statuses(tenant),
        ).update(checked_in_at=None)
        if not done:
            raise FrontDeskError(_("Check-in kann nicht mehr zurückgenommen werden."))
        booking.checked_in_at = None
        _audit("check_in_undone", booking, actor)
    return booking


def check_out(booking, *, actor=None, today=None, tenant=None, extra=None):
    """Выезд: штатный переход в fulfilled (деньги/выручка/уборка) + отметка времени."""
    from apps.core import transactions as core_transactions

    today = today or timezone.localdate()
    if booking.arrival > today:
        raise FrontDeskError(
            _("Anreise ist erst am %(day)s.")
            % {"day": date_format(booking.arrival, "SHORT_DATE_FORMAT")}
        )
    if booking.departure > today:
        raise FrontDeskError(
            _("Abreise vor dem gebuchten Datum — bitte zuerst die Abreise in der Buchung ändern.")
        )
    with transaction.atomic():
        core_transactions.apply_action(
            "stay", booking, "fulfilled", actor=actor, extra=extra or {}, tenant=tenant
        )
    return booking


def stamp_checked_out(booking, now=None) -> None:
    """Отметка выезда (из FSM-перехода); повторный переход второй отметки не ставит."""
    from .models import StayBooking

    now = now or timezone.now()
    if StayBooking.objects.filter(pk=booking.pk, checked_out_at__isnull=True).update(
        checked_out_at=now
    ):
        booking.checked_out_at = now


def state(booking, *, today=None, tenant=None, allowed=None) -> dict:
    """Что показывать стойке у брони: отметки и доступные кнопки (без запросов в БД,
    если ``allowed`` передан — списки Heute считают его один раз)."""
    today = today or timezone.localdate()
    allowed = allowed if allowed is not None else checkin_allowed_statuses(tenant)
    status_ok = booking.status in allowed
    in_stay = booking.arrival <= today < booking.departure
    return {
        "checked_in_at": booking.checked_in_at,
        "checked_out_at": booking.checked_out_at,
        "can_check_in": status_ok and in_stay and not booking.checked_in_at,
        "can_undo": status_ok and bool(booking.checked_in_at) and not booking.checked_out_at,
        "can_check_out": status_ok and booking.arrival <= today and booking.departure <= today,
        "unconfirmed": not status_ok and booking.status in _active(tenant),
    }


# --- «Heute» (Р-9) --------------------------------------------------------------------


def _base_qs():
    from .models import GuestRegistration, StayBooking

    return (
        StayBooking.objects.select_related("customer", "unit", "room")
        .prefetch_related("extra_rooms")
        .annotate(has_registration=Exists(GuestRegistration.objects.filter(booking=OuterRef("pk"))))
    )


def today_lists(tenant=None, today=None) -> dict:
    """Одна точка списков дня: Anreisen / Abreisen / Im Haus (и виджет главной).

    Anreisen — все активные с заездом сегодня (неподтверждённая видна с бейджем,
    заселённые остаются с ✓). Abreisen — выезд сегодня: подтверждённые (не intake)
    и уже выехавшие (fulfilled-роль) с ✓. Im Haus — заселённые/живущие с прошлых
    дней, ещё не выехавшие."""
    today = today or timezone.localdate()
    descs = status_registry.all_descriptors("stay", tenant)
    active = _active(tenant)
    staying = tuple(c for c in active if descs[c].role != "intake")
    done = tuple(c for c, d in descs.items() if d.role == "done")
    qs = _base_qs()
    return {
        "arrivals": qs.filter(arrival=today, status__in=active).order_by("arrival", "pk"),
        "departures": qs.filter(departure=today, status__in=staying + done).order_by(
            "departure", "pk"
        ),
        "in_house": qs.filter(
            Q(arrival__lt=today) | Q(checked_in_at__isnull=False),
            status__in=staying,
            arrival__lte=today,
            departure__gt=today,
            checked_out_at__isnull=True,
        ).order_by("departure", "pk"),
    }
