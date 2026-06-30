"""Публичная заявка + Angebot на витрине (G6 / F3).

`/anfrage/` — форма заявки (honeypot + rate-limit) → Job(new) + письмо владельцу.
`/angebot/<token>/` — публичная страница сметы: клиент принимает/отклоняет (без
аккаунта), что двигает FSM и уведомляет владельца. Гейтинг модуля → 404.
"""

import stripe
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.billing import connect
from apps.core import ratelimit

from . import payments, services
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
        site_plz = request.POST.get("site_plz", "").strip()
        job = services.create_job(
            title=title,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            description=request.POST.get("description", "").strip(),
            site_address=request.POST.get("site_address", "").strip(),
            site_plz=site_plz,  # A7: PLZ объекта (Einzugsgebiet)
            source_channel=(request.GET.get("ch") or "")[:50],
            vehicle=request.POST.get("vehicle", "").strip(),
            # A9: структурные данные авто (только если включён режим Kfz-Werkstatt).
            vehicle_plate=request.POST.get("vehicle_plate", "").strip(),
            vehicle_hsn=request.POST.get("vehicle_hsn", "").strip(),
            vehicle_tsn=request.POST.get("vehicle_tsn", "").strip(),
        )
        services.add_job_photos(job, request.FILES.getlist("photos"))  # A7b
        enqueue_job_email(job, "new")  # владельцу — новый лид
        # A7: мягкий чек зоны — заявку принимаем всегда, но если PLZ вне списка зоны,
        # сообщаем клиенту (управление ожиданиями), не блокируя.
        if site_plz and not request.tenant.serves_plz(site_plz):
            messages.info(
                request,
                _(
                    "Your postal code is outside our usual service area — "
                    "we'll still review your request and get back to you."
                ),
            )
        messages.success(
            request, _("Thank you! Your request has arrived — we'll get back to you soon.")
        )
        return redirect("storefront-anfrage")
    # R6: префилл темы из ?betreff (групповой/корп-запрос со страницы ретрита).
    from apps.tenants import siteconfig

    jobs_vehicle = siteconfig.normalize(request.tenant.site_config).get("jobs_vehicle", False)
    autorepair_ld = ""
    if jobs_vehicle:
        from apps.core.seo import localbusiness_ld

        autorepair_ld = localbusiness_ld(
            request.tenant,
            url=request.build_absolute_uri(reverse("storefront-anfrage")),
            schema_type="AutoRepair",
        )
    return render(
        request,
        "storefront/anfrage.html",
        {
            "betreff": (request.GET.get("betreff") or "")[:200],
            "jobs_vehicle": jobs_vehicle,  # A9: структурные поля авто
            "autorepair_ld": autorepair_ld,  # A9: schema.org AutoRepair (SEO)
            # A7: зона обслуживания — баннер + поле PLZ (показываем, если задана).
            "has_service_area": request.tenant.has_service_area,
            "service_area_note": request.tenant.service_area_note,
            "service_area_plz_list": request.tenant.service_area_plz_list,
        },
    )


def rueckruf(request):
    """A7: быстрый запрос обратного звонка (Rückruf-Anfrage). POST-only — лёгкий лид
    (имя + телефон + опц. удобное время) через тот же jobs-пайплайн, что и Anfrage.

    Альтернатива полной заявке для тех, кто хочет «просто перезвоните мне» — низкий
    порог, типичная конверсия Handwerker. Honeypot + rate-limit как у Anfrage."""
    _require_jobs_active(request)
    if request.method != "POST" or request.POST.get("website"):  # POST + honeypot
        return redirect("storefront-anfrage")
    if ratelimit.hit("rueckruf", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)
    name = request.POST.get("name", "").strip()
    phone = request.POST.get("phone", "").strip()
    if not (name and phone):
        messages.error(request, _("Please leave your name and phone number."))
        return redirect("storefront-anfrage")
    best_time = request.POST.get("best_time", "").strip()
    desc = _("Callback requested.")
    if best_time:
        desc += " " + _("Preferred time: %(t)s") % {"t": best_time[:100]}
    job = services.create_job(
        title="Rückrufbitte",
        name=name,
        phone=phone,
        email=request.POST.get("email", "").strip(),
        description=desc,
        source_channel=(request.GET.get("ch") or "")[:50],
    )
    enqueue_job_email(job, "new")  # владельцу — новый лид (как Anfrage)
    messages.success(request, _("Thank you! We'll call you back shortly."))
    return redirect("storefront-anfrage")


# A9: порядок «публичных» стадий ремонта для тайм-лайна (declined/cancelled — терминально).
_STATUS_FLOW = (
    Job.STATUS_NEW,
    Job.STATUS_QUOTED,
    Job.STATUS_ACCEPTED,
    Job.STATUS_DONE,
    Job.STATUS_INVOICED,
)


def auftrag_status(request, token):
    """A9: публичная страница статуса заявки (Repair-Status) по public_token.

    Read-only тайм-лайн стадий (Anfrage → Angebot → Beauftragt → Erledigt →
    Abgerechnet) с подсветкой текущей; declined/cancelled — терминальная пометка.
    Ссылка приходит клиенту в письме «Auftrag fertig». Гейт модулем jobs."""
    _require_jobs_active(request)
    job = get_object_or_404(Job.objects.select_related("customer"), public_token=token)
    labels = dict(Job.STATUSES)
    terminal = job.status in (Job.STATUS_DECLINED, Job.STATUS_CANCELLED)
    try:
        cur = _STATUS_FLOW.index(job.status)
    except ValueError:
        cur = -1  # терминальный статус — ни одна стадия не «текущая»
    steps = [
        {"label": labels.get(s, s), "done": i < cur, "current": i == cur}
        for i, s in enumerate(_STATUS_FLOW)
    ]
    return render(
        request,
        "storefront/auftrag_status.html",
        {
            "job": job,
            "steps": steps,
            "terminal": terminal,
            "status_label": labels.get(job.status, job.status),
        },
    )


def angebot(request, token):
    _require_jobs_active(request)
    job = get_object_or_404(Job.objects.select_related("customer"), public_token=token)
    if request.method == "POST" and job.status == Job.STATUS_QUOTED:
        action = request.POST.get("action", "")
        # A7c: принятие сметы с Anzahlung — через Stripe Checkout (на счёт бизнеса).
        # Оплата = принятие (вебхук job_deposit → quoted→accepted). Без депозита/
        # оплаты — принимаем сразу, как раньше.
        tenant = getattr(request, "tenant", None)
        if (
            action == "accept"
            and job.deposit_cents > 0
            and getattr(tenant, "payments_enabled", False)
            and connect.is_connect_configured()
        ):
            if job.payment_state != Job.PAYMENT_PAID:
                job.payment_state = Job.PAYMENT_UNPAID
                job.save(update_fields=["payment_state", "updated_at"])
            ok_url = (
                request.build_absolute_uri(reverse("storefront-angebot", args=[token])) + "?paid=1"
            )
            cancel_url = request.build_absolute_uri(reverse("storefront-angebot", args=[token]))
            try:
                return redirect(
                    payments.deposit_checkout_url(
                        job, tenant, success_url=ok_url, cancel_url=cancel_url
                    )
                )
            except stripe.error.StripeError:
                messages.error(request, _("Payment could not be started — please try again."))
                return redirect("storefront-angebot", token=token)
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
        {
            "job": job,
            "lines": list(job.lines.all()),
            "deposit_eur": f"{job.deposit_cents / 100:.2f}".replace(".", ","),
        },
    )
