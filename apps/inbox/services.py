"""Сервисы inbox (M22a): создать тред, добавить сообщение.

Customer переиспользуется по email (как в orders/booking). Ответ клиента в
resolved-тред переоткрывает его (open) и помечает непрочитанным у владельца.
"""

from django.db import transaction
from django.utils import timezone

from apps.promotions.models import Customer

from .models import Conversation, Message


def _get_or_create_customer(*, name, email, phone=""):
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            return customer
    return Customer.objects.create(name=name or "", email=email, phone=phone)


def start_conversation(
    *,
    subject,
    body,
    name="",
    email="",
    phone="",
    customer=None,
    channel=Conversation.CHANNEL_WEB,
    ref_kind="",
    ref_id="",
    ref_label="",
    author_role=Message.AUTHOR_CUSTOMER,
    author_user=None,
    priority="",
):
    """Создать тред с первым сообщением. Customer — по email (если есть)."""
    with transaction.atomic():
        if customer is None and email:
            customer = _get_or_create_customer(name=name, email=email, phone=phone)
        conversation = Conversation.objects.create(
            customer=customer,
            subject=(subject or "").strip()[:200],
            channel=channel,
            ref_kind=(ref_kind or "")[:20],
            ref_id=str(ref_id or "")[:64],
            ref_label=(ref_label or "")[:200],
            # LS-6 «Прямая линия»: high выставляет ТОЛЬКО доверенный problem-гейт
            # (contact ?problem=1 + ref) или кабинет — не сырой публичный ввод.
            priority=(
                priority
                if priority in dict(Conversation.PRIORITIES)
                else Conversation.PRIORITY_NORMAL
            ),
        )
        post_message(
            conversation,
            body=body,
            author_role=author_role,
            author_user=author_user,
            channel=channel,
        )
    # LS-6: проблемный тред → НЕМЕДЛЕННЫЙ Telegram-пуш владельцу (канал UD4-2;
    # no-op без бота/линка; одна тревога на тред — dedupe по conversation).
    if conversation.priority == Conversation.PRIORITY_HIGH:
        _notify_owner_problem(conversation)
    return conversation


def _notify_owner_problem(conversation) -> None:
    """LS-6: пуш «⚠️ Problem» владельцу — fail-safe (сбой не роняет создание треда)."""
    try:
        from django.db import connection

        from apps.promotions.notifications import _tenant
        from apps.telegram.notify import send_to_owner

        tenant = _tenant(connection.schema_name)
        if tenant is None:
            return
        label = conversation.ref_label or conversation.subject or ""
        send_to_owner(
            tenant,
            type="inbox_problem",
            dedupe_key=f"inbox:conv:{conversation.pk}:problem:owner:tg",
            text=f"⚠️ Problem: {label}".strip(),
        )
    except Exception:  # noqa: BLE001 — тревога best-effort, тред уже создан
        pass


def post_message(
    conversation, *, body, author_role, author_user=None, channel=Conversation.CHANNEL_WEB
):
    """Добавить сообщение и обновить тред (last_message_at, непрочитанное, реопен)."""
    message = Message.objects.create(
        conversation=conversation,
        author_role=author_role,
        author_user=author_user,
        body=(body or "").strip(),
        channel=channel,
    )
    conversation.last_message_at = timezone.now()
    if author_role == Message.AUTHOR_CUSTOMER:
        conversation.unread_for_staff = True
        # клиент ответил в закрытый/решённый тред — снова открываем
        if conversation.status in (Conversation.STATUS_RESOLVED, Conversation.STATUS_CLOSED):
            conversation.status = Conversation.STATUS_OPEN
    else:  # ответ владельца — для клиента «pending» (ждём его), у владельца прочитано
        conversation.unread_for_staff = False
    conversation.save(update_fields=["last_message_at", "unread_for_staff", "status", "updated_at"])

    # Письмо второй стороне (M22b): клиенту на ответ владельца, владельцу на вопрос.
    from .notifications import enqueue_message_email

    enqueue_message_email(message)
    return message
