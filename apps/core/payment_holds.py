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


def is_new_payment(kind: str, obj, intent: str) -> bool:
    """FB-33 D4a: пришли новые деньги — платёж, которого нет в книге сделки (повтор вебхука
    находит свою строку). Легаси без книги (ревью H1): повтор по главному intent уже
    оплаченной сделки новым платежом не считаем — иначе вернули бы законный платёж."""
    from apps.core import folio

    if not intent:
        return False
    model = type(obj)
    unpaid = (getattr(model, "PAYMENT_UNPAID", None),) + tuple(_UNPAID.get(kind, ()))
    if (
        getattr(obj, "stripe_payment_intent", "") == intent
        and getattr(obj, "payment_state", "") not in unpaid
    ):
        return False
    return not folio.has_payment(kind, obj, intent)


def is_extra_payment(kind: str, obj, intent: str, *, newly_paid: bool) -> bool:
    """FB-33 D4b: второй платёж Stripe к сделке, у которой главный платёж уже записан
    (оплачена, возвращена, отменена с «nicht erstatten»): этот вебхук оплату не ставит,
    главный intent есть и другой, платежа нет в книге. Решать по строке под блокировкой."""
    main = getattr(obj, "stripe_payment_intent", "") or ""
    return (
        bool(intent)
        and not newly_paid
        and bool(main)
        and intent != main
        and is_new_payment(kind, obj, intent)
    )


def record_extra_payment(kind: str, obj, *, intent: str, amount_cents: int | None = None):
    """FB-33 D4b: строка книги второго платежа — на сумму, которую списал Stripe
    (`amount_total`); без неё — как онлайн-платёж сделки. Пишется и у возвращённой сделки
    (иначе деньги выпали бы из книги). Звать под блокировкой сделки."""
    from apps.core import folio

    if amount_cents:
        return folio.record(
            kind,
            obj,
            amount_cents=int(amount_cents),
            purpose="full",
            method="stripe",
            source="webhook",
            intent=intent,
        )
    return folio.record_online(kind, obj, intent=intent)


def settle_extra_safely(kind: str, obj, *, intent: str) -> None:
    """Вебхук: вернуть второй платёж после блокировки; сбой не роняет вебхук (строка в
    книге, владельцу — письмо `duplicate` внутри `settle_extra_payment`)."""
    try:
        settle_extra_payment(kind, obj, intent=intent)
    except Exception:  # noqa: BLE001 — оплата записана; Stripe не должен получить 500
        logger.exception("%s %s: refund of a second payment crashed", kind, obj.pk)


def locked_deal(model, pk):
    """Строка сделки под `FOR UPDATE OF` самой сделки (ревью H3: связанные ресурс, юнит,
    событие не запираются — порядок замков `lock_scope` и «сделка → документ» цел).
    Битый id — None."""
    from django.core.exceptions import ValidationError

    try:
        return model.objects.select_for_update(of=("self",)).filter(pk=pk).first()
    except (ValidationError, ValueError):
        return None


#: Виды, у которых сбой возврата второго платежа повторяет задача по расписанию
#: (`retry_extra_refunds` из beat `orders.tasks.retry_late_refunds`); у прочих «Stripe не
#: ответил» — сразу письмо.
EXTRA_RETRY_KINDS = ("order",)

#: FB-33 D4a: `DealPayment.source` строки второго платежа, записанной новым путём. Повтор
#: возврата трогает только их: прежние двойные оплаты задним числом не возвращаем.
EXTRA_SOURCE = "extra"
#: Повтор возврата второго платежа: попыток, срок после платежа, строк за проход, просмотр.
EXTRA_RETRY_MAX = 4
EXTRA_RETRY_DAYS = 3
EXTRA_RETRY_BATCH = 50
EXTRA_SCAN_MAX = 500
_EXTRA_RETRY_STEP = timedelta(minutes=15)
#: Исход `_extra_retry_state`.
RETRY_DUE, RETRY_WAIT, RETRY_EXHAUSTED, RETRY_BLIND = "due", "wait", "exhausted", "blind"


def _extra_retry_key(schema: str, kind: str, pk, intent: str) -> str:
    return f"extra-refund-retry:{schema}:{kind}:{pk}:{intent}"


def _extra_retry_state(schema: str, kind: str, pk, intent: str, now) -> str:
    """Счётчик повтора на (сделка, платёж): не больше `EXTRA_RETRY_MAX` раз, пауза 15 мин ·
    2ⁿ. Кэш недоступен — `RETRY_BLIND`: повторять вслепую нельзя (письма без предела), а
    «ждать» вечно — тихая потеря; поэтому письмо владельцу."""
    from django.core.cache import cache

    key = _extra_retry_key(schema, kind, pk, intent)
    try:
        state = cache.get(key) or {"n": 0, "next": 0}
        if state["n"] >= EXTRA_RETRY_MAX:
            return RETRY_EXHAUSTED
        if now.timestamp() < state["next"]:
            return RETRY_WAIT
        pause = _EXTRA_RETRY_STEP * (2 ** state["n"])
        cache.set(
            key,
            {"n": state["n"] + 1, "next": (now + pause).timestamp()},
            (EXTRA_RETRY_DAYS + 1) * 86400,
        )
    except Exception:  # noqa: BLE001
        logger.warning("extra-refund-retry %s: счётчик недоступен — %s %s", schema, kind, pk)
        return RETRY_BLIND
    return RETRY_DUE


