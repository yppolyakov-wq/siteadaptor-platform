"""Celery-beat задачи акций и броней.

Запускаются по расписанию ВНЕ tenant-контекста → проходим по всем схемам
арендаторов и работаем внутри schema_context. Чистая логика вынесена в
helper'ы (expire_due_reservations / roll_due_promotions), работающие в текущей
схеме — их и тестируем напрямую.

Задачи идемпотентны по своей природе (фильтр по времени), idempotent_task
здесь даёт единое имя и совместимость с dedupe-механизмом.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.core.jobs import idempotent_task

from .models import Customer, Promotion, Reservation
from .services import expire
from .state_machine import PromotionSM

# значение, которым затираем обезличенные контакты
_ANONYMIZED_NAME = "—"


def _iter_tenant_schemas():
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        yield tenant.schema_name


def expire_due_reservations(now=None) -> int:
    """Просрочить pending/confirmed брони с истёкшим expires_at (в текущей схеме).

    Возврат остатка делает expire() через ReservationSM. Возвращает число
    просроченных броней.
    """
    now = now or timezone.now()
    stale = Reservation.objects.filter(
        status__in=["pending", "confirmed"],
        expires_at__isnull=False,
        expires_at__lt=now,
    )
    count = 0
    for res in stale:
        expire(res)
        count += 1
    return count


def roll_due_promotions(now=None) -> dict:
    """scheduled→active по starts_at, active→ended по ends_at (в текущей схеме)."""
    now = now or timezone.now()
    sm = PromotionSM()
    activated = ended = 0

    for promo in Promotion.objects.filter(
        status="scheduled", starts_at__isnull=False, starts_at__lte=now
    ):
        # если окно уже целиком в прошлом — не активируем (нет перехода
        # scheduled→ended; такую акцию владелец завершит/архивирует вручную)
        if promo.ends_at and promo.ends_at <= now:
            continue
        sm.apply(promo, "active")
        activated += 1

    for promo in Promotion.objects.filter(status="active", ends_at__isnull=False, ends_at__lte=now):
        sm.apply(promo, "ended")
        ended += 1

    return {"activated": activated, "ended": ended}


@idempotent_task()
def expire_reservations():
    """Beat: просрочка броней по всем схемам арендаторов."""
    now = timezone.now()
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += expire_due_reservations(now)
    return {"expired": total}


@idempotent_task()
def roll_promotion_statuses():
    """Beat: активация/завершение акций по расписанию во всех схемах."""
    now = timezone.now()
    activated = ended = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            res = roll_due_promotions(now)
            activated += res["activated"]
            ended += res["ended"]
    return {"activated": activated, "ended": ended}


# Поля, переносимые в наследника при авто-повторе (всё, кроме идентичности,
# окна, статуса и аналитики — те задаются заново).
_RECUR_CLONE_FIELDS = (
    "title",
    "description",
    "product_id",
    "promo_type",
    "discount_percent",
    "price_override",
    "compare_at_price",
    "images",
    "available_quantity",
    "max_per_customer",
    "reservation_ttl_hours",
    "auto_confirm",
    "show_countdown",
    "strikethrough_old_price",
    "is_surprise",
    "metadata",
)


def _next_window(starts, ends, recurrence, now):
    """Окно следующего повтора: сдвиг на интервал, пропуская прошедшие циклы."""
    delta = timedelta(days=1) if recurrence == Promotion.DAILY else timedelta(weeks=1)
    new_starts, new_ends = starts + delta, ends + delta
    # если beat молчал несколько циклов — перескакиваем к ближайшему будущему
    # окну (ровно один наследник, без «навёрстывания» пачкой)
    while new_ends <= now:
        new_starts += delta
        new_ends += delta
    return new_starts, new_ends


def _spawn_recurrence(promo, now):
    """Создать запланированного наследника завершившейся повторяющейся акции.

    recurrence уходит к наследнику, у родителя гасится → цепочка одиночная.
    """
    new_starts, new_ends = _next_window(promo.starts_at, promo.ends_at, promo.recurrence, now)
    heir = Promotion(
        status="draft",
        starts_at=new_starts,
        ends_at=new_ends,
        recurrence=promo.recurrence,
        **{f: getattr(promo, f) for f in _RECUR_CLONE_FIELDS},
    )
    heir.save()
    PromotionSM().apply(heir, "scheduled")

    promo.recurrence = Promotion.NO_RECUR
    promo.save(update_fields=["recurrence", "updated_at"])
    return heir


def roll_due_recurring(now=None) -> int:
    """Размножить завершившиеся повторяющиеся акции (в текущей схеме).

    Кандидат — status=ended с заданным recurrence и полным окном. Наследник
    встаёт scheduled на следующее окно; у родителя recurrence гасится, поэтому
    одна акция даёт ровно одного наследника. Возвращает число наследников.
    """
    now = now or timezone.now()
    due = Promotion.objects.filter(
        status="ended",
        recurrence__in=[Promotion.DAILY, Promotion.WEEKLY],
        starts_at__isnull=False,
        ends_at__isnull=False,
    )
    spawned = 0
    for promo in due:
        _spawn_recurrence(promo, now)
        spawned += 1
    return spawned


@idempotent_task()
def roll_recurring_promotions():
    """Beat: авто-повтор завершившихся акций по всем схемам арендаторов."""
    now = timezone.now()
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += roll_due_recurring(now)
    return {"spawned": total}


def purge_due_customers(now=None) -> int:
    """DSGVO: обезличить контакты клиентов без активных броней (в текущей схеме).

    Кандидат — клиент, у которого нет pending/confirmed резерваций И активных
    отельных броней, и чья последняя активность (резервации ИЛИ stays — PMS-аудит
    2026-07-27: раньше отельные гости под purge не попадали вовсе) старше
    RESERVATION_PII_RETENTION_DAYS. Сама строка Customer остаётся (для
    агрегатной статистики), но PII затирается.
    """
    from django.db.models.functions import Greatest

    from apps.core import status_registry
    from apps.stays.models import StayBooking

    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.RESERVATION_PII_RETENTION_DAYS)

    # SM-3: активность через реестр (как stays строкой ниже) — резерв в кастом-
    # active статусе владельца тоже живая сделка, его клиента не обезличиваем.
    active_customer_ids = Reservation.objects.filter(
        status__in=status_registry.active_statuses_for("reservation")
    ).values_list("customer_id", flat=True)
    active_stay_ids = StayBooking.objects.filter(
        status__in=status_registry.active_statuses_for("stay")
    ).values_list("customer_id", flat=True)

    stale = (
        Customer.objects.exclude(id__in=active_customer_ids)
        .exclude(id__in=active_stay_ids)
        # PostgreSQL GREATEST игнорирует NULL → работает и для «только stays».
        .annotate(last_activity=Greatest(Max("reservations__updated_at"), Max("stays__updated_at")))
        .filter(last_activity__isnull=False, last_activity__lt=cutoff)
        # уже обезличенные не трогаем повторно
        .exclude(name=_ANONYMIZED_NAME, email="", phone="", note="")
    )

    count = 0
    for customer in stale:
        customer.name = _ANONYMIZED_NAME
        customer.email = ""
        customer.phone = ""
        customer.note = ""
        customer.birthday = None  # PMS-B2: дата рождения — PII, чистим вместе
        customer.save(update_fields=["name", "email", "phone", "note", "birthday", "updated_at"])
        count += 1
    return count


@idempotent_task()
def purge_reservation_pii():
    """Beat: DSGVO-обезличивание старых контактов во всех схемах арендаторов."""
    total = 0
    now = timezone.now()
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += purge_due_customers(now)
    return {"purged": total}


def send_due_winback_coupons(now=None, base_url=None) -> int:
    """B4.4: авто-win-back в текущей схеме. По активным auto_winback-кампаниям
    выдать новый персональный код клиентам сегмента «не покупал N дней», НЕ
    получавшим код этой кампании в окне N дней (иначе слало бы каждый день).
    Только opt-in: сегмент строится поверх consented_customers()."""
    from .models import CouponCampaign
    from .newsletter import segment_customers, send_coupon_campaign

    now = now or timezone.now()
    total = 0
    for campaign in CouponCampaign.objects.filter(
        kind=CouponCampaign.KIND_AUTO_WINBACK, status=CouponCampaign.STATUS_ACTIVE
    ):
        days = campaign.inactive_days or 60
        recent_ids = campaign.vouchers.filter(
            created_at__gte=now - timedelta(days=days), customer__isnull=False
        ).values_list("customer_id", flat=True)
        # PMS-аудит 2026-07-27: exclude ДО top_ltv-слайса (иначе TypeError).
        customers = list(
            segment_customers(
                tag=campaign.tag,
                inactive_days=days,
                top_ltv=campaign.top_ltv,
                exclude_ids=list(recent_ids),
            )
        )
        if not customers:
            continue
        if base_url is None:
            from django.db import connection

            from .notifications import _base_url

            base_url = _base_url(connection.schema_name)
        total += send_coupon_campaign(campaign, base_url=base_url, customers=customers)
    return total


@idempotent_task()
def send_winback_coupons():
    """Beat (раз в сутки): авто-win-back купоны по всем схемам арендаторов."""
    total = 0
    now = timezone.now()
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_winback_coupons(now)
    return {"sent": total}


def send_due_birthday_coupons(today=None, base_url=None) -> int:
    """PMS-B2: «Geburtstagsgruß» в текущей схеме — персональный код именинникам.

    По активным birthday-кампаниям: получатели = consented_customers()
    [+tag кампании] с днём рождения СЕГОДНЯ (29.02 в невисокосный год
    празднуем 28.02). Годовой дедуп окном 300 дней (< 365 повторов не даёт,
    устойчив к сдвигам прогона). UWG §7 — по построению сегмента."""
    import calendar

    from .models import CouponCampaign
    from .newsletter import segment_customers, send_coupon_campaign

    today = today or timezone.localdate()
    day_pairs = [(today.month, today.day)]
    if today.month == 2 and today.day == 28 and not calendar.isleap(today.year):
        day_pairs.append((2, 29))
    total = 0
    for campaign in CouponCampaign.objects.filter(
        kind=CouponCampaign.KIND_BIRTHDAY, status=CouponCampaign.STATUS_ACTIVE
    ):
        recent_ids = campaign.vouchers.filter(
            created_at__gte=timezone.now() - timedelta(days=300), customer__isnull=False
        ).values_list("customer_id", flat=True)
        base = segment_customers(tag=campaign.tag, exclude_ids=list(recent_ids))
        from django.db.models import Q

        cond = Q()
        for month, day in day_pairs:
            cond |= Q(birthday__month=month, birthday__day=day)
        customers = list(base.filter(cond))
        if not customers:
            continue
        if base_url is None:
            from django.db import connection

            from .notifications import _base_url

            base_url = _base_url(connection.schema_name)
        total += send_coupon_campaign(campaign, base_url=base_url, customers=customers)
    return total


@idempotent_task()
def send_birthday_coupons():
    """Beat (раз в сутки): поздравления именинников по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_birthday_coupons()
    return {"sent": total}


