"""SH-23d (решение владельца Р-4): удержание места без оплаты.

«Счёт на 14 дней» и «Vorkasse 3 дня» означают, что место/номер/билет держатся
ровно до срока: без экспирации Zahlungsziel заморозил бы инвентарь на две недели
(и anti-oversell работал бы против владельца). Экспирация — ШТАТНЫЙ путь FSM
(`cancelled`), поэтому ёмкость, склад, лимит акции и письма отрабатывают, как
при обычной отмене; повторный проход идемпотентен — отменённая сделка выпадает
из выборки.

Паттерн взят у `orders.tasks.expire_due_anprobe`: блокировка строки и повторная
проверка ПОД локом (иначе оплата «в последнюю минуту» затирается устаревшим
снимком).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from apps.core import money_contract, status_registry, transactions

logger = logging.getLogger(__name__)

# Виды сделок, у которых удержание имеет смысл: место/номер/билет физически
# заняты. Заказ ведёт свой TTL (Anprobe), заявка ничего не блокирует.
HOLD_KINDS = ("booking", "stay", "ticket")

# Состояния «денег ещё нет» per-kind (те же, что у ERP-2 «Offene Posten»).
_UNPAID = money_contract.UNPAID_HOLD_STATES


def expire_overdue(tenant, *, now=None, kinds=HOLD_KINDS) -> int:
    """Отменить сделки текущей схемы, у которых прошёл срок оплаты.

    Возвращает число отменённых. Сделка без `payment_due_at` не трогается
    никогда — срок ставится только при способах, которые его требуют (счёт и
    Vorkasse), поэтому «оплата на месте» и онлайн-оплата не экспирируются.
    """
    now = now or timezone.now()
    total = 0
    for kind in kinds:
        module = transactions.KIND_MODULE.get(kind)
        if module and tenant is not None and not tenant.is_module_active(module):
            continue
        model = transactions.model_for(kind)
        if model is None:
            continue
        cancelled = status_registry.cancelled_statuses_for(kind, tenant)
        pks = list(
            model.objects.filter(payment_due_at__lt=now, payment_state__in=_UNPAID[kind])
            .exclude(status__in=list(cancelled))
            .values_list("pk", flat=True)[:500]
        )
        for pk in pks:
            try:
                with transaction.atomic():
                    obj = model.objects.select_for_update().get(pk=pk)
                    if (
                        not obj.payment_due_at
                        or obj.payment_due_at >= now
                        or obj.payment_state not in _UNPAID[kind]
                        or obj.status in cancelled
                    ):
                        continue  # оплатили/закрыли под локом — не трогаем
                    transactions.sm_for(kind).apply(obj, "cancelled", actor="system:payment-hold")
                    total += 1
            except Exception:  # noqa: BLE001 — одна сделка не роняет проход
                logger.exception("payment-hold: не удалось отменить %s %s", kind, pk)
                continue
    return total


# --- KA-P6: удержание на время онлайн-оплаты -----------------------------------------

#: Сколько держать номер/время/место, пока клиент на странице оплаты Stripe. 24 ч —
#: максимум жизни сессии Stripe; напоминание B2 (через 6 ч) ведёт на новую сессию,
#: которая удержание продлевает.
ONLINE_HOLD = timedelta(hours=24)
#: Сессия Stripe закрывается раньше конца удержания: оплата «в последнюю секунду»
#: уже не пройдёт, когда сделка снимается.
SESSION_MARGIN = timedelta(minutes=15)


#: Stripe принимает `expires_at` не раньше чем через 30 минут от создания сессии.
STRIPE_MIN_SESSION = timedelta(minutes=30)
#: SEC-D3: отложенный способ (SEPA) зачисляется до ~14 дней — держим сделку дольше.
PROCESSING_HOLD = timedelta(days=14)


def start_online_hold(obj, *, now=None) -> int | None:
    """Поставить срок удержания сделки на время онлайн-оплаты.

    Возвращает `expires_at` для сессии Stripe (unix-время) или None — сессия без своего
    срока (поздняя оплата отменённой сделки вернётся автоматически, `settle_late_payment`).

    SEC-D6 (аудит 2026-11-01): срок ставится один раз и не продлевается. Раньше каждое
    открытие страницы оплаты сдвигало его на сутки вперёд, и место держалось бессрочно.
    - Срока ещё нет: сутки от создания сделки; сделка старше (владелец прислал ссылку
      на оплату позже) — сутки от сейчас.
    - Срок уже есть (первая сессия, Vorkasse, счёт): не трогаем, сессия живёт до него.
    """
    now = now or timezone.now()
    current = getattr(obj, "payment_due_at", None)
    if current is None:
        due = now + ONLINE_HOLD
        created = getattr(obj, "created_at", None)
        if (
            created is not None
            and created + ONLINE_HOLD >= now + STRIPE_MIN_SESSION + SESSION_MARGIN
        ):
            due = created + ONLINE_HOLD
        type(obj).objects.filter(pk=obj.pk).update(payment_due_at=due)
        obj.payment_due_at = due
    else:
        due = current
    expires = min(due, now + ONLINE_HOLD) - SESSION_MARGIN
    if expires - now < STRIPE_MIN_SESSION:
        return None
    return int(expires.timestamp())


#: SEC-D3: metadata.kind Checkout → (вид сделки, ключ id в metadata).
_PROCESSING_KINDS = {
    "booking_deposit": ("booking", "booking_id"),
    "stay_deposit": ("stay", "booking_id"),
    "event_ticket": ("ticket", "ticket_id"),
    "event_installment": ("ticket", "ticket_id"),
}


def _inflight_key(schema: str, kind: str, deal_id: str) -> str:
    return f"pay-inflight:{schema}:{kind}:{deal_id}"


def _processing_target(meta: dict):
    spec = _PROCESSING_KINDS.get(str(meta.get("kind") or ""))
    schema = str(meta.get("tenant_schema") or "")
    if spec is None or not schema:
        return None
    kind, key = spec
    deal_id = str(meta.get(key) or "")
    model = transactions.model_for(kind)
    if model is None or not deal_id:
        return None
    return schema, kind, deal_id, model


def _service_start(kind: str, obj):
    """Начало услуги: удержание не держит место дольше, чем есть смысл."""
    from datetime import datetime, time

    if kind == "stay" and getattr(obj, "arrival", None):
        return timezone.make_aware(datetime.combine(obj.arrival, time.min))
    if kind == "booking":
        return getattr(obj, "start", None)
    if kind == "ticket":
        return getattr(getattr(obj, "event", None), "starts_at", None)
    return None


def hold_while_processing(meta: dict, *, now=None) -> bool:
    """SEC-D3: Checkout завершён, а деньги ещё в пути (SEPA). Сделку не снимаем по
    сроку онлайн-оплаты: срок продлевается до `PROCESSING_HOLD`, но не дальше начала
    услуги. Иначе `expire_overdue` отменял бронь через сутки, а пришедшая через три
    дня оплата возвращалась клиенту.

    Ревью волны 1: продлевается ОДИН раз — только обычное суточное удержание (повторная
    SEPA-сессия или повтор события Stripe срок не двигают), а пока деньги в пути,
    повторная оплата закрыта (`payment_in_flight`). True — срок продлён."""
    target = _processing_target(meta)
    if target is None:
        return False
    schema, kind, deal_id, model = target
    from django.core.cache import cache
    from django.core.exceptions import ValidationError
    from django_tenants.utils import schema_context

    now = now or timezone.now()
    due = now + PROCESSING_HOLD
    try:
        with schema_context(schema), transaction.atomic():
            obj = (
                model.objects.select_for_update()
                .filter(pk=deal_id, payment_state__in=_UNPAID[kind])
                .first()
            )
            if obj is None:
                return False
            current = obj.payment_due_at
            if current is not None and current > now + ONLINE_HOLD + SESSION_MARGIN:
                return False  # уже продлено (или длинное удержание Vorkasse/счёта)
            start = _service_start(kind, obj)
            if start is not None:
                due = min(due, start)
            if current is not None and due <= current:
                return False
            model.objects.filter(pk=obj.pk).update(payment_due_at=due)
    except (ValidationError, ValueError):
        return False
    try:
        cache.set(_inflight_key(schema, kind, deal_id), 1, int(PROCESSING_HOLD.total_seconds()))
    except Exception:  # noqa: BLE001 — кэш недоступен: продление срока уже записано
        logger.warning("payment-hold: in-flight marker not stored")
    return True


#: SEC-D3: после неудачного SEPA-списания — время на оплату другим способом.
FAILED_GRACE = timedelta(hours=1)


def release_after_failed(meta: dict, *, now=None) -> bool:
    """SEC-D3 (ревью волны 1): списание не прошло — место больше не держим 14 дней.
    Срок удержания — через час (клиент успеет заплатить картой), дальше сделку снимает
    `expire_overdue`."""
    target = _processing_target(meta)
    if target is None:
        return False
    schema, kind, deal_id, model = target
    from django.core.cache import cache
    from django.core.exceptions import ValidationError
    from django_tenants.utils import schema_context

    due = (now or timezone.now()) + FAILED_GRACE
    try:
        with schema_context(schema):
            updated = (
                model.objects.filter(pk=deal_id, payment_state__in=_UNPAID[kind])
                .filter(payment_due_at__gt=due)
                .update(payment_due_at=due)
            )
    except (ValidationError, ValueError):
        return False
    try:
        cache.delete(_inflight_key(schema, kind, deal_id))
    except Exception:  # noqa: BLE001
        pass
    return bool(updated)


def clear_in_flight(meta: dict) -> None:
    """Деньги пришли (или окончательно нет) — повторная оплата снова доступна."""
    target = _processing_target(meta)
    if target is None:
        return
    schema, kind, deal_id, _model = target
    from django.core.cache import cache

    try:
        cache.delete(_inflight_key(schema, kind, deal_id))
    except Exception:  # noqa: BLE001
        pass


def payment_in_flight(kind: str, obj) -> bool:
    """SEC-D3 (ревью волны 1): SEPA-оплата сделки ещё в пути — повторная онлайн-оплата
    закрыта, иначе клиент платил бы картой второй раз и обе оплаты проходили."""
    from django.core.cache import cache

    try:
        return bool(cache.get(_inflight_key(connection.schema_name, kind, str(obj.pk))))
    except Exception:  # noqa: BLE001 — кэш недоступен: не блокируем оплату
        return False


def payable(kind: str, obj, tenant=None) -> bool:
    """Сделку можно оплатить онлайн: она не отменена и оплата не в пути (ревью волны 1:
    страница «Jetzt bezahlen» по отменённой брони создавала сессию Stripe, а
    автовозврат стоил бизнесу комиссию)."""
    if getattr(obj, "status", "") in status_registry.cancelled_statuses_for(kind, tenant):
        return False
    return not payment_in_flight(kind, obj)


def settle_late_payment(kind: str, obj, *, newly_paid: bool) -> None:
    """Оплата пришла, а сделка уже снята (удержание истекло, отменили вручную):
    деньги не должны остаться у бизнеса за отменённую бронь — возвращаем сразу.
    Ошибка Stripe → `refund_payment` откатывает состояние и пишет владельцу.

    `newly_paid` — именно этот вебхук перевёл оплату в «оплачено». Повтор вебхука по
    уже оплаченной сделке (Stripe повторяет доставку) НЕ возвращает: владелец мог
    отменить с «nicht erstatten» (KA-D3) — деньги остаются по его решению."""
    from apps.core import refunds

    if not newly_paid:
        return
    from django_tenants.utils import get_tenant_model

    # Ревью волны 1: тенант — ДО проверки статуса, иначе свои статусы отмены (SM-3) под
    # schema_context не видны и поздняя оплата отменённой сделки оставалась у бизнеса.
    tenant = get_tenant_model().objects.filter(schema_name=connection.schema_name).first()
    # Статус — из БД: снятие удержания могло пройти между загрузкой и сохранением.
    obj.refresh_from_db(fields=["status"])
    if getattr(obj, "status", "") not in status_registry.cancelled_statuses_for(kind, tenant):
        return
    result = refunds.refund_payment(kind, obj, tenant)
    logger.warning("late payment on cancelled %s %s → %s", kind, obj.pk, result)