def _first_exhausted_mail(schema: str, kind: str, pk, intent: str) -> bool:
    """Флаг «исчерпано, письмо ушло» — письмо один раз (кэш недоступен — шлём: дубль гасит
    ключ письма)."""
    from django.core.cache import cache

    try:
        return bool(
            cache.add(
                _extra_retry_key(schema, kind, pk, intent) + ":mailed",
                1,
                (EXTRA_RETRY_DAYS + 1) * 86400,
            )
        )
    except Exception:  # noqa: BLE001
        return True


def retry_extra_refunds(now=None, *, kinds=EXTRA_RETRY_KINDS) -> int:
    """FB-33 D4a: повтор возврата ВТОРОГО платежа текущей схемы (Stripe не ответил или
    отказал). Только строки нового пути (`EXTRA_SOURCE`), свежие (`EXTRA_RETRY_DAYS`), без
    частичного возврата, не главный платёж сделки; свежие первыми — исчерпанные не держат
    окно; `EXTRA_RETRY_BATCH` попыток за проход. Исчерпано или счётчик недоступен — письмо
    `duplicate` (одно на платёж). → сколько вернули."""
    from django.db.models import Exists, OuterRef
    from django_tenants.utils import get_tenant_model

    from apps.core import folio, refunds

    now = now or timezone.now()
    schema = connection.schema_name
    tenant = None
    done = tried = 0
    for kind in kinds:
        model = transactions.model_for(kind)
        second = (
            model.objects.filter(pk=OuterRef("deal_id"))
            .exclude(stripe_payment_intent="")
            .exclude(stripe_payment_intent=OuterRef("stripe_payment_intent"))
        )
        rows = (
            folio.open_card_rows(kind)
            .filter(
                Exists(second),
                source=EXTRA_SOURCE,
                refunded_cents=0,
                created_at__gte=now - timedelta(days=EXTRA_RETRY_DAYS),
            )
            .order_by("-created_at")
            .values_list("deal_id", "stripe_payment_intent")[:EXTRA_SCAN_MAX]
        )
        for deal_id, intent in rows:
            if tried >= EXTRA_RETRY_BATCH:
                return done
            state = _extra_retry_state(schema, kind, deal_id, intent, now)
            if state == RETRY_WAIT:
                continue
            if state == RETRY_EXHAUSTED and not _first_exhausted_mail(
                schema, kind, deal_id, intent
            ):
                continue
            obj = model.objects.filter(pk=deal_id).first()
            if obj is None:
                continue
            if tenant is None:  # лениво: обычно повторять нечего
                tenant = get_tenant_model().objects.filter(schema_name=schema).first()
            if state != RETRY_DUE:
                refunds.notify_duplicate_failed(kind, obj, tenant, intent=intent)
                continue
            tried += 1
            try:
                result = refunds.refund_intent(kind, obj, intent, tenant)
            except Exception:  # noqa: BLE001 — один платёж не роняет проход
                logger.exception("extra-refund-retry %s: %s %s — сбой", schema, kind, deal_id)
                continue
            logger.warning("extra-refund-retry %s: %s %s → %s", schema, kind, deal_id, result)
            if result in (refunds.RefundResult.REFUNDED, refunds.RefundResult.ALREADY):
                done += 1
    return done


def settle_extra_payment(kind: str, obj, *, intent: str):
    """FB-33 D4a: второй платёж Stripe к НЕотменённой сделке (решение владельца
    2026-11-24) — уже записан строкой книги, возвращается только он (`refund_intent`).
    Звать после блокировки сделки. Сбой → письмо владельцу `duplicate` (одно на платёж);
    «Stripe не ответил» у вида с повтором — без письма (письмо после исчерпания повторов),
    у прочих — письмо сразу (повтора нет, ревью H4)."""
    from django_tenants.utils import get_tenant_model

    from apps.core import refunds

    tenant = get_tenant_model().objects.filter(schema_name=connection.schema_name).first()
    result = refunds.refund_intent(kind, obj, intent, tenant)
    logger.warning("second payment on %s %s → %s", kind, obj.pk, result)
    if result == refunds.RefundResult.FAILED or (
        result == refunds.RefundResult.UNCERTAIN and kind not in EXTRA_RETRY_KINDS
    ):
        refunds.notify_duplicate_failed(kind, obj, tenant, intent=intent)
    return result


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
