"""Кабинет заказов Click & Collect (Track D / D2b): /dashboard/orders/.

Список входящих с фильтром по статусу, карточка заказа, действия по FSM
(confirm/ready/picked_up/cancel — каждое шлёт письмо клиенту через OrderSM)
и ручная отметка оплаты (v1 — оплата в магазине). Гейтинг модуля «orders» —
ModuleGatingMiddleware по префиксу из реестра.
"""

from decimal import Decimal, InvalidOperation

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core import deal_links
from apps.core.fsm import IllegalTransition

from .models import Order
from .services import OutOfStock
from .state_machine import OrderSM


def _refund_order(request, order):
    """Анти-фрод: вернуть оплату при отмене оплаченного заказа (Stripe Connect)."""
    try:
        connect.refund(
            connect_id=request.tenant.stripe_connect_id,
            payment_intent=order.stripe_payment_intent,
        )
        order.payment_state = Order.PAYMENT_REFUNDED
        order.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Payment refunded."))
    except stripe.error.StripeError:
        messages.error(request, _("Refund failed — please check Stripe."))


def auftragsbuch_context(request):
    """V3 (план unified-sales-page-plan-2026-08-03): Auftragsbuch — заказы по
    ДНЯМ выдачи (DACH-традиция книги заказов пекарни). Ось — `Order.pickup_slot`
    (флоу «заказ ко времени»); активные заказы без слота — блок «ohne Termin».
    Только представление, движок заказов не трогается."""
    from datetime import date, timedelta

    from django.utils import timezone

    from apps.core import status_registry

    try:
        start = date.fromisoformat(request.GET.get("von") or "")
    except ValueError:
        start = timezone.localdate()
    window = 14
    days = [start + timedelta(days=i) for i in range(window)]
    active = status_registry.counted_statuses("order") or ("new", "confirmed", "ready")
    qs = (
        Order.objects.filter(
            pickup_slot__date__gte=start,
            pickup_slot__date__lt=start + timedelta(days=window),
        )
        .select_related("customer")
        .order_by("pickup_slot")
    )
    by_day = {d: [] for d in days}
    for o in qs:
        by_day[timezone.localtime(o.pickup_slot).date()].append(o)
    return {
        "ab_days": [(d, by_day.get(d, [])) for d in days],
        "ab_start": start,
        "ab_prev": start - timedelta(days=window),
        "ab_next": start + timedelta(days=window),
        "ab_today": timezone.localdate(),
        "ab_ohne": (
            Order.objects.filter(pickup_slot__isnull=True, status__in=active)
            .select_related("customer")
            .order_by("-created_at")[:50]
        ),
    }


@login_required
def order_list(request):
    """W10-6: легаси-список заказов — 302 на order-Liste единой страницы
    (паритет достигнут W10-3a: фильтр статуса, поиск, KDS/QR; GET сохраняется)."""
    from apps.core.sales_page import legacy_redirect

    return legacy_redirect(request, tab="order", view="liste")


@login_required
def deliveries(request):
    """R7-3 «Lieferungen» (фидбэк владельца 2026-08-24: «доставку нужно вынести
    отдельно, там могут формироваться отгрузочные накладные»).

    Отдельная рабочая поверхность доставки: заказы с фулфилментом «Lieferung»,
    адрес, трек-номер, накладная (Lieferschein-PDF, приёмник прежний) и смена
    статуса ТЕМ ЖЕ путём, что везде (`board-action` → transactions.apply_action),
    поэтому письмо с Sendungsnummer уходит штатно (W10-5). Фильтр «offen» =
    ещё не отправленные/не закрытые.
    """
    from apps.core import status_registry, transactions

    state = request.GET.get("state", "offen")
    qs = (
        Order.objects.filter(fulfillment=Order.FULFILLMENT_DELIVERY)
        .select_related("customer")
        .prefetch_related("items")
    )
    done = (Order.STATUS_SHIPPED, Order.STATUS_PICKED_UP, Order.STATUS_RETURNED)
    cancelled = status_registry.cancelled_statuses_for("order", request.tenant)
    if state == "offen":
        qs = qs.exclude(status__in=list(done) + list(cancelled))
    elif state == "versendet":
        qs = qs.filter(status=Order.STATUS_SHIPPED)
    rows = []
    for order in qs.order_by("-created_at")[:200]:
        tx = transactions.transaction_for("order", order)
        rows.append({"order": order, "tx": tx})
    return render(
        request,
        "orders/deliveries.html",
        {
            "nav": "deliveries",
            "rows": rows,
            "state": state,
            "states": (
                ("offen", _("Offen")),
                ("versendet", _("Versendet")),
                ("", _("Alle")),
            ),
        },
    )


