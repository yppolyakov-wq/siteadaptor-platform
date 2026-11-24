"""Письма по заказам Click & Collect (Track D / D2b) — через apps.notifications.

Та же механика, что у броней (apps.promotions.notifications): рендер в схеме
арендатора, БД-дедуп по dedupe_key `order:{id}:{event}:{role}`, доставка после
коммита. Хелперы рендера/доменов переиспользуем из promotions.notifications.
"""

import logging

from django.db import connection
from django.urls import reverse

from apps.notifications.prefs import channel_enabled
from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

logger = logging.getLogger(__name__)

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


def _owner_answers(order) -> list:
    """FB-33 M2i-34: строки снимка ответов (`form_answers.rows`) — те же, что у карточки и KDS."""
    from apps.core import form_answers

    return form_answers.rows(getattr(order, "custom_answers", None))


def customer_event(order, event: str) -> str:
    """Событие письма клиенту с подменой шаблона: у Anprobe-резерва created/cancelled — свои
    (юр-риск: обычные письма говорят языком Kaufvertrag/Widerruf), у заказа-запроса (MEN-9)
    — своё письмо о создании. Подмена идемпотентна: подменённое событие не меняется."""
    if getattr(order, "is_anprobe", False) and event in ("created", "cancelled"):
        return f"anprobe_{event}"
    if getattr(order, "is_quote", False) and event == "created":
        return "quote_created"
    return event


def customer_dedupe_key(order, event: str, suffix: str = "") -> str:
    """FB-33 D3: ключ дедупа письма клиенту — один на постановку и на проверку «уже ушло»."""
    return f"order:{order.id}:{customer_event(order, event)}:customer{suffix}"


def missing_customer_mails(order, events) -> list[str]:
    """FB-33 D3: из `events` — те, чьего письма клиенту ещё нет (один запрос к `Notification`).

    Письма нет и тогда, когда его не может быть (канал выключен, отписка, адреса нет):
    такое событие вернётся снова, и `enqueue_order_email` сама решит, что не слать."""
    from apps.notifications.models import Notification

    keys = {event: customer_dedupe_key(order, event) for event in events}
    sent = set(
        Notification.objects.filter(dedupe_key__in=list(keys.values())).values_list(
            "dedupe_key", flat=True
        )
    )
    return [event for event in events if keys[event] not in sent]


def enqueue_order_email(order, event, dedupe_suffix=""):
    """Создать Notification(ы) события заказа (БД-дедуп) и поставить доставку.

    VF-3: `dedupe_suffix` — для РУЧНЫХ отправок (Zahlungslink с карточки):
    фиксированный ключ глотал бы повторную отправку навсегда (прецедент
    Mahnwesen — ключ с датой)."""
    # M3 / MEN-9: у Anprobe-резерва и заказа-запроса свои шаблоны (`customer_event`).
    event = customer_event(order, event)
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
    if template_base and not (customer.email and not customer.unsubscribed and email_on):
        # FB-33 M2i-7 (ревью): письмо клиенту не ушло — причина в лог, без адреса (PII)
        reason = (
            "no_email"
            if not customer.email
            else "unsubscribed"
            if customer.unsubscribed
            else "channel_off"
        )
        logger.info("order %s: customer mail %s skipped (%s)", order.pk, event, reason)
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
            from apps.reviews import links as review_links

            # KAT-3: SEO-URL детали (select_related — без N+1 по товару/категории).
            ctx["review_links"] = (
                [
                    {
                        "title": item.title_snapshot,
                        # SEC-E-M5: ссылка с токеном — право на проверенный отзыв.
                        "url": review_links.with_token(
                            f"{base}{reverse('storefront-product-review', args=[item.product_id])}",
                            "product",
                            item.product_id,
                            customer,
                        ),
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
            dedupe_key=customer_dedupe_key(order, event, dedupe_suffix),
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
        # FB-33 M2i-34: ответы на свои вопросы оформления — только владельцу (клиенту — нет)
        ctx = {**ctx, "custom_answers": _owner_answers(order)}
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
