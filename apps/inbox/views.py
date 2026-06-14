"""Кабинет-inbox (M22a): /dashboard/inbox/ — список тредов + тред с ответом.

Владелец/сотрудник видит обращения клиентов, отвечает, меняет статус (FSM),
приоритет и назначение. Доставка писем клиенту — M22b. Гейтинг — модуль «inbox».
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.core.fsm import IllegalTransition

from . import services
from .models import Conversation, Message
from .state_machine import ConversationSM


@login_required
def inbox_list(request):
    conversations = Conversation.objects.select_related("customer")
    status = request.GET.get("status", "")
    if status in dict(Conversation.STATUSES):
        conversations = conversations.filter(status=status)
    return render(
        request,
        "inbox/list.html",
        {
            "nav": "inbox",
            "conversations": conversations[:200],
            "statuses": Conversation.STATUSES,
            "active_status": status,
            "open_count": Conversation.objects.filter(status=Conversation.STATUS_OPEN).count(),
        },
    )


@login_required
def thread(request, pk):
    conversation = get_object_or_404(Conversation.objects.select_related("customer"), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "reply":
            body = request.POST.get("body", "").strip()
            if body:
                services.post_message(
                    conversation,
                    body=body[:5000],
                    author_role=Message.AUTHOR_STAFF,
                    author_user=request.user,
                )
                messages.success(request, _("Reply sent."))
            else:
                messages.error(request, _("Please write a message."))
        elif action in dict(Conversation.STATUSES):
            try:
                ConversationSM().apply(conversation, action, actor=request.user)
                messages.success(request, _("Status updated."))
            except IllegalTransition:
                messages.error(request, _("This step is not possible in the current status."))
        elif action == "priority":
            priority = request.POST.get("priority", "")
            if priority in dict(Conversation.PRIORITIES):
                conversation.priority = priority
                conversation.save(update_fields=["priority", "updated_at"])
        return redirect("inbox:thread", pk=conversation.pk)

    # Открыли тред — для владельца прочитано.
    if conversation.unread_for_staff:
        conversation.unread_for_staff = False
        conversation.save(update_fields=["unread_for_staff", "updated_at"])
    return render(
        request,
        "inbox/thread.html",
        {
            "nav": "inbox",
            "conversation": conversation,
            "messages_list": conversation.messages.select_related("author_user"),
            "allowed": ConversationSM().allowed_targets(conversation.status),
            "priorities": Conversation.PRIORITIES,
        },
    )