def _active_kitchen_orders():
    """Заказы в работе для KDS: принятые/новые, старые сверху (FIFO кухни)."""
    return (
        Order.objects.filter(status__in=(Order.STATUS_NEW, Order.STATUS_CONFIRMED))
        .select_related("customer")
        .prefetch_related("items")
        .order_by("created_at")
    )


@login_required
def kitchen(request):
    """Küchen-Display (KDS, A4): экран очереди заказов с авто-обновлением.

    Полная страница; доска заказов перезагружается HTMX-поллингом (_kitchen_board).
    Гейтинг модуля «orders» — ModuleGatingMiddleware по префиксу из реестра.
    """
    return render(
        request,
        "orders/kitchen.html",
        {"orders": _active_kitchen_orders(), "nav": "orders"},
    )


@login_required
def table_qr(request):
    """T2a: печатный лист QR-кодов столов. Каждый QR ведёт на витрину с
    ?tisch=N&ch=qr — гость сканирует, заказывает, заказ привязан к столу.

    Кабинет на домене арендатора → build_absolute_uri даёт верный хост витрины.
    Гейтинг модуля «orders» — ModuleGatingMiddleware.
    """
    import segno

    try:
        count = int(request.GET.get("count", "12"))
    except (TypeError, ValueError):
        count = 12
    count = max(1, min(count, 60))
    tables = []
    for n in range(1, count + 1):
        url = request.build_absolute_uri(f"/?tisch={n}&ch=qr")
        data_uri = segno.make(url, error="m").svg_data_uri(scale=4, border=2)
        tables.append({"n": n, "data_uri": data_uri})
    return render(
        request,
        "orders/table_qr.html",
        {"tables": tables, "count": count, "nav": "orders"},
    )


@login_required
def kitchen_board(request):
    """HTMX-партиал доски KDS (поллинг каждые несколько секунд)."""
    return render(request, "orders/_kitchen_board.html", {"orders": _active_kitchen_orders()})


@login_required
@require_POST
def kitchen_action(request, pk):
    """Действие с доски KDS (Annehmen new→confirmed / Fertig confirmed→ready).

    Возвращает обновлённый партиал доски для HTMX-swap (без перезагрузки экрана).
    """
    order = get_object_or_404(Order, pk=pk)
    action = request.POST.get("action", "")
    if action in ("confirmed", "ready"):
        try:
            OrderSM().apply(order, action, actor=request.user)
        except IllegalTransition:
            pass  # статус уже сменился (другой экран) — просто перерисуем доску
    return render(request, "orders/_kitchen_board.html", {"orders": _active_kitchen_orders()})


