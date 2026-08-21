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

from apps.core.csv_safe import csv_safe

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
                csv_safe(entry.source),
                csv_safe(entry.note),
                csv_safe(str(entry.customer)) if entry.customer else "",
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
                csv_safe(entry.note[:36]),
                csv_safe(f"{entry.get_source_display()} {entry.note}".strip()[:60]),
            ]
        )
    return buffer.getvalue()


# ERP-4: счета затрат SKR03 (упрощённо, по категориям ExpenseEntry) — как
# ERLOES_BY_VAT: бухгалтер перемапит, но выгрузка сразу осмысленна.
AUFWAND_BY_CATEGORY = {
    "goods": "3400",  # Wareneingang
    "accommodation": "4660",  # Reisekosten/Unterkunft
    "transport": "4530",  # Fahrzeug-/Transportkosten
    "fees": "4380",  # Beiträge/Gebühren
    "staff": "4190",  # Personal (Aushilfen vor Ort)
    "other": "4900",  # Sonstige betriebliche Aufwendungen
}


def datev_expenses_csv(entries) -> str:
    """ERP-4: DATEV-Buchungsstapel расходов — Aufwandskonto (Soll) an Kasse.

    Зеркало `datev_csv` (выручка): тот же формат/кодировка, бухгалтер получает
    ОБЕ стороны, а не половину книги."""
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
        konto = AUFWAND_BY_CATEGORY.get(entry.category, "4900")
        writer.writerow(
            [
                _comma(entry.amount),
                "S",
                entry.currency,
                konto,
                KASSE,
                entry.date.strftime("%d%m"),
                str(entry.pk)[:12],
                csv_safe(entry.note or entry.get_category_display()),
            ]
        )
    return buffer.getvalue()
