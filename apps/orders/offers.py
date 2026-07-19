"""LS-3 «Sofort-Angebot»: персональное предложение из чата → оплата в 1 клик.

План — docs/ls3-sofort-angebot-plan-2026-07-19.md. Предложение (Offer) живёт
отдельно от заказа; принятие конвертирует его в обычный Order через
create_order(custom_lines=...) — оплата/канбан/статусы дальше СТРОГО
существующими путями orders (второго чекаута нет). jobs (смета Handwerker) не
затронут. Смена статусов — только OfferSM.apply() (конвенция FSM).
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.notifications.prefs import channel_enabled
from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

from .models import Offer, OfferLine
from .services import create_order
from .state_machine import OfferSM


class OfferUnavailable(Exception):
    """Принятие/отклонение невозможно: не open или истёк срок действия."""


def offer_url(offer) -> str:
    """Абсолютная ссылка на публичную страницу /o/<token>/ (пусто без домена —
    паттерн jobs: письмо уходит без ссылки, не падает)."""
    base = _base_url(connection.schema_name)
    return f"{base}{reverse('storefront-offer', args=[offer.token])}" if base else ""


def _clean_lines(lines) -> list[dict]:
    """Отфильтровать строки композера: без названия или с кривой ценой — мимо."""
    out = []
    for line in lines or []:
        title = str(line.get("title") or "").strip()
        if not title:
            continue
        try:
            unit_price = Decimal(str(line.get("unit_price", "0")).replace(",", "."))
        except (InvalidOperation, ValueError):
            continue
        if unit_price < 0:
            continue
        try:
            qty = max(1, int(line.get("qty") or 1))
        except (TypeError, ValueError):
            qty = 1
        ref_id = line.get("ref_id")
        out.append(
            {
                "kind": str(line.get("kind") or "")[:10],
                "ref_id": str(ref_id)[:64] if ref_id else "",
                "title": title[:200],
                "unit_price": unit_price,
                "qty": qty,
            }
        )
    return out


@transaction.atomic
def send_offer(conversation, *, lines, valid_until=None, note="", author=None):
    """Создать предложение из треда: Offer+строки, system-сообщение в ленту,
    письмо клиенту с прямой ссылкой. lines — [{kind, ref_id, title, unit_price,
    qty}]; пустые/кривые строки отбрасываются, совсем без строк — ValueError."""
    clean = _clean_lines(lines)
    if not clean:
        raise ValueError("offer needs at least one line")
    customer = conversation.customer if conversation is not None else None
    offer = Offer.objects.create(
        conversation=conversation,
        customer=customer,
        customer_name=(customer.name if customer else "")[:200],
        customer_email=(customer.email if customer else ""),
        note=(note or "").strip(),
        valid_until=valid_until,
    )
    for i, line in enumerate(clean):
        OfferLine.objects.create(offer=offer, position=i, **line)

    if conversation is not None:
        _post_system_message(
            conversation,
            f"📄 Angebot über {offer.total} {offer.currency} gesendet"
            + (f" (gültig bis {valid_until.strftime('%d.%m.%Y')})" if valid_until else ""),
        )
    enqueue_offer_email(offer, "sent")
    return offer


@transaction.atomic
def accept_offer(offer, *, name="", email="", phone="", payment_method=""):
    """Принять предложение → обычный Order (custom_lines, цены заморожены).

    Идемпотентно: уже принятое возвращает существующий заказ (повторный POST не
    плодит второй). Строки kind=product с живым активным товаром получают FK →
    сток списывается по обычным правилам (anti-oversell/леджер); прочее —
    свободные строки. OutOfStock из create_order пробрасывается (откат, статус
    offer не тронут)."""
    from apps.catalog.models import Product

    offer = Offer.objects.select_for_update().get(pk=offer.pk)
    if offer.status == Offer.STATUS_ACCEPTED and offer.order_id:
        return offer.order
    if offer.status != Offer.STATUS_OPEN or offer.is_expired:
        raise OfferUnavailable()

    custom_lines = []
    for line in offer.lines.all():
        product = None
        if line.kind == "product" and line.ref_id:
            try:
                product = Product.objects.filter(pk=line.ref_id, is_active=True).first()
            except (ValueError, ValidationError):
                product = None  # кривой ref (не-UUID) → свободная строка
        custom_lines.append((line.title, line.unit_price, line.qty, product))
    order = create_order(
        items=(),
        custom_lines=custom_lines,
        name=(name or offer.customer_name or "").strip(),
        email=(email or offer.customer_email or "").strip(),
        phone=(phone or "").strip(),
        note=f"Angebot {str(offer.token)[:8]}",
        source_channel="offer",
        payment_method=payment_method,
    )
    OfferSM().apply(offer, Offer.STATUS_ACCEPTED)
    offer.order = order
    offer.accepted_at = timezone.now()
    offer.save(update_fields=["order", "accepted_at", "updated_at"])

    conversation = offer.conversation
    if conversation is not None:
        # Тред ↔ заказ: мягкий ref (шов inbox) + отметка в ленте.
        conversation.ref_kind = "order"
        conversation.ref_id = str(order.pk)
        conversation.ref_label = order.reference_code
        conversation.save(update_fields=["ref_kind", "ref_id", "ref_label", "updated_at"])
        _post_system_message(
            conversation, f"✅ Angebot angenommen — Bestellung {order.reference_code}"
        )
    return order


@transaction.atomic
def decline_offer(offer):
    """Отклонить (клиент). Идемпотентно: не-open → no-op."""
    offer = Offer.objects.select_for_update().get(pk=offer.pk)
    if offer.status != Offer.STATUS_OPEN:
        return offer
    OfferSM().apply(offer, Offer.STATUS_DECLINED)
    offer.declined_at = timezone.now()
    offer.save(update_fields=["declined_at", "updated_at"])
    if offer.conversation is not None:
        _post_system_message(offer.conversation, "❌ Angebot abgelehnt")
    return offer


@transaction.atomic
def cancel_offer(offer):
    """Отозвать (владелец, кнопка в треде). Идемпотентно: не-open → no-op."""
    offer = Offer.objects.select_for_update().get(pk=offer.pk)
    if offer.status != Offer.STATUS_OPEN:
        return offer
    OfferSM().apply(offer, Offer.STATUS_CANCELLED)
    if offer.conversation is not None:
        _post_system_message(offer.conversation, "Angebot zurückgezogen")
    return offer


def _post_system_message(conversation, body):
    """System-сообщение в ленту треда: без письма (enqueue_message_email шлёт
    только staff/customer-роли) — письмо о предложении идёт отдельным шаблоном."""
    from apps.inbox.models import Message
    from apps.inbox.services import post_message

    post_message(conversation, body=body, author_role=Message.AUTHOR_SYSTEM)


def enqueue_offer_email(offer, event):
    """event: sent → клиенту (прямая ссылка на /o/<token>/); accepted/declined →
    владельцу. Рендер в локали тенанта (L4), БД-дедуп offer:{id}:{event}."""
    tenant = _tenant(connection.schema_name)
    ctx = {
        "offer": offer,
        "offer_url": offer_url(offer) if event == "sent" else "",
        "business": tenant.name if tenant else "",
        "order": offer.order,
    }
    if event == "sent":
        email_on = channel_enabled(tenant, "customer", "offer", event, "email")
        if offer.customer_email and email_on:
            subject, body, html = _render("offer_sent", ctx)
            notify(
                dedupe_key=f"offer:{offer.id}:sent:customer",
                type="offer_sent",
                recipient=offer.customer_email,
                subject=subject,
                body=body,
                html=html,
            )
        return
    owner = _owner_email(tenant)
    if owner and channel_enabled(tenant, "owner", "offer", event, "email"):
        subject, body, html = _render(f"offer_{event}", ctx)
        notify(
            dedupe_key=f"offer:{offer.id}:{event}:owner",
            type=f"offer_{event}",
            recipient=owner,
            subject=subject,
            body=body,
            html=html,
        )
