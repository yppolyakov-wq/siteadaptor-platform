"""Витрина событий (A6c): список → страница события → покупка билета → оплата.

Гейтится модулем events (иначе 404). Защита формы — honeypot + rate-limit по IP
(как бронь/stays). Платное событие при подключённой оплате → Stripe Checkout на
счёт бизнеса (Connect, вариант B); бесплатное — сразу подтверждено; платное без
оплаты онлайн — pending (оплата на месте / подтверждает владелец).
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
from apps.stays.services import StayUnavailable

from . import installments, payments, services
from .models import Event, Teacher, Ticket

RL_LIMIT = 5
RL_WINDOW = 600


def _require_events_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("events"):
        raise Http404


def veranstaltung_index(request):
    _require_events_active(request)
    base = list(
        Event.objects.filter(status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now())
        .prefetch_related("teachers")
        .order_by("starts_at")
    )
    facets = _event_facets(base)  # доступные значения фильтров (по факту наличия)
    selected = {
        "cat": (request.GET.get("cat") or "").strip(),
        "level": (request.GET.get("level") or "").strip(),
        "lang": (request.GET.get("lang") or "").strip(),
        "city": (request.GET.get("city") or "").strip(),
        "dur": (request.GET.get("dur") or "").strip(),
        "month": (request.GET.get("month") or "").strip(),
        "teacher": (request.GET.get("teacher") or "").strip(),
    }
    events = [e for e in base if _event_matches(e, selected)]
    active_filters = any(selected.values())
    # RV3: компактный отсчёт до старта (urgency-пилюля на карточке/гриде). Событие
    # «скоро» (≤14 дней) получает метку Heute/Morgen/In N Tagen — конверсионный сигнал.
    _today = timezone.localtime(timezone.now()).date()
    for e in events:
        _days = (timezone.localtime(e.starts_at).date() - _today).days
        e.starts_soon = 0 <= _days <= 14
        e.countdown_label = (
            _("Today")
            if _days <= 0
            else _("Tomorrow")
            if _days == 1
            else _("In %(n)d days") % {"n": _days}
        )
    # M20U-3: на маленькой витрине (≤ порога событий) фильтры — лишний шум.
    # Показываем панель фильтров, только если событий достаточно или фильтр уже
    # применён. Иначе — чистый список (анти-Битрикс простота).
    show_filters = len(base) > _FILTER_MIN_EVENTS or active_filters
    # M20U-7 (per-page): раскладка списка событий — список (дефолт) или сетка карточек.
    from apps.tenants import siteconfig

    # SE-2b-1: при ?preview=1 берём черновик из сессии (on-canvas правка раскладки).
    _raw = getattr(request.tenant, "site_config", {}) or {}
    if request.GET.get("preview") == "1" and isinstance(
        request.session.get("site_preview_draft"), dict
    ):
        _raw = request.session["site_preview_draft"]
    ev_layout = siteconfig.normalize(_raw)["events_index_layout"]
    events_is_list = ev_layout["preset"] == "list"
    events_grid = siteconfig.grid_class_string(ev_layout)
    return render(
        request,
        "storefront/event_index.html",
        {
            "events": events,
            "facets": facets,
            "f": selected,
            "active_filters": active_filters,
            "show_filters": show_filters,
            "total": len(base),
            "events_is_list": events_is_list,
            "events_grid": events_grid,
        },
    )


# Порог: панель фильтров каталога ретритов показываем только при > N событий.
_FILTER_MIN_EVENTS = 4


def _event_facets(events) -> dict:
    """Доступные значения фильтров по факту наличия среди событий (порядок каталога)."""
    from . import taxonomy

    present = {
        "cat": {e.category for e in events if e.category},
        "level": {e.level for e in events if e.level},
        "lang": {e.language for e in events if e.language},
        "dur": {e.duration_kind for e in events},
    }
    return {
        "cat": [(k, v) for k, v in taxonomy.CATEGORIES if k in present["cat"]],
        "level": [(k, v) for k, v in taxonomy.LEVELS if k in present["level"]],
        "lang": [(k, v) for k, v in taxonomy.LANGUAGES if k in present["lang"]],
        "dur": [(k, v) for k, v in taxonomy.DURATIONS if k in present["dur"]],
        "city": sorted({e.city for e in events if e.city}),
        "month": sorted({e.starts_at.strftime("%Y-%m") for e in events}),
        "teacher": _teacher_facet(events),
    }


def _teacher_facet(events) -> list:
    """[(pk, name)] преподавателей, встречающихся среди событий (по имени)."""
    seen = {}
    for e in events:
        for t in e.teachers.all():
            seen[str(t.pk)] = t.name
    return sorted(seen.items(), key=lambda kv: kv[1])


def _event_matches(event, f) -> bool:
    if f["cat"] and event.category != f["cat"]:
        return False
    if f["level"] and event.level != f["level"]:
        return False
    if f["lang"] and event.language != f["lang"]:
        return False
    if f["city"] and event.city.lower() != f["city"].lower():
        return False
    if f["dur"] and event.duration_kind != f["dur"]:
        return False
    if f["month"] and event.starts_at.strftime("%Y-%m") != f["month"]:
        return False
    if f["teacher"] and f["teacher"] not in {str(t.pk) for t in event.teachers.all()}:
        return False
    return True


_DE_MONTHS = [
    "",
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def veranstaltung_calendar(request):
    """R3b: годовой календарь ретритов — события, сгруппированные по месяцам."""
    _require_events_active(request)
    events = (
        Event.objects.filter(status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now())
        .prefetch_related("teachers")
        .order_by("starts_at")
    )
    groups, current = [], None
    for e in events:
        key = (e.starts_at.year, e.starts_at.month)
        if current is None or current["key"] != key:
            current = {"key": key, "label": f"{_DE_MONTHS[key[1]]} {key[0]}", "events": []}
            groups.append(current)
        current["events"].append(e)
    return render(request, "storefront/event_calendar.html", {"groups": groups})


def _ical_response(events, request, filename):
    from . import ical

    body = ical.render(
        events,
        url_for=lambda e: request.build_absolute_uri(reverse("storefront-event", args=[e.pk])),
        dtstamp=timezone.now(),
        host=request.get_host(),
    )
    resp = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


def veranstaltung_ical(request, pk):
    """R3b: .ics одного события («Zum Kalender hinzufügen»)."""
    _require_events_active(request)
    event = get_object_or_404(Event, pk=pk, status=Event.STATUS_PUBLISHED)
    return _ical_response([event], request, f"event-{pk}.ics")


def veranstaltung_ical_feed(request):
    """R3b: фид-подписка на все опубликованные будущие ретриты."""
    _require_events_active(request)
    events = Event.objects.filter(
        status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now()
    ).order_by("starts_at")
    return _ical_response(events, request, "retreats.ics")


def lehrer_index(request):
    """Витрина: список преподавателей/ведущих (R3). Гейтится модулем events."""
    _require_events_active(request)
    teachers = Teacher.objects.filter(is_active=True)
    return render(request, "storefront/lehrer_index.html", {"teachers": teachers})


def lehrer_detail(request, pk):
    """Витрина: страница преподавателя — био, соцсети, ближайшие ретриты (R3)."""
    _require_events_active(request)
    teacher = get_object_or_404(Teacher, pk=pk, is_active=True)
    return render(
        request,
        "storefront/lehrer_detail.html",
        {"teacher": teacher, "events": teacher.upcoming_events()},
    )


def _parse_agenda(program) -> list:
    """RV2: разобрать плоский `program` (список строк «<Tag/Zeit> — <Text>») в записи
    тайм-лайна {lead, body}. lead — ведущий маркер времени/дня до тире (если есть)."""
    agenda = []
    for raw in program or []:
        s = str(raw).strip()
        if not s:
            continue
        lead, body = "", s
        for sep in (" — ", " – ", " - "):
            if sep in s:
                lead, body = s.split(sep, 1)
                break
        agenda.append({"lead": lead.strip(), "body": body.strip()})
    return agenda


def veranstaltung_detail(request, pk):
    _require_events_active(request)
    event = get_object_or_404(Event, pk=pk, status=Event.STATUS_PUBLISHED)
    from apps.core import extras as extras_engine

    tenant = getattr(request, "tenant", None)
    # R6: координаты для карты — события, иначе фолбэк на гео тенанта.
    lat = event.latitude if event.latitude is not None else getattr(tenant, "latitude", None)
    lng = event.longitude if event.longitude is not None else getattr(tenant, "longitude", None)
    jobs_active = bool(tenant and tenant.is_module_active("jobs"))
    from apps.tenants import siteconfig

    ctx = {
        "event": event,
        "agenda": _parse_agenda(event.program),  # RV2: тайм-лайн программы
        "extras": extras_engine.active_for("events"),  # #7 доп-услуги
        "accommodation": services.accommodation_options(event),  # R5 типы номеров
        "jobs_active": jobs_active,  # R6 корп-запрос (Angebot)
        "map_embed": "",
        "map_link": "",
        "installment_offer": _installment_offer(event),  # R10 предпросмотр рассрочки
        # M20U-4: порядок/видимость тематических секций детальной.
        "event_detail_order": siteconfig.event_detail_order(
            getattr(tenant, "site_config", {}) or {}
        ),
    }
    if lat is not None and lng is not None and not event.is_online:  # R6 карта (RT2: не для онлайн)
        lat, lng = float(lat), float(lng)
        ctx["map_embed"] = (
            "https://www.openstreetmap.org/export/embed.html?bbox="
            f"{lng - 0.012}%2C{lat - 0.006}%2C{lng + 0.012}%2C{lat + 0.006}"
            f"&layer=mapnik&marker={lat}%2C{lng}"
        )
        ctx["map_link"] = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=15/{lat}/{lng}"
    return render(request, "storefront/event_detail.html", ctx)


def _installment_offer(event):
    """R10: предпросмотр рассрочки для витрины (по базовой цене места) или None.

    Репрезентативный график (1 место, from-цена) — для бейджа «in N Raten» и
    чекбокса на форме. Фактический график считается при брони по реальной сумме."""
    if not event.allow_installments:
        return None
    rep = event.from_price_cents
    today = timezone.localdate()
    start = event.starts_at.date()
    if not installments.installments_available(event, rep, today, start):
        return None
    sched = installments.build_schedule(event, rep, today, start)
    return {
        "count": len(sched),
        "first_eur": sched[0]["amount_cents"] / 100,
        "mode": event.installment_mode,
    }


def veranstaltung_memo(request, code):
    """R6: PDF «Teilnehmer-Memo» (памятка участника) по коду билета."""
    _require_events_active(request)
    ticket = get_object_or_404(
        Ticket.objects.select_related("event", "stay_booking__unit"), reference_code=code
    )
    from . import memo

    pdf = memo.build_memo_pdf(ticket, request.tenant)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="memo-{code}.pdf"'
    return resp


def veranstaltung_book(request, pk):
    _require_events_active(request)
    if request.method != "POST":
        return redirect("storefront-event", pk=pk)
    event = get_object_or_404(Event, pk=pk, status=Event.STATUS_PUBLISHED)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-event", pk=pk)
    if ratelimit.hit("event", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return redirect("storefront-event", pk=pk)
    try:
        qty = max(1, min(int(request.POST.get("quantity", "1")), 50))
    except (TypeError, ValueError):
        qty = 1
    answers = {
        q: request.POST.get(f"q{i}", "").strip() for i, q in enumerate(event.questions or [])
    }
    # R1: ответы на структурированные пресет-поля (страна/питание/опыт…).
    from . import registration

    answers.update(registration.collect(event.registration_fields, request.POST))
    # A6 ценовой тир: цена/решение об оплате — по выбранному тиру (иначе единой цене).
    tier_label = request.POST.get("tier", "").strip()
    resolved_price = event.price_for_tier(tier_label)
    pay_mode = (request.POST.get("pay_mode") or "").strip()  # R10: "installments" | ""
    from apps.core import extras as extras_engine

    extras_snap = extras_engine.snapshot(request.POST.getlist("extra"), "events")
    # R5: выбранный тип номера (проживание на даты ретрита) + его цена для решения
    # об оплате/авто-подтверждении (фактическая бронь — атомарно в book_ticket).
    stay_unit_id = (request.POST.get("stay_unit") or "").strip() or None
    acc_quote = services.accommodation_quote(event, stay_unit_id) if stay_unit_id else 0
    # R4: подарочный/промо-код — read-only оценка скидки для решения об оплате
    # (фактическое гашение — атомарно в book_ticket).
    voucher_code = (request.POST.get("voucher_code") or "").strip()
    gross = resolved_price * qty + extras_engine.total_cents(extras_snap) + acc_quote
    discount_quote = services.quote_voucher(voucher_code, gross) if voucher_code else 0
    # itog к оплате = брутто − скидка → auto-confirm при нулевом итоге.
    order_total = max(0, gross - discount_quote)

    try:
        ticket = services.book_ticket(
            event,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            quantity=qty,
            answers=answers,
            source_channel=(request.GET.get("ch") or "")[:50],
            auto_confirm=(order_total == 0),  # бесплатно (билет + Extras + номер − код) — сразу
            tier_label=tier_label,
            extras=extras_snap,
            stay_unit_id=stay_unit_id,
            voucher_code=voucher_code,
            # R8: подпись отказа от ответственности (если событие требует).
            waiver_signed_name=(request.POST.get("waiver_name") or "").strip(),
            health_confirmed=bool(request.POST.get("health_confirmed")),
            signed_ip=ratelimit.client_ip(request),
        )
    except services.SoldOut as exc:
        messages.error(
            request,
            _("Sorry, only %(n)s seats left.") % {"n": exc.available}
            if exc.available
            else _("Sorry, this event is sold out."),
        )
        return redirect("storefront-event", pk=pk)
    except StayUnavailable:
        messages.error(request, _("Sorry, the selected room is no longer available."))
        return redirect("storefront-event", pk=pk)
    except services.PromoInvalid:
        messages.error(request, _("This voucher code is not valid."))
        return redirect("storefront-event", pk=pk)
    except services.WaiverRequired:
        messages.error(request, _("Please sign the waiver to register."))
        return redirect("storefront-event", pk=pk)
    except (services.EventNotBookable, ValueError):
        messages.error(request, _("This event is not available."))
        return redirect("storefront-event", pk=pk)

    # Платный билет + подключённая оплата → Stripe Checkout (на счёт бизнеса).
    tenant = getattr(request, "tenant", None)
    payments_ready = getattr(tenant, "payments_enabled", False) and connect.is_connect_configured()
    # R10: рассрочка — гость выбрал «in Raten» и событие/сумма допускают → Checkout
    # первой доли (сохраняет мандат; остальные доли спишет beat).
    if (
        pay_mode == "installments"
        and payments_ready
        and installments.first_installment_cents(event, ticket.payable_cents) > 0
    ):
        ticket.payment_state = Ticket.PAYMENT_PENDING
        ticket.save(update_fields=["payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(
                reverse("storefront-ticket-ok", args=[ticket.reference_code])
            )
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(reverse("storefront-event", args=[event.pk]))
        try:
            return redirect(
                payments.installment_checkout_url(
                    ticket, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            pass  # рассрочка недоступна — билет остаётся pending
    if (
        ticket.amount_due_now_cents > 0  # R4: депозит или вся payable (после скидки кода)
        and payments_ready
    ):
        ticket.payment_state = Ticket.PAYMENT_PENDING
        ticket.save(update_fields=["payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(
                reverse("storefront-ticket-ok", args=[ticket.reference_code])
            )
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(reverse("storefront-event", args=[event.pk]))
        try:
            return redirect(
                payments.ticket_checkout_url(
                    ticket, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            pass  # оплата недоступна — билет остаётся (pending)
    return redirect("storefront-ticket-ok", code=ticket.reference_code)


def veranstaltung_waitlist(request, pk):
    """Записать в лист ожидания распроданного события (R1)."""
    _require_events_active(request)
    event = get_object_or_404(Event, pk=pk, status=Event.STATUS_PUBLISHED)
    if request.method != "POST" or request.POST.get("website"):  # honeypot
        return redirect("storefront-event", pk=pk)
    if ratelimit.hit(
        "event_waitlist",
        f"{ratelimit.client_ip(request)}:{pk}",
        limit=RL_LIMIT,
        window=RL_WINDOW,
    ):
        return HttpResponse(status=429)
    email = (request.POST.get("email") or "").strip()
    if not email:
        messages.error(request, _("Please enter a valid email."))
        return redirect("storefront-event", pk=pk)
    try:
        qty = max(1, min(int(request.POST.get("quantity", "1")), 50))
    except (TypeError, ValueError):
        qty = 1
    services.join_waitlist(
        event,
        name=(request.POST.get("name") or "").strip(),
        email=email,
        phone=(request.POST.get("phone") or "").strip(),
        party_size=qty,
    )
    messages.success(request, _("We'll let you know as soon as a spot opens up."))
    return redirect("storefront-event", pk=pk)


def veranstaltung_confirmation(request, code):
    _require_events_active(request)
    ticket = get_object_or_404(
        Ticket.objects.select_related("event", "customer"), reference_code=code
    )
    from apps.telegram.notify import deep_link

    return render(
        request,
        "storefront/event_confirmation.html",
        {
            "ticket": ticket,
            "event": ticket.event,
            "just_paid": request.GET.get("paid") == "1",
            "telegram_link": deep_link(ticket.customer),
            "cancel_state": services.cancellation_state(ticket),
            "cancel_url": cancel_url(ticket),
        },
    )


def blog_index(request):
    """RT4: публичный список опубликованных записей блога."""
    from .models import BlogPost

    posts = BlogPost.objects.filter(is_published=True)
    return render(request, "storefront/blog_index.html", {"posts": posts})


def blog_detail(request, slug):
    """RT4: публичная детальная страница записи блога."""
    from .models import BlogPost

    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    recent = BlogPost.objects.filter(is_published=True).exclude(pk=post.pk)[:4]
    return render(request, "storefront/blog_detail.html", {"post": post, "recent": recent})


def ticket_qr(request, code):
    """RT1: персональный QR билета. Кодирует ссылку Check-in в кабинете —
    организатор сканирует штатной камерой и отмечает гостя пришедшим."""
    import io

    import segno

    if ratelimit.hit("ticket_qr", ratelimit.client_ip(request), limit=60, window=600):
        return HttpResponse(status=429)
    code = code.strip().upper()
    get_object_or_404(Ticket, reference_code=code)
    checkin_url = request.build_absolute_uri(reverse("events:checkin", args=[code]))
    buf = io.BytesIO()
    segno.make(checkin_url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


_CANCEL_SALT = "event-ticket-cancel"


def cancel_token(ticket) -> str:
    from django.core import signing

    return signing.dumps(str(ticket.pk), salt=_CANCEL_SALT)


def cancel_url(ticket) -> str:
    return reverse("storefront-ticket-cancel", args=[cancel_token(ticket)])


def veranstaltung_cancel(request, token):
    """R12: самостоятельная отмена билета гостем по подписанной ссылке.

    GET — показать политику отмены (из события) и кнопку. POST — отменить через
    FSM; при бесплатной отмене (flexible до дедлайна) и онлайн-оплате вернуть
    деньги (Stripe Connect). Невозвратный тариф — отмена без возврата. Отмена
    освобождает место (привязанный номер + лист ожидания, как в кабинете).
    """
    _require_events_active(request)
    from django.core import signing

    try:
        pk = signing.loads(token, salt=_CANCEL_SALT)
    except signing.BadSignature as exc:
        raise Http404 from exc
    ticket = get_object_or_404(Ticket.objects.select_related("event", "customer"), pk=pk)
    state = services.cancellation_state(ticket)

    if request.method == "POST" and state["can_cancel"]:
        from apps.core.fsm import IllegalTransition

        from .state_machine import TicketSM

        try:
            TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
        except IllegalTransition:
            messages.error(request, _("This ticket can no longer be cancelled."))
            return redirect(reverse("storefront-ticket-cancel", args=[token]))
        # R5: освободить привязанный номер; R1: уведомить лист ожидания.
        _cancel_linked_stay(ticket)
        services.notify_event_waitlist(ticket.event)
        # Возврат: только при бесплатной отмене и онлайн-оплате (депозит/полная).
        tenant = getattr(request, "tenant", None)
        if (
            state["free"]
            and ticket.payment_state in (Ticket.PAYMENT_PAID, Ticket.PAYMENT_DEPOSIT)
            and ticket.stripe_payment_intent
            and getattr(tenant, "stripe_connect_id", "")
        ):
            try:
                connect.refund(
                    connect_id=tenant.stripe_connect_id,
                    payment_intent=ticket.stripe_payment_intent,
                )
                ticket.payment_state = Ticket.PAYMENT_REFUNDED
                ticket.save(update_fields=["payment_state", "updated_at"])
            except stripe.error.StripeError:
                pass  # отмена состоялась; возврат можно довести вручную в кабинете
        messages.success(request, _("Your ticket has been cancelled."))
        return redirect(reverse("storefront-ticket-cancel", args=[token]))

    return render(
        request,
        "storefront/event_cancel.html",
        {"ticket": ticket, "event": ticket.event, "state": state, "token": token},
    )


def _cancel_linked_stay(ticket) -> None:
    """R5: отменить привязанную бронь проживания (освобождает номер)."""
    booking = ticket.stay_booking
    if booking and booking.status in (booking.STATUS_PENDING, booking.STATUS_CONFIRMED):
        booking.status = booking.STATUS_CANCELLED
        booking.save(update_fields=["status", "updated_at"])
