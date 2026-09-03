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

from django.db import transaction
from django.utils import timezone

from apps.core import status_registry, transactions

logger = logging.getLogger(__name__)

# Виды сделок, у которых удержание имеет смысл: место/номер/билет физически
# заняты. Заказ ведёт свой TTL (Anprobe), заявка ничего не блокирует.
HOLD_KINDS = ("booking", "stay", "ticket")

# Состояния «денег ещё нет» per-kind (те же, что у ERP-2 «Offene Posten»).
_UNPAID = {
    "booking": ("none", "pending"),
    "stay": ("none", "pending"),
    "ticket": ("none", "pending", "deposit"),
}


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