@login_required
def order_detail(request, pk):
    from apps.catalog import picker as catalog_picker
    from apps.core import deal_card, transition_rules

    from . import editing as order_editing
    from .totals import order_totals

    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    sm = OrderSM()
    # FB-3: правила переходов владельца скрывают не-danger переходы (FSM не трогаем).
    subset = transition_rules.subset_for(getattr(request, "tenant", None), "order")
    allowed = [
        t
        for t in sm.allowed_targets(order.status)
        if transition_rules.keep_target(order.status, t, subset)
    ]
    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "items": order.items.all(),
            "allowed_targets": allowed,
            "nav": "orders",
            # SH группа B: правка доступна, пока заказ не закрыт (решение владельца
            # «править всегда»); терминальный — read-only, его склад уже возвращён.
            "editable": order_editing.is_editable(order, getattr(request, "tenant", None)),
            "parts": catalog_picker._catalog_parts(getattr(request, "tenant", None)),
            "shipping_eur_input": f"{order.shipping_cents / 100:.2f}",
            # SH-3/4: разбивка итога (нетто/НДС по ставкам) — один хелпер на все
            # поверхности; §19 Kleinunternehmer обнуляет НДС.
            # SH-9: счёт из заказа — только при активном модуле «Finanzen»
            # (иначе кнопка вела бы в гейт путей → 404, класс сверки 2026-08-19).
            "finance_active": bool(
                getattr(request, "tenant", None) and request.tenant.is_module_active("finance")
            ),
            # VF-3: ссылка на оплату — те же гейты, что публичный /bezahlen/.
            "pay_link_ready": bool(
                order.payment_method == "stripe"
                and order.payment_state == "unpaid"
                and order.status == "new"
                and order.total > 0
                and getattr(request, "tenant", None)
                and request.tenant.payments_enabled
            ),
            "pay_path": reverse("storefront-order-pay", args=[order.reference_code]),
            "totals": order_totals(
                order,
                small_business=bool(
                    getattr(request, "tenant", None) and request.tenant.small_business
                ),
            ),
            "discount_eur_input": f"{order.discount_cents / 100:.2f}",
            # DC-1: общий скелет карточки сделки — голова, статус, клиент, связи
            # и календарь приходят из одного источника (core/deal_card_base.html);
            # crm_active/inbox_active/deal_links тоже оттуда.
            **deal_card.card_context(
                request,
                "order",
                order,
                sections=_order_sections(request, order),
                # VS-3: заказ может быть прикреплён к брони (предзаказ торта к столу).
                links=deal_links.block_context("order", order.pk),
            ),
        },
    )


