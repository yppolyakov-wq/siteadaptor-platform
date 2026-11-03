"""UX-D D6.5: Finanzen — «＋ Buchung»/«＋ Ausgabe» шторками, «＋ Neue Rechnung» страницей.

Раньше формы журнала, расходов и счёта висели раскрытыми под списками, а ошибка ввода
(редирект с сообщением) стирала всё введённое — у счёта до 8 строк. Теперь разбор — один
на шторку/страницу и старые формы (`parse_*`): строгий (D6.0), ошибка — у поля, ввод
сохраняется, ничего не пишется. Контракт шторки — `docs/references/patterns/drawer.md`."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core.owner_login import local_next

from .models import ExpenseEntry, RevenueEntry
from .services import record_revenue

logger = logging.getLogger(__name__)
INVOICE_LINES = 8


def _vat(raw, default: str):
    """Ставка из белого списка; неизвестная → None (ошибка у поля, а не молча 19 %)."""
    raw = (raw or default).strip()
    return next((r for r in RevenueEntry.VAT_RATES if str(r) == raw), None)


def _amount(post, field, errors, *, allow_negative=False, required=True):
    from .views import _FormError, _post_amount

    raw = post.get(field)
    if not required and not (raw or "").strip():
        return None
    try:
        return _post_amount(raw, allow_negative=allow_negative)
    except _FormError as exc:
        errors[field] = str(exc)
        return None


def _date(post, field, default, errors):
    from .views import _FormError, _post_date

    try:
        return _post_date(post.get(field), default)
    except _FormError as exc:
        errors[field] = str(exc)
        return None


# --- Журнал выручки -------------------------------------------------------------------


def parse_journal(post) -> tuple[dict, dict]:
    errors, out = {}, {}
    out["amount"] = _amount(post, "amount", errors)
    if out["amount"] is not None and out["amount"] <= 0:
        errors["amount"] = _("Amount must be positive.")
    out["vat_rate"] = _vat(post.get("vat_rate"), "19.00")
    if out["vat_rate"] is None:
        errors["vat_rate"] = _("Invalid input.")
    out["date"] = _date(post, "date", timezone.localdate(), errors)
    out["note"] = (post.get("note") or "").strip()[:200]
    return out, errors


def _values(post, fields) -> dict:
    return {f: (post.get(f) or "").strip()[:500] for f in fields}


def _render(request, ctx, *, drawer_tpl, page_tpl, back):
    ctx.setdefault("next_url", drawer_mod.drawer_next(request, reverse(back)))
    if request.method == "POST":
        ctx["next_url"] = local_next(request) or ctx["next_url"]
    if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
        return drawer_mod.fragment(render(request, drawer_tpl, ctx))
    return render(request, page_tpl, ctx)


JOURNAL_FIELDS = ("amount", "vat_rate", "date", "note")


@login_required
@drawer_mod.drawer_aware
def journal_new(request):
    """«＋ Buchung» — ручная выручка (продажа у кассы) шторкой."""

    def form(values, errors=None):
        return _render(
            request,
            {
                "nav": "finance",
                "fv": values,
                "fv_errors": errors or {},
                "vat_rates": RevenueEntry.VAT_RATES,
            },
            drawer_tpl="finance/_journal_new_drawer.html",
            page_tpl="finance/journal_new.html",
            back="finance:journal",
        )

    if request.method != "POST":
        return form({"date": timezone.localdate().isoformat(), "vat_rate": "19.00"})
    values, errors = parse_journal(request.POST)
    if errors:
        if drawer_mod.is_drawer(request):
            messages.error(request, next(iter(errors.values())))
        return form(_values(request.POST, JOURNAL_FIELDS), errors)
    record_revenue(source=RevenueEntry.SOURCE_MANUAL, **values)
    messages.success(request, _("Entry added."))
    return redirect(local_next(request) or reverse("finance:journal"))


# --- Расходы --------------------------------------------------------------------------

EXPENSE_FIELDS = ("amount", "vat_rate", "supplier", "due_date", "category", "date", "note")


def parse_expense(post) -> tuple[dict, dict]:
    errors, out = {}, {}
    out["amount"] = _amount(post, "amount", errors)
    if out["amount"] is not None and out["amount"] <= 0:
        errors["amount"] = _("Amount must be positive.")
    out["vat_rate"] = _vat(post.get("vat_rate"), "0.00")
    if out["vat_rate"] is None:
        errors["vat_rate"] = _("Invalid input.")
    category = post.get("category") or ""
    out["category"] = (
        category if category in dict(ExpenseEntry.CATEGORIES) else ExpenseEntry.CATEGORY_OTHER
    )
    out["supplier"] = None
    raw = post.get("supplier") or ""
    if raw:
        from apps.inventory.models import Lieferant

        try:
            out["supplier"] = Lieferant.objects.filter(pk=uuid.UUID(raw)).first()
        except ValueError:
            out["supplier"] = None
        if out["supplier"] is None:
            errors["supplier"] = _("Nicht gefunden.")
    out["due_date"] = _date(post, "due_date", None, errors)
    out["date"] = _date(post, "date", timezone.localdate(), errors)
    out["note"] = (post.get("note") or "").strip()[:200]
    return out, errors


def create_expense(request, values) -> ExpenseEntry:
    """Запись расхода + Beleg (шифрованный SecureDocument). Битый файл не роняет запись,
    но владелец видит предупреждение (и причина пишется в лог)."""
    document = None
    if request.FILES.get("beleg"):
        from apps.documents import services as doc_services
        from apps.documents.models import SecureDocument

        try:
            document = doc_services.store(
                request.FILES["beleg"],
                owner=None,
                kind=SecureDocument.KIND_RECEIPT,
                note="Eingangsrechnung",
                uploaded_by=str(request.user)[:150],
            )
        except Exception:  # noqa: BLE001 — битый файл не роняет запись расхода
            logger.exception("expense receipt upload failed")
            messages.warning(request, _("Beleg konnte nicht gespeichert werden."))
    return ExpenseEntry.objects.create(
        source=ExpenseEntry.SOURCE_MANUAL,
        amount=values["amount"],
        category=values["category"],
        vat_rate=values["vat_rate"],
        supplier=values["supplier"],
        due_date=values["due_date"],
        paid_at=None if values["due_date"] else timezone.localdate(),
        document=document,
        date=values["date"],
        note=values["note"],
    )


@login_required
@drawer_mod.drawer_aware
def expense_new(request):
    """«＋ Ausgabe» — расход/входящий счёт шторкой (с Beleg)."""
    from apps.inventory.models import Lieferant

    def form(values, errors=None):
        return _render(
            request,
            {
                "nav": "finance",
                "fv": values,
                "fv_errors": errors or {},
                "vat_rates": RevenueEntry.VAT_RATES,
                "categories": ExpenseEntry.CATEGORIES,
                "suppliers": Lieferant.objects.order_by("name"),
            },
            drawer_tpl="finance/_expense_new_drawer.html",
            page_tpl="finance/expense_new.html",
            back="finance:expenses",
        )

    if request.method != "POST":
        return form({"date": timezone.localdate().isoformat(), "vat_rate": "0.00"})
    values, errors = parse_expense(request.POST)
    if errors:
        if drawer_mod.is_drawer(request):
            messages.error(request, next(iter(errors.values())))
        return form(_values(request.POST, EXPENSE_FIELDS), errors)
    create_expense(request, values)
    messages.success(request, _("Entry added."))
    return redirect(local_next(request) or reverse("finance:expenses"))


# --- Счёт -----------------------------------------------------------------------------


def parse_invoice(post, tenant) -> tuple[dict, dict]:
    """Строки (до 8), ставка, клиент, получатель, язык → (данные, ошибки).

    Ошибка строки — у её поля (`line_price_3`); строка без текста пропускается."""
    from apps.core.documents import business_language, clean_language
    from apps.promotions.models import Customer

    errors, lines = {}, []
    for index in range(1, INVOICE_LINES + 1):
        text = (post.get(f"line_text_{index}") or "").strip()
        if not text:
            continue
        raw_qty = (post.get(f"line_qty_{index}") or "1").strip()
        if not raw_qty.isascii() or not raw_qty.isdigit() or not 1 <= int(raw_qty) <= 9999:
            errors[f"line_qty_{index}"] = _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {
                "lo": 1,
                "hi": 9999,
            }
            continue
        price = _amount(post, f"line_price_{index}", errors, allow_negative=True, required=False)
        if f"line_price_{index}" in errors:
            continue
        lines.append(
            {"text": text[:200], "qty": int(raw_qty), "unit_price": str(price or Decimal("0"))}
        )
    if not lines and not errors:
        errors["line_text_1"] = _("Add at least one line.")
    vat_rate = _vat(post.get("vat_rate"), "19.00")
    if vat_rate is None:
        errors["vat_rate"] = _("Invalid input.")
    customer = None
    raw = post.get("customer") or ""
    if raw:
        try:
            customer = Customer.objects.select_related("company").filter(pk=uuid.UUID(raw)).first()
        except ValueError:
            customer = None
        if customer is None:
            errors["customer"] = _("Nicht gefunden.")
    data = {
        "lines": lines,
        "vat_rate": vat_rate,
        "customer": customer,
        "recipient": (post.get("recipient") or "").strip()[:500],
        "note": (post.get("note") or "").strip()[:200],
        "language": clean_language(post.get("language"), tenant) or business_language(tenant),
    }
    return data, errors


def create_invoice(tenant, data):
    """Черновик счёта из разобранных данных (нумерация — при выставлении, GoBD)."""
    from .models import Invoice
    from .services import compute_totals

    small = tenant.small_business
    net, vat, gross = compute_totals(data["lines"], data["vat_rate"], small_business=small)
    customer = data["customer"]
    # CO-2: корпоративный гость без явного получателя → реквизиты компании.
    company_recipient = (
        customer.company.invoice_recipient if customer and customer.company_id else ""
    )
    return Invoice.objects.create(
        customer=customer,
        language=data["language"],
        recipient=data["recipient"] or company_recipient or (str(customer) if customer else ""),
        lines=data["lines"],
        vat_rate=Decimal("0") if small else data["vat_rate"],
        net=net,
        vat_amount=vat,
        gross=gross,
        note=data["note"],
    )


INVOICE_FIELDS = (
    "customer",
    "vat_rate",
    "recipient",
    "note",
    "language",
    *(f"line_{k}_{i}" for i in range(1, INVOICE_LINES + 1) for k in ("text", "qty", "price")),
)


@login_required
def invoice_new(request):
    """«＋ Neue Rechnung» — страница (8 строк + поиск клиента). Ошибка не стирает ввод."""
    from apps.core.documents import business_language, language_choices

    from .views import _customer_context

    errors = {}
    if request.method == "POST":
        data, errors = parse_invoice(request.POST, request.tenant)
        if not errors:
            invoice = create_invoice(request.tenant, data)
            messages.success(request, _("Draft created."))
            return redirect("finance:invoice-detail", pk=invoice.pk)
        values = _values(request.POST, INVOICE_FIELDS)
    else:
        values = {"vat_rate": "19.00", "language": business_language(request.tenant)}
    ctx = _customer_context(request)
    if request.method == "POST" and values.get("customer"):
        # выбранный клиент остаётся в селекте после ошибки
        from apps.promotions.models import Customer

        try:
            chosen = Customer.objects.filter(pk=uuid.UUID(values["customer"])).first()
        except ValueError:
            chosen = None
        if chosen and all(c.pk != chosen.pk for c in ctx["customers"]):
            chosen.pick_label = chosen.name or "—"
            ctx["customers"] = [chosen, *ctx["customers"]]
        ctx["selected_customer"] = chosen
    rows = [
        {
            "i": i,
            "text": values.get(f"line_text_{i}", ""),
            "qty": values.get(f"line_qty_{i}", "1") or "1",
            "price": values.get(f"line_price_{i}", ""),
            "err_qty": errors.get(f"line_qty_{i}"),
            "err_price": errors.get(f"line_price_{i}"),
            "err_text": errors.get(f"line_text_{i}"),
        }
        for i in range(1, INVOICE_LINES + 1)
    ]
    return render(
        request,
        "finance/invoice_new.html",
        {
            "nav": "finance",
            "fv": values,
            "fv_errors": errors,
            "rows": rows,
            "vat_rates": RevenueEntry.VAT_RATES,
            "small_business": request.tenant.small_business,
            "doc_languages": language_choices(request.tenant),
            **ctx,
        },
    )
