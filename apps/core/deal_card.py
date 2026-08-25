"""DC-1: единый скелет карточки сделки (ТЗ владельца 2026-08-25).

Требование владельца: «базовые функции и блоки должны иметь общие настройки —
меняется один, меняются все сразу». Поэтому вид карточки задаёт ОДИН шаблон
`core/deal_card_base.html` + общие партиалы `core/_deal_*.html`, а этот модуль —
их единый контекст: контракт `Transaction` (номер, статус, суммы, переходы),
гейты модулей и календарь сделки.

Секции карточки включаются ПО ДАННЫМ, а не по типу бизнеса: список позиций есть
там, где есть позиции; календарь — там, где у направления есть календарный
движок (бронь номера — Belegungsplan, запись — Tagesplan, заказ — Auftragsbuch
при используемых слотах выдачи). У заявок и билетов движка нет — блок не
рисуется вовсе, вместо пустой рамки.
"""

from __future__ import annotations

import copy
from dataclasses import replace as _dc_replace

from django.http import QueryDict
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from apps.core import status_labels, transactions, transition_rules

# Подписи секций — в одном месте: правка меняет ВСЕ карточки сразу.
SECTION_TITLES = {
    "items": _("Positionen"),
    "discount": _("Rabatt"),
    "totals": _("Summen"),
    "payment": _("Zahlung & Rechnung"),
    "status": _("Status"),
    "customer": _("Kunde"),
    "calendar": _("Kalender"),
}

# Календарный движок направления: (шаблон тела, функция контекста).
_CALENDARS = {
    "stay": ("stays/_belegungsplan_body.html", "apps.stays.views.calendar_context"),
    "booking": ("booking/_tagesplan_body.html", "apps.booking.views.calendar_context"),
    "order": ("orders/_auftragsbuch_body.html", "apps.orders.views.auftragsbuch_context"),
}


def _module_active(tenant, key: str) -> bool:
    try:
        return bool(tenant and tenant.is_module_active(key))
    except Exception:  # noqa: BLE001 — гейты карточки fail-closed
        return False


def _resolve(path: str):
    module, _sep, name = path.rpartition(".")
    return getattr(__import__(module, fromlist=[name]), name)


def _calendar_query(kind: str, obj) -> dict | None:
    """GET-параметры календаря, наведённого на саму сделку."""
    from datetime import timedelta

    if kind == "stay":
        arrival = getattr(obj, "arrival", None)
        # Окно Belegungsplan начинается за пару дней до заезда — бронь видна сразу.
        return {"von": (arrival - timedelta(days=2)).isoformat()} if arrival else {}
    if kind == "booking":
        start = getattr(obj, "start", None)
        return {"tag": start.date().isoformat()} if start else {}
    if kind == "order":
        slot = getattr(obj, "pickup_slot", None)
        return {"tag": slot.date().isoformat()} if slot else {}
    return None


def calendar_html(request, kind: str, obj) -> str:
    """Календарь сделки, развёрнутый (владелец: «открывается сразу ниже сетки»).

    Тот же движок, что на странице продаж, — тела календарей партиализованы
    волной V. Ошибка построения не должна ронять карточку: календарь
    вспомогательный, а карточка — рабочая поверхность."""
    spec = _CALENDARS.get(kind)
    query = _calendar_query(kind, obj)
    if not spec or query is None:
        return ""
    tenant = getattr(request, "tenant", None)
    if kind == "order":
        from apps.core import sales_page

        # SH-1: Auftragsbuch показываем только там, где слоты выдачи реально ставятся.
        if "kalender" not in sales_page.views_for("order", tenant):
            return ""
    template, ctx_path = spec
    try:
        sub = copy.copy(request)  # поверхностная копия: оригинальный GET не трогаем
        sub.GET = (
            QueryDict(mutable=False)
            if not query
            else QueryDict("&".join(f"{k}={v}" for k, v in query.items()))
        )
        ctx = _resolve(ctx_path)(sub)
        if not isinstance(ctx, dict):  # ?box=1 — фрагмент карточки, не наш случай
            return ""
        # На карточке сделки календарь показывает ЗАНЯТОСТЬ; формы создания новой
        # брони/записи живут на самом календаре продаж (иначе карточка одной
        # сделки предлагала бы завести другую).
        ctx["deal_calendar_compact"] = True
        return render_to_string(template, ctx, request=sub)
    except Exception:  # noqa: BLE001 — см. docstring
        return ""


def card_context(request, kind: str, obj, *, sections=(), links=None, hide_targets=()) -> dict:
    """Общий контекст карточки сделки для `core/deal_card_base.html`.

    `sections` — какие секции наполняет конкретная карточка (по данным);
    базовый шаблон рисует обёртку только для перечисленных."""
    tenant = getattr(request, "tenant", None)
    deal = transactions.transaction_for(
        kind,
        obj,
        status_labels.custom_labels(tenant, kind),
        transition_rules.subset_for(tenant, kind),
    )
    if hide_targets:
        # Переход, у которого есть СВОЙ приёмник со сторонним эффектом (у заявки
        # «invoiced» ещё и выставляет счёт), из общих кнопок статуса убираем —
        # иначе generic-путь сменил бы статус без этого эффекта.
        deal = _dc_replace(
            deal,
            allowed_actions=[
                a for a in deal.allowed_actions if a.get("target") not in hide_targets
            ],
        )
    calendar = calendar_html(request, kind, obj)
    # «Когда» в мете печатаем, только если этой даты ещё нет в заголовке сделки
    # (у брони номера title уже содержит даты — иначе строка дублируется).
    when = getattr(deal, "when", None)
    show_when = bool(
        when
        and getattr(when, "strftime", None)
        and when.strftime("%d.%m") not in (deal.title or "")
    )
    return {
        "deal": deal,
        "deal_obj": obj,
        "deal_kind": kind,
        "deal_sections": tuple(sections),
        "deal_titles": SECTION_TITLES,
        "deal_calendar_html": calendar,
        "deal_show_when": show_when,
        # DC-5: скидка владельца — общий блок между составом и суммами.
        "deal_discount_cents": int(getattr(obj, "discount_cents", 0) or 0),
        "deal_discount_input": f"{int(getattr(obj, 'discount_cents', 0) or 0) / 100:.2f}",
        "deal_discount_note": getattr(obj, "voucher_code", "") or "",
        # DC-4: внешний номер правится прямо в голове — там, где поле есть.
        "deal_external_editable": hasattr(obj, "external_code"),
        "deal_external_code": getattr(obj, "external_code", ""),
        "deal_links": links,
        "crm_active": _module_active(tenant, "crm"),
        "inbox_active": _module_active(tenant, "inbox"),
    }