@login_required
@require_POST
def order_edit(request, pk):
    """SH группа B (фидбэк владельца 2026-08-20): правка заказа из кабинета —
    состав/количество/скидка/доставка/клиент.

    Один приёмник с `action=` (паттерн карточки заявки): вся арифметика и все
    движения склада живут в `orders.editing`, вьюха только разбирает форму.
    Решение владельца: править можно любой НЕзакрытый заказ, склад и леджер
    пересчитываются тем же движком, что создание/отмена."""
    from apps.catalog.models import Product, ProductVariant
    from apps.catalog.picker import _resolve_part, _service_snapshot

    from . import editing

    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    tenant = getattr(request, "tenant", None)
    action = request.POST.get("action", "")
    try:
        if action == "items":
            # Количества всех позиций одной формой: qty_<pk> (0 = удалить).
            for item in list(order.items.all()):
                raw = request.POST.get(f"qty_{item.pk}")
                if raw is None:
                    continue
                try:
                    qty = int(raw)
                except (TypeError, ValueError):
                    continue
                if qty != item.qty:
                    editing.set_item_qty(order, item.pk, qty, tenant=tenant)
            messages.success(request, _("Positionen aktualisiert."))
        elif action == "add_item":
            raw = request.POST.get("part", "")
            title = (request.POST.get("title") or "").strip()
            qty = request.POST.get("qty") or 1
            price_raw = (request.POST.get("price") or "").strip().replace(",", ".")
            price = Decimal(price_raw) if price_raw else None
            products = {str(p.pk): p for p in Product.objects.all()} if raw else {}
            variants = {str(v.pk): v for v in ProductVariant.objects.all()} if raw else {}
            product, variant = _resolve_part(raw, products, variants)
            svc_vat = None
            if product is None and raw.startswith("s:"):
                # Услуга: FK нет, в заказ едет снимок названия/цены (как у сметы).
                svc_title, svc_price, svc_vat = _service_snapshot(raw)
                title = title or (svc_title or "")
                price = price if price is not None else svc_price
            if product is None and (not title or price is None):
                messages.error(request, _("Bitte Position wählen oder Text und Preis angeben."))
            else:
                editing.add_item(
                    order,
                    product=product,
                    variant=variant,
                    qty=qty,
                    title=title,
                    unit_price=price,
                    tenant=tenant,
                    vat_rate=svc_vat,
                )
                messages.success(request, _("Position hinzugefügt."))
        elif action == "discount":
            raw = (request.POST.get("discount") or "0").strip().replace(",", ".")
            cents = int(Decimal(raw or "0") * 100)
            editing.set_discount(
                order, cents=cents, note=request.POST.get("discount_note", ""), tenant=tenant
            )
            messages.success(request, _("Rabatt gespeichert."))
        elif action == "delivery":
            raw = (request.POST.get("shipping") or "").strip().replace(",", ".")
            editing.update_delivery(
                order,
                fulfillment=request.POST.get("fulfillment"),
                address=request.POST.get("shipping_address", ""),
                shipping_cents=int(Decimal(raw) * 100) if raw else None,
                tenant=tenant,
            )
            messages.success(request, _("Lieferung gespeichert."))
        elif action == "numbers":
            # SH-8: внешний номер (касса/маркетплейс) — свободное поле рядом с
            # собственным кодом; сам reference_code не трогаем: на него ссылаются
            # письма, PDF, платежи и поиск.
            order.external_code = (request.POST.get("external_code") or "").strip()[:50]
            order.save(update_fields=["external_code", "updated_at"])
            messages.success(request, _("Nummern gespeichert."))
        elif action == "payment":
            # SH-9: плательщик и способ оплаты. `payment_state` меняет отдельная
            # кнопка «оплачено» (там же возврат Stripe) — здесь только реквизиты.
            method = request.POST.get("payment_method", "")
            if method in dict(Order.PAYMENT_METHODS) or method == "":
                order.payment_method = method
            order.billing_name = (request.POST.get("billing_name") or "").strip()[:200]
            order.billing_address = (request.POST.get("billing_address") or "").strip()[:1000]
            order.save(
                update_fields=["payment_method", "billing_name", "billing_address", "updated_at"]
            )
            messages.success(request, _("Zahlungsdaten gespeichert."))
        elif action == "invoice":
            from apps.finance.services import invoice_from_order

            invoice = invoice_from_order(order, getattr(request, "tenant", None))
            messages.success(request, _("Rechnungsentwurf erstellt."))
            return redirect("finance:invoice-detail", pk=invoice.pk)
        elif action == "invoice_pdf":
            # VF-3: «сохранение PDF счёта» одним действием — черновик по заказу
            # переиспользуется (иначе каждый клик плодил бы дубли в Finanzen);
            # номер НЕ присваивается (GoBD: только issue), PDF черновика легален.
            from apps.finance.models import Invoice
            from apps.finance.services import invoice_from_order

            note = f"Auftrag {order.reference_code}"
            invoice = (
                Invoice.objects.filter(status="draft", note=note).order_by("-created_at").first()
            )
            if invoice is None:
                invoice = invoice_from_order(order, getattr(request, "tenant", None))
            return redirect("finance:invoice-pdf", pk=invoice.pk)
        elif action == "payment_link":
            # VF-3: «отправка ссылки на оплату» — письмо с прямой /bezahlen/
            # (гейты зеркалят публичную страницу: Stripe + не оплачен + new).
            from django.utils import timezone as _tz

            from .notifications import enqueue_order_email

            payable = (
                order.payment_method == "stripe"
                and order.payment_state == "unpaid"
                and order.status == "new"
                and order.total > 0
                and getattr(request, "tenant", None)
                and request.tenant.payments_enabled
            )
            email = getattr(order.customer, "email", "")
            if not payable:
                messages.error(
                    request,
                    _(
                        "Zahlungslink nicht verfügbar: Zahlart Stripe, Status neu und offene Zahlung nötig."
                    ),
                )
            elif not email:
                messages.error(request, _("Der Kunde hat keine E-Mail-Adresse."))
            else:
                enqueue_order_email(
                    order,
                    "payment_link",
                    dedupe_suffix=f":{_tz.now():%Y%m%d%H%M%S}",
                )
                messages.success(
                    request,
                    _("Zahlungslink wurde an %(email)s gesendet.") % {"email": email},
                )
        elif action == "customer":
            editing.update_customer(
                order,
                name=request.POST.get("name", ""),
                email=request.POST.get("email", ""),
                phone=request.POST.get("phone", ""),
            )
            messages.success(request, _("Kundendaten gespeichert."))
        else:
            messages.error(request, _("Unknown action."))
    except editing.OrderLocked as exc:
        messages.error(request, str(exc))
    except OutOfStock as exc:
        messages.error(
            request,
            _("Nicht genug Bestand: %(title)s (verfügbar: %(n)s).")
            % {"title": exc.title, "n": exc.available},
        )
    except (InvalidOperation, ValueError):
        messages.error(request, _("Bitte Zahlen im Format 12,50 eingeben."))
    return redirect("orders:order-detail", pk=order.pk)