# PMS-B (остаток CRM-волны): авто-тег постоянного клиента. Порог — честные
# 3+ покупки; источник — RevenueEntry (generic-деньги всех движков, как LTV).
STAMMKUNDE_TAG = "stammkunde"
STAMMKUNDE_MIN_PURCHASES = 3


def tag_regular_customers() -> int:
    """Добавить «stammkunde» клиентам с ≥3 покупками (текущая схема).

    Только ДОБАВЛЯЕМ этот один тег: остальные теги владельца не трогаем и
    ничего не удаляем. Тег поддерживается автоматикой: снятый вручную
    вернётся следующим прогоном, пока клиент проходит порог (тег отражает
    факт «постоянный», а не мнение). Питает сегменты кампаний B4."""
    from django.db.models import Count

    from apps.finance.models import RevenueEntry

    ids = list(
        RevenueEntry.objects.filter(customer__isnull=False)
        .values("customer")
        .annotate(n=Count("id"))
        .filter(n__gte=STAMMKUNDE_MIN_PURCHASES)
        .values_list("customer", flat=True)
    )
    tagged = 0
    for customer in Customer.objects.filter(pk__in=ids):
        tags = list(customer.tags or [])
        if STAMMKUNDE_TAG in tags:
            continue
        tags.append(STAMMKUNDE_TAG)
        customer.tags = tags
        customer.save(update_fields=["tags", "updated_at"])
        tagged += 1
    return tagged


@idempotent_task()
def auto_tag_customers():
    """Beat (раз в сутки): авто-теги клиентов по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += tag_regular_customers()
    return {"tagged": total}
