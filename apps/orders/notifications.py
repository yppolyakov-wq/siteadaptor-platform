"""Письма по заказам Click & Collect (Track D / D2b) — через apps.notifications.

Та же механика, что у броней (apps.promotions.notifications): рендер в схеме
арендатора, БД-дедуп по dedupe_key `order:{id}:{event}:{role}`, доставка после
коммита. Хелперы рендера/доменов переиспользуем из promotions.notifications.
"""

from django.db import connection
from django.urls import reverse

from apps.notifications.prefs import channel_enabled
from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

# событие -> базовое имя шаблона письма клиенту
_CUSTOMER_TEMPLATES = {
    "created": "order_created",
    "confirmed": "order_confirmed",
    "ready": "order_ready",
    "picked_up": "order_picked_up",
    "shipped": "order_shipped",  # G4: versandt (с трек-номером)
    "cancelled": "order_cancelled",
    "returned": "order_returned",  # A2c: возврат/Widerruf
    "post_purchase": "order_post_purchase",  # CM-6.4: danke + запрос отзыва о товарах
    "payment_reminder": "order_payment_reminder",  # B2.1: незавершённая Stripe-оплата
    # VF-3 (2026-08-24): ручная отправка ссылки на оплату с карточки заказа.
    "payment_link": "order_payment_link",
    # M3 Boutique: Anprobe-резерв — свои тексты (unverbindliche Reservierung,
    # KEIN Kaufvertrag; Kauf erst im Geschäft) вместо языка договора купли-продажи.
    "anprobe_created": "order_anprobe_created",
    "anprobe_cancelled": "order_anprobe_cancelled",
    # MEN-9: заказ-запрос на просчёт (кейтеринг) — «Anfrage eingegangen, wir
    # melden uns mit einem Angebot» вместо языка договора купли-продажи.
    "quote_created": "order_quote_created",
}


def enqueue_order_email(order, event, dedupe_suffix=""):
    """Создать Notification(ы) события заказа (БД-дедуп) и поставить доставку.

    VF-3: `dedupe_suffix` — для РУЧНЫХ отправок (Zahlungslink с карточки):
    фиксированный ключ глотал бы повторную отправку навсегда (прецедент
    Mahnwesen — ключ с датой)."""
    # M3: у Anprobe-резервов created/cancelled ремапятся на свои шаблоны (юр-риск:
    # обычные письма говорят языком Kaufvertrag/Widerruf). Остальные события —
    # штатные (confirmed/ready уместны и для резерва).
    if getattr(order, "is_anprobe", False) and event in ("created", "cancelled"):
        event = f"anprobe_{event}"
    # MEN-9: у заказа-запроса своё письмо о создании (без Kaufvertrag/Widerruf).
    elif getattr(order, "is_quote", False) and event == "created":
        event = "quote_created"
    schema = connection.schema_name
    customer = order.customer
    tenant = _tenant(schema)
    ctx = {
        "order": order,
        "customer": customer,
        "items": list(order.items.all()),
        # E7-2: банковские реквизиты бизнеса — для Vorkasse-блока в письме
        # (Verwendungszweck = reference_code, без PII).
        "bank_holder": getattr(tenant, "bank_holder", ""),
        "bank_iban": getattr(tenant, "bank_iban", ""),
        "bank_bic": getattr(tenant, "bank_bic", ""),
    }

    template_base = _CUSTOMER_TEMPLATES.get(event)
    email_on = channel_enabled(tenant, "customer", "order", event, "email")
    if template_base and customer.email and not customer.unsubscribed and email_on:
        base = _base_url(schema)
        # LS-6 «Прямая линия»: ссылка «Etwas stimmt nicht?» в подтверждении —
        # доверенный problem-гейт contact (high-тред + пуш владельцу).
        if event in ("confirmed", "post_purchase"):
            ctx["problem_url"] = (
                f"{base}{reverse('storefront-message')}?problem=1&ref_kind=order&ref_id={order.reference_code}"
                if base
                else ""
            )
        # B2.1: ссылка на подтверждение (там кнопка «Jetzt bezahlen»).
        if event == "payment_reminder":
            ctx["order_url"] = (
                f"{base}{reverse('storefront-order', args=[order.reference_code])}" if base else ""
            )
        # VF-3: прямая ссылка оплаты — /bezahlen/ сам уводит в Stripe Checkout
        # (оплаченный заказ страница честно вернёт на подтверждение).
        if event == "payment_link":
            ctx["pay_url"] = (
                f"{base}{reverse('storefront-order-pay', args=[order.reference_code])}"
                if base
                else ""
            )
        # CM-6.4: ссылки «оценить товар» (деталь#bewertungen) — только с base.
        if event == "post_purchase":
            # KAT-3: SEO-URL детали (select_related — без N+1 по товару/категории).
            ctx["review_links"] = (
                [
                    {
                        "title": item.title_snapshot,
                        "url": f"{base}{item.product.get_absolute_url()}#bewertungen",
                    }
                    for item in order.items.select_related("product__category")
                    if item.product_id
                ][:5]
                if base
                else []
            )
        unsub = (
            f"{base}{reverse('storefront-unsubscribe', args=[customer.unsubscribe_token])}"
            if base
            else ""
        )
        subject, body, html = _render(template_base, {**ctx, "unsubscribe_url": unsub})
        headers = None
        if unsub:
            headers = {
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        notify(
            dedupe_key=f"order:{order.id}:{event}:customer{dedupe_suffix}",
            type=f"order_{event}",
            recipient=customer.email,
            subject=subject,
            body=body,
            html=html,
            headers=headers,
        )

    # TG3: то же событие — в Telegram, если клиент привязал бота (дополняет email).
    if (
        template_base
        and customer
        and channel_enabled(tenant, "customer", "order", event, "telegram")
    ):
        from apps.telegram.notify import send_to_customer

        subject_tg, body_tg, _html = _render(template_base, {**ctx, "unsubscribe_url": ""})
        send_to_customer(
            customer,
            type=f"order_{event}",
            dedupe_key=f"order:{order.id}:{event}:tg",
            text=subject_tg or body_tg,
        )

    # владельцу — только при новом заказе (email + UD4c Telegram-пуш).
    # Ревью M3 (HIGH): ремап anprobe_created ломал эту ветку — владелец НЕ узнавал
    # о резерве, хотя клиенту обещано «wir legen es zurück». Событие prefs-матрицы
    # остаётся "created" (UD4-2 знает только его), шаблон — свой для резерва.
    if event in ("created", "anprobe_created"):
        owner = _owner_email(tenant)
        owner_tpl = "order_anprobe_owner" if event == "anprobe_created" else "order_owner"
        if owner and channel_enabled(tenant, "owner", "order", "created", "email"):
            subject, body, html = _render(owner_tpl, {**ctx, "unsubscribe_url": ""})
            notify(
                dedupe_key=f"order:{order.id}:created:owner",
                type="order_created_owner",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )
        if channel_enabled(tenant, "owner", "order", "created", "telegram"):
            from apps.telegram.notify import send_to_owner

            subj_o, body_o, _h = _render(owner_tpl, {**ctx, "unsubscribe_url": ""})
            send_to_owner(
                tenant,
                type="order_created_owner",
                dedupe_key=f"order:{order.id}:created:owner:tg",
                text=subj_o or body_o,
            )