@login_required
@require_POST
def order_action(request, pk):
    order = get_object_or_404(Order, pk=pk)
    action = request.POST.get("action", "")
    if action == "mark_paid":
        order.payment_state = Order.PAYMENT_PAID
        order.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Marked as paid."))
    elif action in ("confirmed", "ready", "picked_up", "shipped", "cancelled", "returned"):
        # W10-5: спец-поля (tracking_code при shipped) пишет единая точка
        # apply_action ДО apply — письмо включает номер; shipped_at ставит FSM (W7c).
        from apps.core import transactions as core_transactions

        try:
            core_transactions.apply_action(
                "order", order, action, actor=request.user, extra=request.POST
            )
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect("orders:order-detail", pk=order.pk)
        messages.success(request, _("Order updated."))
        # Отмена/возврат оплаченного заказа возвращает оплату (Widerruf/анти-фрод).
        if (
            action in ("cancelled", "returned")
            and order.payment_state == Order.PAYMENT_PAID
            and order.stripe_payment_intent
        ):
            _refund_order(request, order)
    else:
        messages.error(request, _("Unknown action."))
    return redirect("orders:order-detail", pk=order.pk)


@login_required
def delivery_note_pdf(request, pk):
    """Lieferschein-PDF заказа (A2b) — накладная + адресная этикетка."""
    from .pdf import build_delivery_note_pdf

    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items"), pk=pk
    )
    from django.utils import translation

    from apps.core.documents import document_language

    # I18N-7b: накладная едет с посылкой к клиенту — язык ссылкой `?lang=`.
    with translation.override(document_language(request)):
        pdf = build_delivery_note_pdf(order, request.tenant)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="Lieferschein-{order.reference_code}.pdf"'
    return resp


def _eur_to_cents(raw) -> int:
    try:
        return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


def _parse_pickup_locations(request) -> list[dict]:
    """Текст «Name | Adresse» построчно → [{name,address}] (только с name, до 10)."""
    out = []
    for line in (request.POST.get("pickup_locations", "") or "").splitlines():
        if not line.strip():
            continue
        name, _, address = line.partition("|")
        if name.strip():
            out.append({"name": name.strip()[:120], "address": address.strip()[:200]})
        if len(out) >= 10:
            break
    return out


ZONE_ROWS = 6  # A2a: число строк-зон в форме доставки


def _parse_delivery_zones(request) -> list[dict]:
    """Собрать delivery_zones из строк формы (только непустые PLZ)."""
    zones = []
    for i in range(ZONE_ROWS):
        plz = request.POST.get(f"zone_plz_{i}", "").strip()[:120]
        if not plz:
            continue
        zones.append(
            {
                "plz": plz,
                "fee_cents": _eur_to_cents(request.POST.get(f"zone_fee_{i}")),
                "free_cents": _eur_to_cents(request.POST.get(f"zone_free_{i}")),
                "min_cents": _eur_to_cents(request.POST.get(f"zone_min_{i}")),
            }
        )
    return zones


