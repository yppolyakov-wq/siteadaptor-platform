"""KA-12 E4.4b (B6): правила отмены и самопереноса записи — одна точка.

Политика живёт на услуге (`cancel_window_hours`, `late_cancel`) и СНИМКОМ уходит в
запись при бронировании (`Booking.cancel_policy`): правка услуги не меняет условия
уже заключённых записей. Пустой снимок = старая запись (бесплатно до начала, возврат,
без самопереноса) — ровно прежнее поведение личного кабинета.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from .models import LATE_CANCEL_KEEP, LATE_CANCEL_REFUND, MAX_SELF_RESCHEDULES, Booking

POLICY_VERSION = 1


def snapshot(service) -> dict:
    """Снимок политики из СВЕЖЕЙ строки услуги (объект во вьюхе мог устареть)."""
    pk = getattr(service, "pk", None)
    if not pk:
        return {}
    from .models import Service

    row = Service.objects.filter(pk=pk).values("cancel_window_hours", "late_cancel").first()
    if row is None:
        return {}
    return {
        "v": POLICY_VERSION,
        "window_h": int(row["cancel_window_hours"]),
        "late": row["late_cancel"],
        "resched_max": MAX_SELF_RESCHEDULES,
    }


@dataclass(frozen=True)
class PolicyState:
    can_cancel: bool
    free: bool
    deadline: object  # aware datetime или None
    late_mode: str
    kept_cents: int
    can_reschedule: bool
    reschedules_left: int
    reason: str = ""


def _policy(booking) -> dict:
    p = booking.cancel_policy if isinstance(booking.cancel_policy, dict) else {}
    if p.get("v") != POLICY_VERSION:
        return {"window_h": 0, "late": LATE_CANCEL_REFUND, "resched_max": 0, "legacy": True}
    return p


def state(booking, now=None) -> PolicyState:
    from apps.core import status_registry

    now = now or timezone.now()
    p = _policy(booking)
    window = max(0, int(p.get("window_h") or 0))
    late = (
        p.get("late")
        if p.get("late") in (LATE_CANCEL_KEEP, LATE_CANCEL_REFUND)
        else LATE_CANCEL_REFUND
    )
    deadline = booking.start - timedelta(hours=window)
    active = booking.status in status_registry.active_statuses_for("booking")
    if not active or booking.start <= now:
        return PolicyState(False, False, deadline, late, 0, False, 0, "closed")
    free = now <= deadline
    kept = 0
    if not free and late == LATE_CANCEL_KEEP and booking.payment_state == Booking.PAYMENT_DEPOSIT:
        kept = int(booking.deposit_cents or 0)
    can_cancel, reason = True, ""
    if getattr(booking, "invoice_id", None):
        can_cancel, reason = False, "invoice"
    elif (
        not free
        and late == LATE_CANCEL_KEEP
        and booking.payment_state == Booking.PAYMENT_PAID
        and int(booking.deposit_cents or 0) < int(booking.price_cents or 0)
    ):
        # Оплачено больше депозита: частичный возврат «всё кроме Anzahlung» — v2.
        can_cancel, reason = False, "contact"
    left = max(0, int(p.get("resched_max") or 0) - int(booking.reschedule_count or 0))
    can_reschedule = bool(
        free and booking.service_id and not booking.group_code and left > 0 and not p.get("legacy")
    )
    return PolicyState(can_cancel, free, deadline, late, kept, can_reschedule, left, reason)


class NotCancellable(Exception):
    """Самоотмена запрещена условиями (счёт выставлен / нужен контакт / прошло)."""

    def __init__(self, reason: str = ""):
        super().__init__(reason)
        self.reason = reason


def _terms(booking, now) -> tuple[bool, str]:
    """(в бесплатном окне?, режим поздней отмены) — без учёта статуса (для повтора)."""
    p = _policy(booking)
    late = (
        p.get("late")
        if p.get("late") in (LATE_CANCEL_KEEP, LATE_CANCEL_REFUND)
        else LATE_CANCEL_REFUND
    )
    window = max(0, int(p.get("window_h") or 0))
    return now <= booking.start - timedelta(hours=window), late


def guest_cancel(booking, *, tenant=None, now=None):
    """Отмена гостем (ЛК / ссылка «Termin verwalten»). → (RefundResult, удержано ¢).

    Под блокировкой строк записи (и всей группы HF-6c, в порядке pk) статус и
    условия перепроверяются; FSM-хуки возвращают лимит акции, промокод и опции.
    Деньги — после коммита: в окне или при «immer erstatten» — `refund_payment`,
    иначе Anzahlung остаётся бизнесу и пишется выручкой (`retain_on_cancel`).
    Повтор по уже отменённой записи ДОВОДИТ недошедший возврат (он идемпотентен)."""
    from django.db import transaction

    from apps.core import refunds, status_registry
    from apps.core.money_contract import retain_on_cancel

    from .state_machine import BookingSM

    now = now or timezone.now()
    with transaction.atomic():
        members = Booking.objects.select_for_update().filter(pk=booking.pk)
        if booking.group_code:
            members = Booking.objects.select_for_update().filter(group_code=booking.group_code)
        members = list(members.order_by("pk"))
        head = next((b for b in members if b.pk == booking.pk), None)
        if head is None:
            raise NotCancellable("closed")
        cancelled = status_registry.cancelled_statuses_for("booking", tenant)
        st = state(head, now)
        if head.status not in cancelled:
            if not st.can_cancel:
                raise NotCancellable(st.reason or "closed")
            active = status_registry.active_statuses_for("booking", tenant)
            free_now = st.free
            from .notifications import enqueue_booking_email

            transaction.on_commit(lambda: enqueue_booking_email(head, "guest_cancelled"))
            for b in members:
                if b.status in active:
                    BookingSM().apply(b, "cancelled", actor=None)
                    if free_now and b.card_id:
                        _return_pass_credit(b)
    free, late = _terms(head, now)
    payer = next((b for b in members if (b.stripe_payment_intent or "").strip()), head)
    payer.refresh_from_db()
    result = refunds.RefundResult.NONE
    if free or late == LATE_CANCEL_REFUND:
        result = refunds.refund_payment("booking", payer, tenant)
    kept = 0
    if result != refunds.RefundResult.FAILED:
        retain_on_cancel("booking", payer, tenant)
        if not free and late == LATE_CANCEL_KEEP and payer.payment_state == Booking.PAYMENT_DEPOSIT:
            kept = int(payer.deposit_cents or 0)
    return result, kept


def _return_pass_credit(booking):
    """В-1: бесплатная отмена возвращает визит Mehrfachkarte (поздняя — сжигает).
    Отвязка `card` в той же транзакции — повтор отмены второй раз не вернёт."""
    from django.db.models import F

    from .models import Pass

    Pass.objects.filter(pk=booking.card_id, credits_used__gt=0).update(
        credits_used=F("credits_used") - 1, updated_at=timezone.now()
    )
    Booking.objects.filter(pk=booking.pk).update(card=None, updated_at=timezone.now())


class RescheduleRefused(Exception):
    """Самоперенос невозможен: `reason` — код для текста гостю."""

    def __init__(self, reason: str = ""):
        super().__init__(reason)
        self.reason = reason


def guest_reschedule(booking, *, start, tenant=None, now=None):
    """Самоперенос гостем на свободное время мастера с навыком (B6).

    Длина = снимок записи (вариант, единицы HF-7), часы/горизонт/минимальный срок —
    те же, что у витрины; цену не пересчитываем: другая сезонная цена или время вне
    правил акции → отказ («bitte neu buchen»); pool-опция держит день — перенос на
    другой день запрещён. Блокировки: ресурсы (старый и новый) по pk, затем строка
    записи — тот же порядок, что у кабинетного `move` (без встречного дедлока).
    Счётчик — условным UPDATE (двойной клик не даёт третьего переноса)."""
    from django.db import transaction
    from django.db.models import F

    from apps.core.models import Extra

    from . import availability, pricing
    from . import services as svc_mod
    from .models import Resource

    now = now or timezone.now()
    st = state(booking, now)
    if not st.can_reschedule:
        raise RescheduleRefused("limit" if st.free and st.reschedules_left == 0 else "closed")
    service = booking.service
    length = booking.end - booking.start
    minutes = int(length.total_seconds() // 60)
    end = start + length
    if start == booking.start:
        raise RescheduleRefused("same")
    current = booking.resource
    if availability.has_skill(service, current) and start in availability.service_slots(
        service,
        timezone.localtime(start).date(),
        resource=current,
        duration_minutes=minutes,
        exclude=booking.pk,
    ):
        target = current
    else:
        target = availability.assign_resource(
            service, start, duration_minutes=minutes, exclude=booking.pk
        )
    if target is None:
        raise svc_mod.SlotTaken()
    old_day, new_day = timezone.localtime(booking.start).date(), timezone.localtime(start).date()
    if pricing.variant_price_cents(
        service, new_day, booking.variant
    ) != pricing.variant_price_cents(service, old_day, booking.variant):
        raise RescheduleRefused("price")
    if booking.promotion_id:
        from apps.promotions.price_layer import promo_for_service

        hit = promo_for_service(service, start, target.pk)
        if hit is None or hit[0].pk != booking.promotion_id:
            raise RescheduleRefused("promo")
    if new_day != old_day:
        ids = [e.get("id") for e in (booking.extras or []) if isinstance(e, dict) and e.get("id")]
        if ids and Extra.objects.filter(pk__in=ids, tracker=Extra.TRACKER_POOL).exists():
            raise RescheduleRefused("extras")
    with transaction.atomic():
        list(
            Resource.objects.select_for_update()
            .filter(pk__in={booking.resource_id, target.pk})
            .order_by("pk")
        )
        fresh = Booking.objects.select_for_update().get(pk=booking.pk)
        st = state(fresh, now)
        if not st.can_reschedule:
            raise RescheduleRefused("closed")
        busy_until = svc_mod.occupied_end(service, end, fresh=True)
        overlaps = svc_mod.overlapping(target, start, busy_until or end).exclude(pk=fresh.pk)
        if svc_mod._would_overfill(target, overlaps, fresh.party_size):
            raise svc_mod.SlotTaken()
        limit = int(_policy(fresh).get("resched_max") or 0)
        updated = Booking.objects.filter(pk=fresh.pk, reschedule_count__lt=limit).update(
            start=start,
            end=end,
            occupied_until=busy_until,
            resource=target,
            reschedule_count=F("reschedule_count") + 1,
            reminder_sent_at=None,
            updated_at=timezone.now(),
        )
        if not updated:
            raise RescheduleRefused("limit")
        fresh.refresh_from_db()
        from .notifications import enqueue_booking_email

        transaction.on_commit(lambda: enqueue_booking_email(fresh, "moved"))
        transaction.on_commit(lambda: enqueue_booking_email(fresh, "guest_moved"))
    return fresh


_MANAGE_SALT = "termin-manage"


def manage_token(booking) -> str:
    """Подписанная ссылка гостя (код `T-XXXXXX` для изменений не годится — перебор).
    У группы HF-6c — по первой записи группы."""
    from django.core import signing

    head = booking
    if booking.group_code:
        head = (
            Booking.objects.filter(group_code=booking.group_code).order_by("start", "pk").first()
            or booking
        )
    return signing.dumps(str(head.pk), salt=_MANAGE_SALT)


def booking_from_token(token):
    from django.core import signing

    try:
        pk = signing.loads(token, salt=_MANAGE_SALT)
    except signing.BadSignature:
        return None
    return Booking.objects.select_related("service", "resource", "variant").filter(pk=pk).first()
