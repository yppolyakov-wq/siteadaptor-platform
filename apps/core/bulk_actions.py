"""KA-12 E2.1: массовая смена статуса сделок из списка продаж.

Тот же путь, что у одиночной кнопки: `transactions.apply_action` (письма, склад,
возврат денег при отмене — штатно), каждый объект в своём atomic. Клиенту не
доверяем: пересечение допустимых переходов пересчитывается на сервере, цель вне
него отклоняет весь запрос. Частичный успех — честный отчёт с причинами.

Ограничения (решения плана `ka-12-w3-deal-plan-2026-10-24.md`):
- не больше MAX_IDS сделок за раз; при опасной цели (отмена) — не больше MAX_DANGER;
- опасная цель требует явного подтверждения (`confirm`);
- «Versendet» массово не проставляем — письмо ушло бы без трек-номера;
- оплаченная бронь номера (выбор erstatten / nicht) пропускается — только в карточке.
"""

import logging
import uuid
from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core import transactions

MAX_IDS = 50
# Отмена оплаченной сделки возвращает деньги через Stripe синхронно (как у одиночной
# кнопки) — держим запрос коротким (security-ревью E2.1).
MAX_DANGER = 10
# Цели, которые массово не ставим: им нужны данные конкретной сделки.
NOT_BULK = {"order": {"shipped"}}


class BulkRefused(Exception):
    """Запрос отклонён целиком (ничего не изменено). `str(exc)` — текст владельцу."""


@dataclass
class BulkResult:
    changed: int = 0
    already: int = 0
    skipped: dict = field(default_factory=dict)  # причина → число
    refunds: list = field(default_factory=list)  # RefundResult по изменённым
    check_codes: list = field(default_factory=list)  # возврат не прошёл / не ясен

    def skip(self, reason) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def clean_ids(raw_ids) -> list:
    """Список UUID без мусора и дублей, в порядке прихода."""
    out = []
    for raw in raw_ids:
        try:
            pk = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            continue
        if pk not in out:
            out.append(pk)
    return out


def common_actions(kind: str, objs, subset) -> list[dict]:
    """Пересечение допустимых переходов выбранных сделок (порядок — первой)."""
    common = None
    for obj in objs:
        actions = transactions.allowed_actions_for(kind, obj.status, subset, obj=obj)
        targets = {a["target"] for a in actions if a["target"] not in NOT_BULK.get(kind, ())}
        common = targets if common is None else common & targets
        if not common:
            return []
    first = transactions.allowed_actions_for(kind, objs[0].status, subset, obj=objs[0])
    return [a for a in first if a["target"] in (common or set())]


def apply_bulk(
    tenant, kind, ids, target, *, confirm=False, actor=None, on_refund=None
) -> BulkResult:
    """`on_refund(result)` зовётся СРАЗУ после возврата каждой сделки — пока в
    contextvar лежит её остаток наличными (refunds._OFFLINE_REST перезаписывается
    следующим возвратом; ревью E2.1)."""
    from apps.core import refunds, transition_rules
    from apps.core.fsm import IllegalTransition, PaymentRequired

    if kind not in transactions.TRANSACTION_KINDS or not tenant.is_module_active(
        transactions.KIND_MODULE[kind]
    ):
        raise BulkRefused(_("Dieser Bereich ist nicht aktiv."))
    pks = clean_ids(ids)
    if not pks:
        raise BulkRefused(_("Bitte zuerst Einträge auswählen."))
    if len(pks) > MAX_IDS:
        raise BulkRefused(_("Höchstens %(n)s Einträge auf einmal.") % {"n": MAX_IDS})
    model = transactions.model_for(kind)
    objs = list(model.objects.filter(pk__in=pks))
    if not objs:
        raise BulkRefused(_("Bitte zuerst Einträge auswählen."))
    subset = transition_rules.subset_for(tenant, kind)
    result = BulkResult()
    pending = [o for o in objs if o.status != target]
    result.already = len(objs) - len(pending)
    if not pending:
        return result
    allowed = {a["target"]: a for a in common_actions(kind, pending, subset)}
    if target not in allowed:
        raise BulkRefused(_("Dieser Schritt ist nicht für alle ausgewählten Einträge möglich."))
    if allowed[target]["danger"]:
        if not confirm:
            raise BulkRefused(_("Bitte den Schritt bestätigen."))
        if len(pending) > MAX_DANGER:
            raise BulkRefused(
                _("Stornieren geht höchstens für %(n)s Einträge auf einmal.") % {"n": MAX_DANGER}
            )
    for obj in pending:
        try:
            with transaction.atomic():
                locked = model.objects.select_for_update().get(pk=obj.pk)
                if locked.status == target:
                    result.already += 1
                    continue
                refund = transactions.apply_action(
                    kind, locked, target, actor=actor, extra={}, tenant=tenant
                )
        except refunds.RefundChoiceRequired:
            result.skip(_("bezahlt — Erstattung in der Buchung wählen"))
            continue
        except refunds.RefundNotAllowed:
            result.skip(_("bezahlt — Erstattung nur durch Inhaber oder Buchhaltung"))
            continue
        except PaymentRequired:
            result.skip(_("noch nicht bezahlt"))
            continue
        except IllegalTransition:
            result.skip(_("Schritt im aktuellen Status nicht möglich"))
            continue
        except model.DoesNotExist:
            result.skip(_("inzwischen gelöscht"))
            continue
        except Exception:  # noqa: BLE001 — одна сделка не обрывает отчёт по остальным
            logging.getLogger(__name__).exception("bulk status %s %s failed", kind, obj.pk)
            result.skip(_("Fehler — bitte einzeln öffnen"))
            continue
        result.changed += 1
        if refund != refunds.RefundResult.NONE:
            result.refunds.append(refund)
            if refund in (
                refunds.RefundResult.FAILED,
                refunds.RefundResult.UNCERTAIN,
                refunds.RefundResult.MANUAL,
            ):
                result.check_codes.append(obj.reference_code)
            if on_refund is not None:
                on_refund(refund)
    return result