def _zone_rows(tenant) -> list[dict]:
    """ZONE_ROWS строк для формы: существующие зоны (в €) + пустые добивки."""
    zones = list(getattr(tenant, "delivery_zones", None) or [])
    rows = []
    for i in range(ZONE_ROWS):
        z = zones[i] if i < len(zones) else None
        rows.append(
            {
                "i": i,
                "plz": z.get("plz", "") if z else "",
                "fee_eur": f"{(z.get('fee_cents') or 0) / 100:.2f}" if z else "",
                "free_eur": f"{(z.get('free_cents') or 0) / 100:.2f}" if z else "",
                "min_eur": f"{(z.get('min_cents') or 0) / 100:.2f}" if z else "",
            }
        )
    return rows


def save_delivery(tenant, request) -> None:
    """W4-3: сохранить настройки доставки/Abholung (Versand + зоны + pickup). Извлечено
    из order_settings без изменения семантики — переиспользуется единым экраном
    «Zahlung & Versand» (core.payment_settings)."""
    tenant.delivery_enabled = bool(request.POST.get("delivery_enabled"))
    tenant.delivery_fee_cents = _eur_to_cents(request.POST.get("delivery_fee_eur"))
    tenant.delivery_free_cents = _eur_to_cents(request.POST.get("delivery_free_eur"))
    tenant.delivery_min_cents = _eur_to_cents(request.POST.get("delivery_min_eur"))
    tenant.delivery_area = request.POST.get("delivery_area", "").strip()[:2000]
    tenant.pickup_min_cents = _eur_to_cents(request.POST.get("pickup_min_eur"))
    tenant.delivery_restrict_to_zones = bool(request.POST.get("delivery_restrict_to_zones"))
    tenant.delivery_zones = _parse_delivery_zones(request)
    tenant.pickup_locations = _parse_pickup_locations(request)
    tenant.save(
        update_fields=[
            "delivery_enabled",
            "delivery_fee_cents",
            "delivery_free_cents",
            "delivery_min_cents",
            "delivery_area",
            "pickup_min_cents",
            "delivery_restrict_to_zones",
            "delivery_zones",
            "pickup_locations",
            "updated_at",
        ]
    )


def save_vorkasse(tenant, request) -> None:
    """W4-3: сохранить Vorkasse/Überweisung + банковские реквизиты. IBAN нормализуем
    (без пробелов, верхний регистр); включение без IBAN не активирует способ на витрине
    (guard в orders.payments.available_methods). Извлечено из order_settings 1:1."""
    tenant.vorkasse_enabled = bool(request.POST.get("vorkasse_enabled"))
    tenant.bank_holder = request.POST.get("bank_holder", "").strip()[:120]
    tenant.bank_iban = request.POST.get("bank_iban", "").replace(" ", "").upper()[:34]
    tenant.bank_bic = request.POST.get("bank_bic", "").replace(" ", "").upper()[:11]
    tenant.save(
        update_fields=["vorkasse_enabled", "bank_holder", "bank_iban", "bank_bic", "updated_at"]
    )


def save_prepay(tenant, request) -> None:
    """W4-3: сохранить онлайн-предоплату Click&Collect (P2.5c). Извлечено 1:1."""
    tenant.orders_prepay = bool(request.POST.get("orders_prepay"))
    tenant.save(update_fields=["orders_prepay", "updated_at"])


def _order_sections(request, order):
    """DF-1c: «Документы» — при активном Finanzen (счёт) или доставке
    (Lieferschein). Иначе секция была бы пустой рамкой (найдено стендом)."""
    tenant = getattr(request, "tenant", None)
    try:
        finance = bool(tenant and tenant.is_module_active("finance"))
    except Exception:  # noqa: BLE001 — гейт fail-closed
        finance = False
    has_docs = finance or bool(getattr(order, "is_delivery", False))
    return (
        ("items", "discount", "totals", "payment")
        + (("documents",) if has_docs else ())
        + ("thread",)
    )
