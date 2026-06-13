"""Публичная заявка + Angebot на витрине (G6 / F3).

`/anfrage/` — форма заявки (honeypot + rate-limit) → Job(new) + письмо владельцу.
`/angebot/<token>/` — публичная страница сметы: клиент принимает/отклоняет (без
аккаунта), что двигает FSM и уведомляет владельца. Гейтинг модуля → 404.
"""

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import ratelimit

from . import services
from .models import Job
from .notifications import enqueue_job_email
from .state_machine import JobSM

RL_LIMIT = 5
RL_WINDOW = 600


def _require_jobs_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("jobs"):
        raise Http404


def anfrage(request):
    _require_jobs_active(request)
    if request.method == "POST":
        if request.POST.get("website"):  # honeypot
            return redirect("storefront-anfrage")
        if ratelimit.hit("anfrage", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
            return HttpResponse(status=429)
        title = request.POST.get("title", "").strip()
        name = request.POST.get("name", "").strip()
        if not (title and name):
            messages.error(request, _("Please tell us your name and what you need."))
            return redirect("storefront-anfrage")
        job = services.create_job(
            title=title,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            description=request.POST.get("description", "").strip(),
            site_address=request.POST.get("site_address", "").strip(),
            source_channel=(request.GET.get("ch") or "")[:50],
        )
        enqueue_job_email(job, "new")  # владельцу — новый лид
        messages.success(
            request, _("Thank you! Your request has arrived — we'll get back to you soon.")
        )
        return redirect("storefront-anfrage")
    return render(request, "storefront/anfrage.html", {})


def angebot(request, token):
    _require_jobs_active(request)
    job = get_object_or_404(Job.objects.select_related("customer"), public_token=token)
    if request.method == "POST" and job.status == Job.STATUS_QUOTED:
        action = request.POST.get("action", "")
        if action in ("accept", "decline"):
            dst = Job.STATUS_ACCEPTED if action == "accept" else Job.STATUS_DECLINED
            JobSM().apply(job, dst)  # on_transition → письмо владельцу
            if dst == Job.STATUS_ACCEPTED:
                job.accepted_at = timezone.now()
                job.save(update_fields=["accepted_at", "updated_at"])
            messages.success(
                request,
                _("Thank you — your decision was recorded.")
                if dst == Job.STATUS_ACCEPTED
                else _("Thank you for letting us know."),
            )
        return redirect("storefront-angebot", token=token)
    return render(
        request,
        "storefront/angebot.html",
        {"job": job, "lines": list(job.lines.all())},
    )
