"""X8: поиск по ДАННЫМ для палитры Ctrl+K (план x8-palette-data-plan-2026-08-19).

Сценарий №1 микро-владельца — «найти заказ фрау Мюллер», а не «открыть раздел».
Палитра W8 искала только названия разделов; здесь — тонкий слой ПОВЕРХ уже
существующих (и уже гейтнутых замками) поисков:

- сделки  → `transactions._managed_queryset(kind, q=…)` по видимым kind (X6-2);
- клиенты → тот же фильтр, что список CRM (`crm.views._filtered_customers`);
- предложения → `sellable_manage.sellable_manage_sections_for(q=…)` (X6-2).

Новых способов ЧТЕНИЯ данных не вводим: гейты модулей и изоляция схемой
тенанта наследуются от источников.
"""

from django.utils.translation import gettext_lazy as _

MIN_QUERY = 2  # «а» ничего не значит и стоит полного скана
PER_SECTION = 5
TOTAL_CAP = 20

SECTION_LABELS = {
    "deals": _("Verkäufe"),
    "customers": _("Kontakte"),
    "sellables": _("Sortiment"),
}


def _deals(tenant, q: str) -> list[dict]:
    from apps.core import sales_page, transactions

    out = []
    for kind in sales_page.visible_kinds(tenant):
        for obj in transactions._managed_queryset(kind, q=q)[:PER_SECTION]:
            tx = transactions.transaction_for(kind, obj)
            if tx is None:
                continue
            out.append(
                {
                    "label": tx.title,
                    "sub": f"#{tx.reference_code}" + (f" · {tx.customer}" if tx.customer else ""),
                    "url": tx.manage_url or "",
                }
            )
            if len(out) >= PER_SECTION:
                return out
    # MX-7: Sofort-Angebot (orders.Offer) — вторая смета, которой не было ни на
    # доске, ни в поиске (перепись v2 §1). Ищем по получателю; вход — тред inbox.
    if tenant.is_module_active("orders") and len(out) < PER_SECTION:
        from django.db.models import Q as _Q
        from django.urls import NoReverseMatch, reverse

        from apps.orders.models import Offer

        offers = Offer.objects.filter(
            _Q(customer_name__icontains=q) | _Q(customer_email__icontains=q)
        ).order_by("-created_at")[: PER_SECTION - len(out)]
        for offer in offers:
            try:
                url = reverse("inbox:thread", args=[offer.conversation_id])
            except (NoReverseMatch, AttributeError):
                url = ""
            out.append(
                {
                    "label": _("Angebot · %(who)s")
                    % {"who": offer.customer_name or offer.customer_email},
                    "sub": f"{offer.get_status_display()}",
                    "url": url,
                }
            )
    return out


def _customers(tenant, q: str) -> list[dict]:
    if not tenant.is_module_active("crm"):
        return []
    from django.db.models import Q
    from django.urls import reverse

    from apps.crm.models import Customer

    qs = Customer.objects.filter(
        Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
    )
    return [
        {
            "label": c.name or c.email,
            "sub": c.email or c.phone or "",
            "url": reverse("crm:customer-detail", args=[c.pk]),
        }
        for c in qs[:PER_SECTION]
    ]


def _sellables(tenant, q: str) -> list[dict]:
    from apps.core import sellable_manage

    out = []
    for section in sellable_manage.sellable_manage_sections_for(tenant, limit=PER_SECTION, q=q):
        for item in section["items"]:
            out.append(
                {
                    "label": item.name,
                    "sub": str(section["label"]),
                    "url": item.edit_url or "",
                }
            )
            if len(out) >= PER_SECTION:
                return out
    return out


def search(tenant, q: str) -> list[dict]:
    """Секции результата: [{key, label, items:[{label, sub, url}]}].
    Короткий запрос → пустой ответ БЕЗ запросов в БД."""
    q = (q or "").strip()
    if len(q) < MIN_QUERY:
        return []
    sections, total = [], 0
    for key, fn in (("deals", _deals), ("customers", _customers), ("sellables", _sellables)):
        try:
            items = fn(tenant, q)
        except Exception:  # noqa: BLE001 — одна секция не валит палитру
            items = []
        items = [i for i in items if i["url"]][: max(0, min(PER_SECTION, TOTAL_CAP - total))]
        if items:
            total += len(items)
            sections.append({"key": key, "label": SECTION_LABELS[key], "items": items})
        if total >= TOTAL_CAP:
            break
    return sections
