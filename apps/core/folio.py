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

from django.db import transaction

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
    from apps.core import money_contract, transactions
    from apps.core.models import DealPayment

    amount_cents = int(amount_cents or 0)
    if amount_cents <= 0:
        return None
    model = transactions.model_for(kind)
    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=obj.pk)
        if intent:
            existing = DealPayment.objects.filter(
                deal_kind=kind, stripe_payment_intent=intent
            ).first()
            if existing is not None:
                forget(obj)
                return existing
        has_rows = DealPayment.objects.filter(deal_kind=kind, deal_id=locked.pk).exists()
        if not has_rows:
            opening = money_contract.legacy_paid_cents(kind, locked)
            if opening > 0:
                DealPayment.objects.create(
                    deal_kind=kind,
                    deal_id=locked.pk,
                    purpose=DealPayment.PURPOSE_OPENING,
                    method=getattr(locked, "payment_method", "") or "",
                    amount_cents=opening,
                    stripe_payment_intent=getattr(locked, "stripe_payment_intent", "") or "",
                    source="legacy",
                )
        row = DealPayment.objects.create(
            deal_kind=kind,
            deal_id=locked.pk,
            purpose=purpose,
            method=method,
            amount_cents=amount_cents,
            stripe_payment_intent=intent,
            source=source,
        )
    forget(obj)
    return row
