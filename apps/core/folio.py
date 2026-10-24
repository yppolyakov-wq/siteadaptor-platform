"""KA-12 B2-3: фолио платежей сделки (`core.DealPayment`).

Пишущая сторона; читает `money_contract` (`_paid`/`money_state`/`due`). Правила:

* фолио — денежная книга, а не выручка: журнал здесь не трогаем;
* сделка без строк — легаси, деньги читаются по-старому (`payment_state` + снимки);
* первая запись в легаси-сделку под блокировкой строки сделки сначала переносит уже
  полученную сумму строкой `opening` — иначе второй платёж «затёр» бы первый;
* платёж Stripe идемпотентен по intent (unique-constraint + проверка под блокировкой).

Списки зовут `prefetch` один раз, чтобы `due()` по строкам не делал запрос на каждую.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

_CACHE = "_folio_rows"


def _query(kind: str, ids):
    from apps.core.models import DealPayment

    return DealPayment.objects.filter(deal_kind=kind, deal_id__in=list(ids))


def rows(kind: str, obj) -> list:
    """Строки фолио сделки (из кэша `prefetch`, иначе запрос)."""
    cached = getattr(obj, _CACHE, None)
    if cached is not None:
        return cached
    found = list(_query(kind, [obj.pk]))
    setattr(obj, _CACHE, found)
    return found


def prefetch(kind: str, objs) -> None:
    """Один запрос на список сделок: кэш строк на каждом объекте."""
    objs = [o for o in objs if o is not None]
    if not objs:
        return
    by_deal: dict = {o.pk: [] for o in objs}
    for row in _query(kind, by_deal):
        by_deal.setdefault(row.deal_id, []).append(row)
    for o in objs:
        setattr(o, _CACHE, by_deal.get(o.pk, []))


def forget(obj) -> None:
    if hasattr(obj, _CACHE):
        delattr(obj, _CACHE)


def totals(kind: str, obj) -> tuple[int, int] | None:
    """(оплачено, возвращено) в центах или None, если строк нет (легаси)."""
    found = rows(kind, obj)
    if not found:
        return None
    return sum(r.amount_cents for r in found), sum(r.refunded_cents for r in found)


#: Виды сделок с фолио. Заявка — нет: её деньги идут через счёт и `prepaid_cents`
#: (сертификат + Anzahlung), второй источник там только запутал бы «уже получено».
#: Резерв (легаси) и gift/pass — тоже нет.
FOLIO_KINDS = ("order", "booking", "stay", "ticket")

#: KA-12 B2-8d: виды с ДАТИРОВАННЫМИ строками для среза УСт. У заявки строки только
#: дают даты поступления денег; её деньги по-прежнему читаются через `prepaid_cents`
#: (все денежные читатели гейтятся `FOLIO_KINDS`, не этим списком).
DATED_KINDS = FOLIO_KINDS + ("job",)


def _create_opening(kind: str, locked, *, new_intent: str) -> None:
    """Перенести в фолио то, что легаси-сделка уже получила по прежним правилам.

    Возвращённая целиком сделка — строка с оплатой И возвратом (иначе старый платёж
    и его возврат пропали бы из книги). intent прежнего платежа сохраняем, только
    если это не intent записываемого сейчас платежа (иначе строки столкнулись бы)."""
    from apps.core import money_contract
    from apps.core.models import DealPayment

    refunded_state = getattr(type(locked), "PAYMENT_REFUNDED", "refunded")
    if getattr(locked, "payment_state", "") == refunded_state:
        total = money_contract._total(kind, locked)
        online = min(money_contract._online_paid(kind, locked, total), total)
        amount = int((online * 100).to_integral_value())
        refunded = amount
    else:
        amount = money_contract.legacy_paid_cents(kind, locked)
        refunded = 0
    if amount <= 0:
        return
    old_intent = getattr(locked, "stripe_payment_intent", "") or ""
    DealPayment.objects.create(
        deal_kind=kind,
        deal_id=locked.pk,
        purpose=DealPayment.PURPOSE_OPENING,
        method=getattr(locked, "payment_method", "") or "",
        amount_cents=amount,
        refunded_cents=refunded,
        stripe_payment_intent=old_intent if old_intent != new_intent else "",
        source="legacy",
    )


def ensure_opening(kind: str, obj) -> None:
    """Легаси-сделке без строк — строка «Eröffnung» (под блокировкой сделки).
    Нужна перед частичным возвратом: возвращать можно только то, что есть в книге."""
    from apps.core import transactions
    from apps.core.models import DealPayment

    with transaction.atomic():
        locked = transactions.model_for(kind).objects.select_for_update().get(pk=obj.pk)
        if not DealPayment.objects.filter(deal_kind=kind, deal_id=locked.pk).exists():
            _create_opening(kind, locked, new_intent="")
    forget(obj)


def card_refunded_cents(kind: str, obj) -> int:
    """Сколько уже вернула карта (строки Stripe в фолио); 0 у легаси-сделки."""
    return sum(
        r.refunded_cents for r in rows(kind, obj) if r.method == "stripe" or r.stripe_payment_intent
    )


def mark_refunded(kind: str, obj, *, intent: str) -> None:
    """Полный возврат картой: строки этого платежа Stripe — возвращены целиком.
    Наличные/перевод (другие строки) карта не возвращает — их видно как «остаток»."""
    from django.db.models import F, Q

    from apps.core.models import DealPayment

    deal_rows = DealPayment.objects.filter(deal_kind=kind, deal_id=obj.pk)
    target = deal_rows.filter(stripe_payment_intent=intent) if intent else deal_rows.none()
    if not target.exists():
        # Легаси-строка opening без intent, но оплаченная картой.
        target = deal_rows.filter(Q(method="stripe") & Q(stripe_payment_intent=""))
    # B2-8a: дата возврата — только строкам, где он действительно случился сейчас.
    target.exclude(refunded_cents=F("amount_cents")).update(
        refunded_cents=F("amount_cents"), refunded_at=timezone.now()
    )
    forget(obj)


def record_online(kind: str, obj, *, intent: str = ""):
    """Вебхук Stripe: записать онлайн-платёж (депозит или всё — как `_online_paid`)."""
    if kind not in FOLIO_KINDS:
        return None
    from apps.core import money_contract

    total = money_contract._total(kind, obj)
    online = min(money_contract._online_paid(kind, obj, total), total)
    purpose = "full" if online >= total else "deposit"
    return record(
        kind,
        obj,
        amount_cents=int((online * 100).to_integral_value()),
        purpose=purpose,
        method="stripe",
        source="webhook",
        intent=intent,
    )


def record(
    kind: str,
    obj,
    *,
    amount_cents: int,
    purpose: str,
    method: str = "",
    source: str = "",
    intent: str = "",
):
    """Записать полученный платёж. Звать ДО смены `payment_state`: строка `opening`
    легаси-сделки считается по состоянию, которое было до этого платежа.

    Возвращает строку (повтор с тем же intent — прежнюю строку)."""
    from apps.core import transactions
    from apps.core.models import DealPayment

    amount_cents = int(amount_cents or 0)
    if amount_cents <= 0:
        return None
    model = transactions.model_for(kind)

    def _existing(deal_pk):
        return DealPayment.objects.filter(
            deal_kind=kind, deal_id=deal_pk, stripe_payment_intent=intent
        ).first()

    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=obj.pk)
        if intent:
            existing = _existing(locked.pk)
            if existing is not None:
                forget(obj)
                return existing
        has_rows = DealPayment.objects.filter(deal_kind=kind, deal_id=locked.pk).exists()
        if not has_rows:
            _create_opening(kind, locked, new_intent=intent)
        if not intent:
            # Платёж без intent (касса/банк/исполнение) — не больше реального остатка
            # по свежей книге под блокировкой: двойной клик «bezahlt» не задваивает.
            from django.db.models import Sum

            from apps.core import money_contract

            total = int((money_contract._total(kind, locked) * 100).to_integral_value())
            booked = (
                DealPayment.objects.filter(deal_kind=kind, deal_id=locked.pk).aggregate(
                    net=Sum("amount_cents") - Sum("refunded_cents")
                )["net"]
                or 0
            )
            amount_cents = min(amount_cents, total - booked)
            if amount_cents <= 0:
                forget(obj)
                return None
        try:
            with transaction.atomic():
                row = DealPayment.objects.create(
                    deal_kind=kind,
                    deal_id=locked.pk,
                    purpose=purpose,
                    method=method,
                    amount_cents=amount_cents,
                    stripe_payment_intent=intent,
                    source=source,
                )
        except IntegrityError:
            # Гонка повтора с тем же intent (вебхук ∥ ручной вызов) — строка уже есть.
            row = _existing(locked.pk)
    forget(obj)
    return row


def record_job_payment(
    job,
    *,
    amount_cents: int,
    purpose: str,
    method: str = "",
    source: str = "",
    intent: str = "",
    only_if_dated: bool = False,
):
    """KA-12 B2-8d: дата поступления денег по заявке — для Mindest-Ist/Ist среза УСт.

    Деньги заявки эта строка НЕ меняет (заявка не в `FOLIO_KINDS`). Без строки
    `opening`: легаси-заявка с уже полученными деньгами не получает сегодняшнюю дату
    задним числом. Сумма — не больше остатка «zu zahlen» по строкам; повтор intent —
    прежняя строка. `only_if_dated` — только если у заявки уже есть датированные
    строки (остаток по счёту легаси-заявки датой не известен)."""
    from django.db.models import Sum

    from apps.core.models import DealPayment

    amount_cents = int(amount_cents or 0)
    if amount_cents <= 0:
        return None
    model = type(job)

    def _existing(deal_pk):
        return DealPayment.objects.filter(
            deal_kind="job", deal_id=deal_pk, stripe_payment_intent=intent
        ).first()

    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=job.pk)
        if intent:
            existing = _existing(locked.pk)
            if existing is not None:
                return existing
        deal_rows = DealPayment.objects.filter(deal_kind="job", deal_id=locked.pk)
        if only_if_dated and not deal_rows.exists():
            return None
        payable = int((Decimal(locked.payable_gross) * 100).to_integral_value())
        booked = deal_rows.aggregate(net=Sum("amount_cents") - Sum("refunded_cents"))["net"] or 0
        amount_cents = min(amount_cents, payable - booked)
        if amount_cents <= 0:
            return None
        try:
            with transaction.atomic():
                return DealPayment.objects.create(
                    deal_kind="job",
                    deal_id=locked.pk,
                    purpose=purpose,
                    method=method,
                    amount_cents=amount_cents,
                    stripe_payment_intent=intent,
                    source=source,
                )
        except IntegrityError:
            return _existing(locked.pk)
