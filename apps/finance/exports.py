"""Экспорт журнала выручки (Track D / D4c): обычный CSV + DATEV-CSV.

DATEV — упрощённый Buchungsstapel (без EXTF-метастроки): точка с запятой,
десятичная запятая, Belegdatum TTMM, кодировка cp1252 — формат полей, который
понимают DATEV-Format-Assistent и бухгалтеры. Счета SKR03: Kasse 1000,
Erlöse 8400 (19 %) / 8300 (7 %) / 8195 (steuerfrei/§19). Полный бухучёт
сознательно не делаем (ТЗ D4) — это перенос данных бухгалтеру, не замена ему.
"""

import csv
import io
from decimal import Decimal

# SKR03 (самый распространённый у малого бизнеса DE).
KASSE = "1000"
ERLOES_BY_VAT = {
    Decimal("19.00"): "8400",
    Decimal("7.00"): "8300",
    Decimal("0.00"): "8195",
}


def _comma(value) -> str:
    return f"{Decimal(value):.2f}".replace(".", ",")


def plain_csv(entries) -> str:
    """Обычный CSV за период (Excel-friendly, utf-8-sig добавляет вьюха)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "source", "note", "customer", "vat_rate", "amount", "currency"])
    for entry in entries:
        writer.writerow(
            [
                entry.date.isoformat(),
                entry.source,
                entry.note,
                str(entry.customer) if entry.customer else "",
                entry.vat_rate,
                entry.amount,
                entry.currency,
            ]
        )
    return buffer.getvalue()


def datev_csv(entries) -> str:
    """Упрощённый DATEV-Buchungsstapel: Kasse (Soll) an Erlöskonto по ставке."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "Umsatz",
            "Soll/Haben-Kennzeichen",
            "WKZ Umsatz",
            "Konto",
            "Gegenkonto (ohne BU-Schlüssel)",
            "Belegdatum",
            "Belegfeld 1",
            "Buchungstext",
        ]
    )
    for entry in entries:
        erloes = ERLOES_BY_VAT.get(Decimal(entry.vat_rate), "8400")
        writer.writerow(
            [
                _comma(entry.amount),
                "S",
                entry.currency,
                KASSE,
                erloes,
                f"{entry.date:%d%m}",
                entry.note[:36],
                f"{entry.get_source_display()} {entry.note}".strip()[:60],
            ]
        )
    return buffer.getvalue()
