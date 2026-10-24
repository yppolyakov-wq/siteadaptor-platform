"""KA-12 E2.2: CSV продаж — заказы, брони номеров, записи, билеты, заявки.

Файл = то, что владелец видит в списке: те же фильтры (статус, поиск) и та же
сортировка. Свободный текст — через `csv_safe` (formula-инъекция), числа и даты
как есть. Выгрузка с персональными данными — только владельцу (KA-H11), запись
о выгрузке — в журнал без персональных данных (`roles.audit_export`).
"""

import csv

from django.utils.translation import gettext_lazy as _

from apps.core import transactions
from apps.core.csv_safe import csv_safe

#: Потолок строк одного файла; больше — пометка об усечении в последней строке.
MAX_ROWS = 10_000

EXPORT_KINDS = ("order", "stay", "booking", "ticket", "job")

HEADER = (
    _("Code"),
    _("Externe Nummer"),
    _("Angelegt"),
    _("Termin"),
    _("Kunde"),
    _("E-Mail"),
    _("Telefon"),
    _("Titel"),
    _("Status"),
    _("Betrag"),
    _("Währung"),
    _("Zahlungsart"),
    _("Zahlungsstatus"),
)


def _iso(value) -> str:
    if not value:
        return ""
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def write_rows(out, kind: str, qs, tenant) -> int:
    """Пишет заголовок и строки в `out` (file-like). Возвращает число строк."""
    from apps.core import status_labels, transition_rules

    labels = status_labels.custom_labels(tenant, kind)
    subset = transition_rules.subset_for(tenant, kind)
    writer = csv.writer(out)
    writer.writerow([str(h) for h in HEADER])
    rows = 0
    for obj in qs.iterator(chunk_size=500):
        if rows >= MAX_ROWS:
            writer.writerow([str(_("… gekürzt: mehr als %(n)s Zeilen") % {"n": MAX_ROWS})])
            break
        tx = transactions.transaction_for(kind, obj, labels, subset)
        customer = obj.customer
        amount = tx.amount_value
        writer.writerow(
            [
                obj.reference_code,
                csv_safe(getattr(obj, "external_code", "") or ""),
                _iso(obj.created_at),
                _iso(tx.when),
                csv_safe(getattr(customer, "name", "") or ""),
                csv_safe(getattr(customer, "email", "") or ""),
                csv_safe(getattr(customer, "phone", "") or ""),
                csv_safe(tx.title),
                csv_safe(tx.status_label),
                "" if amount is None else f"{amount:.2f}",
                tx.currency or "",
                csv_safe(getattr(obj, "payment_method", "") or ""),
                csv_safe(getattr(obj, "payment_state", "") or ""),
            ]
        )
        rows += 1
    return rows
