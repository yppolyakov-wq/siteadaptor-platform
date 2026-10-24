"""KA-12 B2-8a: срез UStVA по режиму налогообложения бизнеса (решение T-1).

Срез — подсказка владельцу, НЕ декларация: подпись на экране так и говорит.

- **Soll** (§ 13 Abs. 1 Nr. 1a UStG, дефолт): налог возникает при исполнении — это
  журнал выручки (`RevenueEntry`, пишется при исполнении). Плюс Mindest-Istversteuerung
  (§ 13 Abs. 1 Nr. 1a S. 4): деньги, полученные ДО исполнения (Anzahlung), облагаются в
  месяце поступления и вычитаются в месяце исполнения, чтобы не обложить дважды.
- **Ist** (§ 20 UStG): налог возникает при поступлении денег — фолио платежей
  (`DealPayment`) по датам поступления минус возвраты по дате возврата. Что фолио не
  ведёт (заявки, сертификаты, абонементы, ручные записи, легаси-сделки без строк) —
  по дате журнала, с пометкой.
- **Kleinunternehmer** (§ 19 UStG): налог не взимается, Vorsteuer не вычитается.

Разбивка платежа по ставкам — пропорционально составу сделки (`core.vat.deal_vat`):
Anzahlung за номер с Kurtaxe делится так же, как вся бронь.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

ZERO = Decimal("0")
CENT = Decimal("0.01")

REGIME_SOLL = "soll"
REGIME_IST = "ist"
REGIME_KLEIN = "klein"
#: Одна радио-группа в «Recht & Steuern» (T-1). Kleinunternehmer хранится в
#: `Tenant.small_business` (на нём уже счета/PDF), режим — в `Tenant.tax_regime`.
REGIME_CHOICES = [
    (REGIME_SOLL, gettext_lazy("Sollversteuerung — USt bei Leistung (Standard)")),
    (REGIME_IST, gettext_lazy("Istversteuerung — USt bei Zahlungseingang")),
    (REGIME_KLEIN, gettext_lazy("Kleinunternehmer (§ 19 UStG) — Rechnungen ohne MwSt.")),
]

#: Источник журнала → вид сделки с фолио (`apps.core.folio.FOLIO_KINDS`).
_SOURCE_KIND = {"order": "order", "stay": "stay", "booking": "booking", "event": "ticket"}


def regime_of(tenant) -> str:
    if getattr(tenant, "small_business", False):
        return REGIME_KLEIN
    regime = getattr(tenant, "tax_regime", "") or REGIME_SOLL
    return regime if regime in (REGIME_SOLL, REGIME_IST) else REGIME_SOLL


def apply_regime(tenant, value: str) -> bool:
    """Записать выбор радио-группы в поля тенанта (без save). False — значение чужое."""
    if value == REGIME_KLEIN:
        tenant.small_business = True
        return True
    if value in (REGIME_SOLL, REGIME_IST):
        tenant.small_business = False
        tenant.tax_regime = value
        return True
    return False


def _vat(gross: Decimal, rate: Decimal) -> Decimal:
    return gross * rate / (Decimal("100") + rate) if rate else ZERO


def _deal_ref(source: str, source_ref: str):
    """(вид, uuid) сделки с фолио по записи журнала или None."""
    kind = _SOURCE_KIND.get(source)
    if kind is None or not source_ref:
        return None
    try:
        return kind, uuid.UUID(source_ref.split(":", 1)[0])
    except ValueError:
        return None


def _local_day(dt) -> date:
    return timezone.localdate(dt) if timezone.is_aware(dt) else dt.date()


class _Mixes:
    """Доли ставок сделок (пакетно по виду). Сделка не найдена — None (пометка)."""

    def __init__(self):
        self._cache: dict = {}

    def load(self, refs) -> None:
        from apps.core import transactions

        by_kind = defaultdict(set)
        for kind, pk in refs:
            if (kind, pk) not in self._cache:
                by_kind[kind].add(pk)
        for kind, ids in by_kind.items():
            found = {o.pk: o for o in transactions.model_for(kind).objects.filter(pk__in=ids)}
            for pk in ids:
                obj = found.get(pk)
                self._cache[(kind, pk)] = self._mix(kind, obj) if obj is not None else None

    @staticmethod
    def _mix(kind, obj):
        from apps.core.vat import deal_vat

        vat = deal_vat(kind, obj)
        gross = vat["gross"]
        if not gross:
            return None
        return [(row["rate"], row["gross"] / gross) for row in vat["rows"]]

    def get(self, ref):
        return self._cache.get(ref)


class _Acc:
    """Брутто по ставкам + пометки."""

    def __init__(self):
        self.by_rate: dict = defaultdict(lambda: ZERO)
        self.unmapped = False

    def add(self, gross: Decimal, rate: Decimal) -> None:
        self.by_rate[Decimal(rate)] += gross

    def add_mixed(self, gross: Decimal, mix) -> None:
        if not mix:
            # Состав сделки неизвестен (удалена/пустая) — честно 19 % и пометка.
            self.unmapped = True
            self.add(gross, Decimal("19.00"))
            return
        for rate, share in mix:
            self.add(gross * share, rate)


def _events(rows):
    """Денежные события строк фолио: (день, брутто €) — поступление и возврат."""
    for row in rows:
        yield _local_day(row.created_at), Decimal(row.amount_cents) / 100
        if row.refunded_cents:
            yield (
                _local_day(row.refunded_at or row.updated_at),
                -Decimal(row.refunded_cents) / 100,
            )


def _refs_q(refs):
    """По виду — `deal_id__in` (индекс dealpayment_deal_idx), без OR на каждую сделку."""
    by_kind = defaultdict(set)
    for kind, pk in refs:
        by_kind[kind].add(pk)
    q = Q(pk__in=[])
    for kind, ids in by_kind.items():
        q |= Q(deal_kind=kind, deal_id__in=ids)
    return q


def _folio_rows(refs) -> list:
    from apps.core.models import DealPayment

    if not refs:
        return []
    return list(DealPayment.objects.filter(_refs_q(refs)))


def _rows_with_events_in(von: date, bis: date) -> list:
    """Строки фолио, у которых в периоде поступление или возврат."""
    from datetime import datetime, time, timedelta

    from apps.core.folio import FOLIO_KINDS
    from apps.core.models import DealPayment

    tz = timezone.get_current_timezone()
    start = datetime.combine(von, time.min, tzinfo=tz)
    end = datetime.combine(bis + timedelta(days=1), time.min, tzinfo=tz)
    qs = DealPayment.objects.filter(deal_kind__in=FOLIO_KINDS).annotate(
        refunded_day=Coalesce("refunded_at", "updated_at")
    )
    return list(
        qs.filter(
            Q(created_at__gte=start, created_at__lt=end)
            | Q(refunded_cents__gt=0, refunded_day__gte=start, refunded_day__lt=end)
        )
    )


def _journal_of(refs) -> dict:
    """Все записи журнала сделок с фолио (за всё время), по сделке."""
    from .models import RevenueEntry

    out: dict = defaultdict(list)
    if not refs:
        return out
    from django.db.models.functions import Left

    # «{id}» и «{id}:meal/:return/…» — по первым 36 знакам (uuid), одним IN на источник.
    q = Q(pk__in=[])
    by_source = defaultdict(set)
    for kind, pk in refs:
        by_source[{"ticket": "event"}.get(kind, kind)].add(str(pk))
    for source, ids in by_source.items():
        q |= Q(source=source, ref_head__in=ids)
    qs = RevenueEntry.objects.annotate(ref_head=Left("source_ref", 36))
    for entry in qs.filter(q).only("source", "source_ref", "date", "amount"):
        ref = _deal_ref(entry.source, entry.source_ref)
        if ref is not None:
            out[ref].append(entry)
    return out


def _soll(von: date, bis: date, entries, acc: _Acc, notes: list) -> None:
    for e in entries:
        acc.add(e.amount, e.vat_rate)
    # Mindest-Ist: сделки с деньгами, двинувшимися в периоде, + сделки, исполненные в
    # периоде (у них вычитается налог, уплаченный с предоплаты раньше).
    moved = _rows_with_events_in(von, bis)
    refs = {(r.deal_kind, r.deal_id) for r in moved}
    recognized_here = {
        ref
        for e in entries
        if (ref := _deal_ref(e.source, e.source_ref)) is not None and e.amount > 0
    }
    refs |= recognized_here
    if not refs:
        return
    journal = _journal_of(refs)
    # Исполнение — первая ПОЛОЖИТЕЛЬНАЯ проводка (сторно раньше неё дату не сдвигает).
    rec = {}
    for ref, es in journal.items():
        days = [e.date for e in es if e.amount > 0]
        if days:
            rec[ref] = min(days)
    rows = _folio_rows(refs)
    mixes = _Mixes()
    mixes.load(refs)
    by_deal = defaultdict(list)
    for row in rows:
        by_deal[(row.deal_kind, row.deal_id)].append(row)
    advance = False
    for ref, deal_rows in by_deal.items():
        r_day = rec.get(ref)
        mix = mixes.get(ref)
        for day, gross in _events(deal_rows):
            if r_day is not None and day >= r_day:
                continue  # деньги в день исполнения или позже — это уже журнал
            if von <= day <= bis:
                acc.add_mixed(gross, mix)
                advance = True
        if r_day is not None and von <= r_day <= bis:
            before = sum((g for d, g in _events(deal_rows) if d < r_day), ZERO)
            if before:
                acc.add_mixed(-before, mix)
                advance = True
    if advance:
        notes.append(
            _(
                "Anzahlungen vor der Leistung sind im Monat des Zahlungseingangs enthalten "
                "und im Monat der Leistung wieder abgezogen (Mindest-Istversteuerung)."
            )
        )


def _ist(von: date, bis: date, entries, acc: _Acc, notes: list) -> None:
    moved = _rows_with_events_in(von, bis)
    refs = {(r.deal_kind, r.deal_id) for r in moved}
    journal_refs = {ref for e in entries if (ref := _deal_ref(e.source, e.source_ref)) is not None}
    from apps.core.models import DealPayment

    with_folio = set()
    if journal_refs:
        with_folio = set(
            DealPayment.objects.filter(_refs_q(journal_refs)).values_list("deal_kind", "deal_id")
        )
    mixes = _Mixes()
    mixes.load(refs)  # остаток без фолио берёт ставки журнала, не состав
    by_deal = defaultdict(list)
    for row in moved:
        by_deal[(row.deal_kind, row.deal_id)].append(row)
    for ref, deal_rows in by_deal.items():
        mix = mixes.get(ref)
        for day, gross in _events(deal_rows):
            if von <= day <= bis:
                acc.add_mixed(gross, mix)
    # Остаток, полученный при исполнении без строки фолио (оплата на месте после
    # онлайн-депозита): журнал сделки больше, чем пришло по книге, — разница в день
    # исполнения. Сверяем с ПОЛУЧЕННЫМ без вычета возвратов: возврат уже учтён в
    # своём месяце, а снижение цены (Minderung) уменьшает и журнал.
    covered = defaultdict(lambda: ZERO)
    journal_by_deal = defaultdict(list)
    legacy = False
    for e in entries:
        ref = _deal_ref(e.source, e.source_ref)
        if ref is None or ref not in with_folio:
            acc.add(e.amount, e.vat_rate)
            legacy = True
            continue
        journal_by_deal[ref].append(e)
    if journal_by_deal:
        journal = _journal_of(set(journal_by_deal))
        for row in _folio_rows(set(journal_by_deal)):
            covered[(row.deal_kind, row.deal_id)] += Decimal(row.amount_cents) / 100
        for ref, deal_entries in journal_by_deal.items():
            posted_entries = journal.get(ref, ())
            gap = sum((e.amount for e in posted_entries), ZERO) - covered[ref]
            # Разница — один раз, в день ПОСЛЕДНЕЙ положительной проводки сделки
            # (иначе сделка с журналом в двух месяцах дала бы её дважды).
            last = max((e.date for e in posted_entries if e.amount > 0), default=None)
            here = [e for e in deal_entries if e.date == last and e.amount > 0]
            here_sum = sum((e.amount for e in here), ZERO)
            if gap <= 0 or here_sum <= 0:
                continue
            share = gap / here_sum  # вся разница — по ставкам последней проводки
            for e in here:
                acc.add(e.amount * share, e.vat_rate)
    notes.append(
        _(
            "Einnahmen oben nach Leistungsdatum; Umsatzsteuer hier nach Zahlungseingang. "
            "Vorsteuer nach Belegdatum."
        )
    )
    if legacy:
        notes.append(
            _(
                "Aufträge, Gutscheine, Mehrfachkarten, manuelle Buchungen und ältere "
                "Verkäufe ohne Zahlungsbuch sind nach Buchungsdatum enthalten."
            )
        )


def ustva_slice(tenant, von: date, bis: date, entries, expenses) -> dict:
    """Срез за период: строки по ставкам, USt, Vorsteuer, Zahllast, пометки."""
    regime = regime_of(tenant)
    notes: list = []
    if regime == REGIME_KLEIN:
        notes.append(_("Kleinunternehmer (§ 19 UStG): keine Umsatzsteuer, kein Vorsteuerabzug."))
        return {
            "regime": regime,
            "rows": [],
            "ust": ZERO,
            "vorsteuer": ZERO,
            "zahllast": ZERO,
            "notes": notes,
        }
    entries = list(entries)
    acc = _Acc()
    if regime == REGIME_IST:
        _ist(von, bis, entries, acc, notes)
    else:
        _soll(von, bis, entries, acc, notes)
    if acc.unmapped:
        notes.append(
            _("Einige Zahlungen ohne erkennbare Leistung — mit dem Regelsteuersatz angesetzt.")
        )
    rows = []
    for rate in sorted(acc.by_rate, reverse=True):
        gross = acc.by_rate[rate].quantize(CENT)
        if not gross:
            continue
        rows.append({"rate": rate, "gross": gross, "vat": _vat(gross, rate).quantize(CENT)})
    ust = sum((r["vat"] for r in rows), ZERO)
    vorsteuer = sum((_vat(e.amount, e.vat_rate) for e in expenses if e.vat_rate), ZERO).quantize(
        CENT
    )
    return {
        "regime": regime,
        "rows": rows,
        "ust": ust,
        "vorsteuer": vorsteuer,
        "zahllast": ust - vorsteuer,
        "notes": notes,
    }
