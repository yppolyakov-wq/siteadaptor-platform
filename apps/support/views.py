"""Кабинет «Hilfe» владельца (M22c): /dashboard/help/ — тикеты к SiteAdaptor.

Данные SHARED (SupportThread/Message в public), привязка к request.tenant. Часть
core-модуля settings (всегда доступно). Платформа отвечает из unfold-админки.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from . import services
from .models import SupportMessage, SupportThread


@login_required
def help_list(request):
    tenant = request.tenant
    if request.method == "POST":
        subject = request.POST.get("subject", "").strip()
        body = request.POST.get("body", "").strip()
        if subject and body:
            thread = services.open_thread(tenant=tenant, subject=subject, body=body[:5000])
            messages.success(request, _("Your request was sent to support."))
            return redirect("support:thread", pk=thread.pk)
        messages.error(request, _("Please enter a subject and a message."))
        return redirect("support:help")
    return render(
        request,
        "support/help_list.html",
        {"nav": "support", "threads": SupportThread.objects.filter(tenant=tenant)[:100]},
    )


@login_required
def help_thread(request, pk):
    thread = get_object_or_404(SupportThread, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            services.add_message(thread, body=body[:5000], author_role=SupportMessage.AUTHOR_OWNER)
            messages.success(request, _("Message sent."))
        return redirect("support:thread", pk=thread.pk)
    if thread.unread_for_owner:
        thread.unread_for_owner = False
        thread.save(update_fields=["unread_for_owner", "updated_at"])
    return render(
        request,
        "support/help_thread.html",
        {"nav": "support", "thread": thread, "messages_list": thread.messages.all()},
    )
