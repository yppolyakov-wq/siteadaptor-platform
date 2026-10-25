"""Кабинет событий (A6b): CRUD, ростер участников, действия FSM, CSV-экспорт."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import refunds
from apps.core import transactions as core_transactions
from apps.core.csv_safe import csv_safe
from apps.core.roles import audit_export
from apps.core.view_perms import perm_required

from . import itinerary, registration
from .forms import EventForm, TeacherForm, TourForm, unique_tour_slug
from .models import Event, Teacher, Ticket, Tour
from .services import book_ticket, notify_event_waitlist
from .state_machine import EventSM


def _add_event_photos(event, uploaded) -> None:
    """Сохранить загруженные фото места/мероприятия (до 12). Первое — обложка,
    если фото ещё нет. Переиспускаем catalog.images (Pillow + storage)."""
    from apps.catalog.images import save_product_image

    if not uploaded:
        return
    images = list(event.images or [])
    for f in uploaded[:12]:
        try:
            ref = save_product_image(
                f, is_primary=not images, sort_order=len(images), folder="events"
            )
        except Exception:
            continue
        images.append(ref)
    if images != list(event.images or []):
        event.images = images[:24]
        event.save(update_fields=["images"])


def _delete_event_photo(event, ref_id) -> None:
    from apps.catalog.images import delete_stored_image

    keep = [i for i in event.images if str(i.get("id")) != str(ref_id)]
    for i in event.images:
        if str(i.get("id")) == str(ref_id):
            delete_stored_image(i)
    if keep and not any(i.get("is_primary") for i in keep):
        keep[0]["is_primary"] = True
    event.images = keep
    event.save(update_fields=["images"])


@login_required
def event_list(request):
    events = Event.objects.all().order_by("-starts_at")
    return render(request, "events/event_list.html", {"events": events, "nav": "events"})


@login_required
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.save()
        _add_event_photos(event, request.FILES.getlist("photos"))
        if event.status == Event.STATUS_PUBLISHED:
            # CM-3: создано сразу опубликованным → авто-черновик поста в каналы.
            from apps.publishing.services import event_share_draft

            event_share_draft(event)
        messages.success(request, _("Event created."))
        return redirect("events:detail", pk=event.pk)
    from . import taxonomy

    return render(
        request,
        "events/event_form.html",
        {"form": form, "nav": "events", "category_presets": taxonomy.CATEGORIES},
    )


@login_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    was_published = event.status == Event.STATUS_PUBLISHED
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        _add_event_photos(event, request.FILES.getlist("photos"))
        if event.status == Event.STATUS_PUBLISHED and not was_published:
            # CM-3: первая публикация → авто-черновик поста в каналы.
            from apps.publishing.services import event_share_draft

            event_share_draft(event)
        if request.POST.get("delete_image"):
            _delete_event_photo(event, request.POST["delete_image"])
        messages.success(request, _("Event saved."))
        return redirect("events:detail", pk=event.pk)
    from . import taxonomy

    return render(
        request,
        "events/event_form.html",
        {"form": form, "event": event, "nav": "events", "category_presets": taxonomy.CATEGORIES},
    )


@login_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    tickets = event.tickets.select_related("customer").all()
    # 3b: допы для правки состава билета (scope events + адресные этого события).
    from apps.core import extras as extras_engine

    edit_extras = extras_engine.active_for("events", entity_kind="event", entity_id=str(event.pk))
    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "tickets": tickets,
            "edit_extras": edit_extras,
            "waitlist": event.waitlist.all(),
            "nav": "events",
            # KA-H8: отмена события — подтверждение с последствиями.
            "cancel_confirm_text": _(
                "Veranstaltung wirklich absagen? Alle aktiven Anmeldungen werden storniert, "
                "Kartenzahlungen erstattet und die Teilnehmer per E-Mail informiert."
            ),
        },
    )


@login_required
@require_POST
def waitlist_notify(request, pk):
    """Разослать письма «снова frei» листу ожидания (если есть места)."""
    event = get_object_or_404(Event, pk=pk)
    sent = notify_event_waitlist(event)
    if sent:
        messages.success(request, _("Notified %(n)s people from the waitlist.") % {"n": sent})
    else:
        messages.info(request, _("No one to notify (no free spots or empty waitlist)."))
    return redirect("events:detail", pk=pk)


@login_required
@require_POST
def event_action(request, pk):
    """Публикация/снятие/отмена события (EventSM)."""
    event = get_object_or_404(Event, pk=pk)
    target = request.POST.get("target", "")
    if target == Event.STATUS_CANCELLED:
        # KA-H8: отмена события = массовый возврат и письма всем участникам —
        # только владелец и только с подтверждением (не одним кликом/POST).
        from apps.core.permissions import has_perm

        if not has_perm(request.user, "veranstaltung.absagen"):
            messages.error(request, _("Nur der Inhaber kann eine Veranstaltung absagen."))
            return redirect("events:detail", pk=pk)
        if request.POST.get("confirm_cancel") != "1":
            messages.error(request, _("Bitte die Absage bestätigen."))
            return redirect("events:detail", pk=pk)
    try:
        EventSM().apply(event, target, actor=request.user)
        if target == Event.STATUS_CANCELLED:
            messages.success(
                request,
                _(
                    "Veranstaltung abgesagt. Die Anmeldungen werden jetzt storniert — die "
                    "Zusammenfassung erhalten Sie per E-Mail."
                ),
            )
        else:
            messages.success(request, _("Event updated."))
    except Exception:  # noqa: BLE001 — недопустимый переход
        messages.error(request, _("Action not allowed."))
    return redirect("events:detail", pk=pk)


@login_required
@require_POST
def ticket_add(request, pk):
    """Ручная запись участника (без оплаты) — сразу подтверждён."""
    event = get_object_or_404(Event, pk=pk)
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, _("Name is required."))
        return redirect("events:detail", pk=pk)
    try:
        qty = max(1, int(request.POST.get("quantity", "1")))
    except (TypeError, ValueError):
        qty = 1
    from .services import EventNotBookable, SoldOut, WaiverRequired

    try:
        book_ticket(
            event,
            name=name,
            email=(request.POST.get("email") or "").strip(),
            phone=(request.POST.get("phone") or "").strip(),
            quantity=qty,
            auto_confirm=True,
        )
        messages.success(request, _("Attendee added."))
    except SoldOut:
        messages.error(request, _("Not enough seats left."))
    except EventNotBookable:
        messages.error(request, _("Publish the event first."))
    except WaiverRequired:  # KA-H8: было необработанное исключение → 500
        messages.error(
            request,
            _(
                "Diese Veranstaltung verlangt eine unterschriebene Haftungsfreistellung. "
                "Teilnehmer melden sich dafür selbst über die Website an."
            ),
        )
    return redirect("events:detail", pk=pk)


@login_required
def ticket_detail(request, pk):
    """DC-7 (ТЗ владельца 2026-08-25): карточка билета — экрана не было вовсе,
    доска и списки вели на страницу СОБЫТИЯ, где билет терялся среди прочих.

    Собирается общим скелетом карточки сделки (`core/deal_card_base.html`):
    голова, статус, клиент, скидка и связи — из одного источника; здесь —
    специфика билета: тир, места, доп-услуги, ответы анкеты, waiver.
    """
    from apps.core import deal_card, deal_links
    from apps.core import extras as extras_engine

    from .models import Ticket

    ticket = get_object_or_404(Ticket.objects.select_related("customer", "event"), pk=pk)
    edit_extras = extras_engine.active_for(
        "events", entity_kind="event", entity_id=str(ticket.event_id)
    )
    chosen = {
        str(e.get("id")) for e in (ticket.extras or []) if isinstance(e, dict) and e.get("id")
    }
    return render(
        request,
        "events/ticket_detail.html",
        {
            "t": ticket,
            "nav": "events",
            "edit_extras": edit_extras,
            "chosen_extra_ids": chosen,
            "waiver": getattr(ticket, "waiver", None),
            **deal_card.card_context(
                request,
                "ticket",
                ticket,
                sections=("items", "discount", "totals", "payment", "thread"),
                links=deal_links.block_context("ticket", ticket.pk),
            ),
        },
    )


@login_required
@require_POST
def ticket_action(request, pk, tid):
    """Действия по билету: confirm / attended / cancel (FSM) + mark paid."""
    ticket = get_object_or_404(Ticket, pk=tid, event_id=pk)
    target = request.POST.get("target", "")
    if request.POST.get("action") == "extras":
        # 3b (зеркало MX-3): правка состава допов билета; итог — свойство
        # Ticket.total_cents (пересчитывается сам). Enforcement трекеров — MX-2e.
        from apps.core import extras as extras_engine
        from apps.core import option_trackers

        if ticket.status not in (Ticket.STATUS_PENDING, Ticket.STATUS_CONFIRMED):
            messages.error(request, _("This step is not possible in the current status."))
            return redirect("events:detail", pk=pk)
        old_total = ticket.total_cents
        new_snap = extras_engine.snapshot(
            request.POST.getlist("extra"),
            "events",
            entity_kind="event",
            entity_id=str(ticket.event_id),
        )
        try:
            option_trackers.sync_options(ticket.extras, new_snap, kind="ticket", deal=ticket)
        except option_trackers.PoolFull as exc:
            messages.error(
                request,
                _("„%(label)s“ ist im gewählten Zeitraum leider ausgebucht.")
                % {"label": exc.label},
            )
            return redirect("events:detail", pk=pk)
        except option_trackers.OptionOutOfStock as exc:
            messages.error(
                request,
                _("„%(label)s“ ist leider nicht mehr verfügbar.") % {"label": exc.label},
            )
            return redirect("events:detail", pk=pk)
        ticket.extras = new_snap
        ticket.save(update_fields=["extras", "updated_at"])
        messages.success(request, _("Ticket updated."))
        if ticket.payment_state == Ticket.PAYMENT_PAID and ticket.total_cents != old_total:
            diff = (ticket.total_cents - old_total) / 100
            messages.warning(
                request,
                _(
                    "Der Betrag hat sich um %(diff)s € geändert — Nachzahlung oder "
                    "Erstattung mit dem Gast klären."
                )
                % {"diff": f"{diff:+.2f}"},
            )
        return redirect("events:detail", pk=pk)
    if target == "paid":
        if ticket.status == Ticket.STATUS_CANCELLED or (
            ticket.payment_state == Ticket.PAYMENT_REFUNDED
        ):
            messages.error(request, _("This step is not possible in the current status."))
            return redirect("events:detail", pk=pk)
        # KA-H8: ручное «bezahlt» закрывает рассрочку — иначе beat списывал бы
        # следующие доли с карты повторно.
        from .installments import settle_manually

        plan = getattr(ticket, "installment_plan", None) if _has_plan(ticket) else None
        if plan is not None and settle_manually(plan):  # ждёт блокировку доли beat'а
            messages.info(
                request,
                _("Ratenzahlung als bezahlt abgeschlossen — weitere Raten werden nicht abgebucht."),
            )
        from apps.core import money_contract

        money_contract.settle_payment("ticket", ticket)  # KA-MC: единый путь
        messages.success(request, _("Marked as paid."))
    else:
        try:
            refund = core_transactions.apply_action(
                "ticket",
                ticket,
                target,
                actor=request.user,
                tenant=getattr(request, "tenant", None),
            )
        except refunds.RefundNotAllowed:
            messages.error(request, str(refunds.NOT_ALLOWED_MSG))
            return redirect("events:detail", pk=pk)
        except Exception:  # noqa: BLE001
            messages.error(request, _("Action not allowed."))
            return redirect("events:detail", pk=pk)
        messages.success(request, _("Ticket updated."))
        # KA-H4: отмена оплаченного билета возвращает оплату — вне try: статус уже
        # сохранён, сбой после него не должен показать «Action not allowed.».
        refunds.flash(request, refund, "ticket")
        if target == Ticket.STATUS_CANCELLED:
            # R5/MX-0: номер освобождает TicketSM-хук (единый узел).
            # Отмена освободила место → уведомить лист ожидания (R1).
            notify_event_waitlist(ticket.event)
    return redirect("events:detail", pk=pk)


@login_required
def tour_list(request):
    """MT-1: список тур-продуктов + быстрое создание (заголовок → slug)."""
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        if title:
            tour = Tour.objects.create(title=title[:200], slug=unique_tour_slug(title))
            messages.success(request, _("Tour created."))
            return redirect("events:tour-edit", pk=tour.pk)
        return redirect("events:tour-list")
    tours = Tour.objects.prefetch_related("departures")
    return render(request, "events/tour_list.html", {"tours": tours, "nav": "events"})


@login_required
def tour_edit(request, pk):
    """MT-1: правка тура — поля, блоки лендинга, маршрут, фото, удаление.

    Маршрут приходит отдельными строками (`it_*_<i>`), поэтому сохраняется
    только когда редактор реально был на странице: сентинел `it_present`
    защищает наполнение от затирания частичной формой (инвариант W0).
    """
    tour = get_object_or_404(Tour, pk=pk)
    if request.method == "POST" and request.POST.get("action") == "delete":
        tour.delete()
        messages.success(request, _("Tour deleted."))
        return redirect("events:tour-list")
    form = TourForm(request.POST or None, instance=tour)
    if request.method == "POST" and form.is_valid():
        form.save()
        if request.POST.get("it_present"):
            tour.itinerary = itinerary.from_post(request.POST)
            tour.save(update_fields=["itinerary"])
        _add_tour_photos(tour, request.FILES.getlist("photos"))
        if request.POST.get("delete_image"):
            _delete_tour_photo(tour, request.POST["delete_image"])
        messages.success(request, _("Tour saved."))
        return redirect("events:tour-edit", pk=tour.pk)
    stops = itinerary.normalize(tour.itinerary)
    return render(
        request,
        "events/tour_form.html",
        {
            "form": form,
            "tour": tour,
            "nav": "events",
            # Запас пустых строк, чтобы маршрут дорастал без JS (паттерн FD-3).
            "stops": stops + [{}] * 3,
            "visibility_choices": itinerary.visibility_choices(),
            "departures": tour.departures.order_by("starts_at"),
        },
    )


def _add_tour_photos(tour, uploaded) -> None:
    """Фото тура — тем же конвейером, что фото события (Pillow + storage)."""
    from apps.catalog.images import save_product_image

    if not uploaded:
        return
    images = list(tour.images or [])
    for f in uploaded[:12]:
        try:
            ref = save_product_image(
                f, is_primary=not images, sort_order=len(images), folder="tours"
            )
        except Exception:
            continue
        images.append(ref)
    if images != list(tour.images or []):
        tour.images = images[:24]
        tour.save(update_fields=["images"])


def _delete_tour_photo(tour, ref_id) -> None:
    from apps.catalog.images import delete_stored_image

    keep = [i for i in tour.images if str(i.get("id")) != str(ref_id)]
    for i in tour.images:
        if str(i.get("id")) == str(ref_id):
            delete_stored_image(i)
    if keep and not any(i.get("is_primary") for i in keep):
        keep[0]["is_primary"] = True
    tour.images = keep
    tour.save(update_fields=["images"])


@login_required
def blog_list(request):
    """RT4: кабинет блога — список записей + создание (простой POST)."""
    from django.utils import timezone
    from django.utils.text import slugify

    from .models import BlogPost

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if title:
            base = slugify(title) or "post"
            slug, n = base, 1
            while BlogPost.objects.filter(slug=slug).exists():
                n += 1
                slug = f"{base}-{n}"
            published = bool(request.POST.get("publish"))
            # CM-2: «Veröffentlichen am» — будущая дата планирует публикацию
            # (черновик с датой; beat send_due_content включит по наступлении).
            publish_at = _parse_publish_at(request)
            if publish_at is not None:
                published = False
            post = BlogPost.objects.create(
                title=title[:200],
                slug=slug[:220],
                excerpt=request.POST.get("excerpt", "").strip()[:300],
                body=request.POST.get("body", "").strip(),
                cover=_uploaded_cover(request),
                is_published=published,
                published_at=publish_at or (timezone.now() if published else None),
            )
            if published:
                # CM-3: опубликован сразу → авто-черновик поста в каналы.
                from apps.publishing.services import blog_share_draft

                blog_share_draft(post)
            messages.success(request, _("Post created."))
        return redirect("blog-list")
    # Фидбэк владельца 2026-08-25 («кнопка поделиться и выбрать канал где»):
    # у каждой опубликованной статьи — меню каналов с прямыми share-ссылками;
    # «во все активные каналы» остаётся отдельным пунктом (модуль publishing).
    from urllib.parse import quote

    from django.urls import reverse

    from apps.core.share_links import share_targets

    posts = list(BlogPost.objects.all())
    base = f"{request.scheme}://{request.get_host()}"
    rows = []
    for post in posts:
        url = f"{base}{reverse('storefront-blog-post', args=[post.slug])}"
        rows.append(
            {
                "post": post,
                "share_url": url,
                "share_targets": share_targets(post.title, url),
                # «Во все активные каналы» — существующий контент-календарь с
                # префиллом текста и ссылки (модуль publishing).
                "share_all_url": (
                    f"{reverse('publishing-posts')}?text={quote(post.title)}&link={quote(url)}"
                ),
            }
        )
    return render(
        request,
        "events/blog_list.html",
        {
            "nav": "blog",  # W7b: своя вкладка в Marketing-хабе (была "events")
            "posts": posts,
            "rows": rows,
            # CM-3: пункт «во все каналы» виден только при активном модуле publishing.
            "can_share": getattr(request, "tenant", None) is not None
            and request.tenant.is_module_active("publishing"),
        },
    )


@login_required
def blog_edit(request, pk):
    """RT4: правка записи блога + публикация/снятие/удаление."""
    from django.utils import timezone

    from .models import BlogPost

    post = get_object_or_404(BlogPost, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "delete":
            post.delete()
            messages.success(request, _("Post deleted."))
            return redirect("blog-list")
        post.title = request.POST.get("title", post.title).strip()[:200]
        post.excerpt = request.POST.get("excerpt", "").strip()[:300]
        post.body = request.POST.get("body", "").strip()
        cover = _uploaded_cover(request)
        if cover or request.POST.get("remove_cover"):
            post.cover = cover
        publish = bool(request.POST.get("publish"))
        publish_at = _parse_publish_at(request)
        was_published = post.is_published
        if publish_at is not None:
            # CM-2: будущая дата планирует (перекрывает чекбокс) — beat включит.
            post.is_published = False
            post.published_at = publish_at
        else:
            if publish and not post.is_published:
                post.published_at = timezone.now()
            post.is_published = publish
        post.save()
        if post.is_published and not was_published:
            # CM-3: первая публикация → авто-черновик поста в каналы.
            from apps.publishing.services import blog_share_draft

            blog_share_draft(post)
        messages.success(request, _("Post saved."))
        return redirect("blog-edit", pk=post.pk)
    return render(
        request,
        "events/blog_edit.html",
        {
            "nav": "events",
            "post": post,
            "can_share": getattr(request, "tenant", None) is not None
            and request.tenant.is_module_active("publishing"),
        },
    )


def _parse_publish_at(request):
    """CM-2: «Veröffentlichen am» из формы блога — только БУДУЩАЯ aware-дата
    (прошлая/пустая → None: обычная логика publish-чекбокса)."""
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    raw = (request.POST.get("publish_at") or "").strip()
    dt = parse_datetime(raw) if raw else None
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt if dt > timezone.now() else None


def _uploaded_cover(request) -> dict:
    """RT4: FileRef из загруженной обложки (поле «cover») или {}."""
    uploaded = request.FILES.get("cover")
    if not uploaded:
        return {}
    from apps.catalog.images import save_product_image

    try:
        return save_product_image(uploaded, is_primary=True, folder="blog")
    except Exception:  # noqa: BLE001 — кривой файл не валит CRUD
        return {}


@login_required
@require_POST
def event_series(request, pk):
    """RT3: создать recurring-серию — N повторов события с шагом интервала."""
    from . import services

    event = get_object_or_404(Event, pk=pk)
    interval = request.POST.get("interval", "weekly")
    try:
        count = int(request.POST.get("count", "0"))
    except (TypeError, ValueError):
        count = 0
    if count < 1:
        messages.error(request, _("Please choose how many occurrences to create."))
        return redirect("events:detail", pk=pk)
    created = services.create_series(event, interval=interval, count=count)
    messages.success(
        request,
        _("Created %(n)d more dates in this series.") % {"n": len(created)},
    )
    return redirect("events:detail", pk=pk)


def _has_plan(ticket) -> bool:
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return ticket.installment_plan is not None
    except ObjectDoesNotExist:
        return False


@login_required
def checkin(request, code):
    """RT1: Check-in билета по QR (организатор в кабинете). GET — карточка гостя и
    кнопка «Einchecken»; POST — отметить пришедшим (status→attended + checked_in_at).
    Сканирует логин-сессия владельца; чужой без логина уходит на login (защита)."""
    from django.utils import timezone

    ticket = get_object_or_404(
        Ticket.objects.select_related("event", "customer"),
        reference_code=code.strip().upper(),
    )
    if request.method == "POST":
        if ticket.status == Ticket.STATUS_CANCELLED:
            messages.error(request, _("This ticket is cancelled."))
        elif ticket.event.status == ticket.event.STATUS_CANCELLED:
            messages.error(request, _("Die Veranstaltung wurde abgesagt."))
        elif ticket.checked_in_at:
            messages.info(request, _("Already checked in."))
        elif ticket.status == Ticket.STATUS_PENDING and not request.POST.get("confirm_first"):
            # KA-H8: неоплаченный билет не «приходит» мимо FSM — сначала подтвердить.
            messages.error(request, _("Das Ticket ist noch nicht bestätigt."))
        else:
            tenant = getattr(request, "tenant", None)
            try:
                if ticket.status == Ticket.STATUS_PENDING:
                    core_transactions.apply_action(
                        "ticket", ticket, Ticket.STATUS_CONFIRMED, actor=request.user, tenant=tenant
                    )
                if ticket.status != Ticket.STATUS_ATTENDED:
                    core_transactions.apply_action(
                        "ticket", ticket, Ticket.STATUS_ATTENDED, actor=request.user, tenant=tenant
                    )
            except Exception:  # noqa: BLE001 — запрещённый переход: ничего не пишем
                messages.error(request, _("Action not allowed."))
                return redirect("events:checkin", code=ticket.reference_code)
            ticket.checked_in_at = timezone.now()
            ticket.save(update_fields=["checked_in_at", "updated_at"])
            messages.success(request, _("Checked in — welcome!"))
        return redirect("events:checkin", code=ticket.reference_code)
    return render(request, "events/checkin.html", {"ticket": ticket, "event": ticket.event})


@login_required
def teacher_list(request):
    teachers = Teacher.objects.all()
    return render(request, "events/teacher_list.html", {"teachers": teachers, "nav": "events"})


@login_required
def teacher_create(request):
    form = TeacherForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Teacher created."))
        return redirect("events:teacher-list")
    return render(request, "events/teacher_form.html", {"form": form, "nav": "events"})


@login_required
def teacher_edit(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    form = TeacherForm(request.POST or None, instance=teacher)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Teacher saved."))
        return redirect("events:teacher-list")
    return render(
        request,
        "events/teacher_form.html",
        {"form": form, "teacher": teacher, "nav": "events"},
    )


@login_required
@require_POST
def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    teacher.delete()
    messages.success(request, _("Teacher deleted."))
    return redirect("events:teacher-list")


@login_required
@perm_required("kunden.export")
def roster_csv(request, pk):
    """CSV-ростер участников события (utf-8-sig — Excel-friendly)."""
    event = get_object_or_404(Event, pk=pk)
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="roster-{event.pk}.csv"'
    writer = csv.writer(response, delimiter=";")
    question_cols = list(event.questions or [])
    reg_cols = registration.labels(event.registration_fields)  # [(key, label)]
    show_unterkunft = event.offers_accommodation
    show_waiver = event.waiver_required  # R8
    writer.writerow(
        [
            "Code",
            "Name",
            "E-Mail",
            "Telefon",
            "Plätze",
            "Status",
            "Bezahlt",
            # KA-12 T-2: что гиду нужно в день старта — тариф, деньги, допы, вход.
            "Tarif",
            "Betrag",
            "Offen",
            "Extras",
            "Check-in",
            *(["Unterkunft"] if show_unterkunft else []),
            *(["Waiver"] if show_waiver else []),
            *question_cols,
            *[label for _key, label in reg_cols],
        ]
    )
    from apps.core import folio, money_contract

    tickets = list(event.tickets.select_related("customer", "stay_booking__unit", "waiver"))
    folio.prefetch("ticket", tickets)  # ревью T-2: остаток без запроса на каждый билет
    rows = 0
    for t in tickets:
        rows += 1
        answers = t.answers or {}
        room = t.stay_booking.unit.name if t.stay_booking and t.stay_booking.unit else ""
        waiver = getattr(t, "waiver", None)
        waiver_cell = (
            f"{waiver.signed_name} ({waiver.signed_at:%d.%m.%Y})"
            if waiver and waiver.signed_at
            else ("✓" if waiver else "—")
        )
        writer.writerow(
            [
                t.reference_code,
                csv_safe(t.customer.name),
                csv_safe(t.customer.email),
                csv_safe(t.customer.phone),
                t.quantity,
                t.get_status_display(),
                t.get_payment_state_display(),
                csv_safe(t.tier_label),
                f"{t.payable_cents / 100:.2f}",
                f"{money_contract.due('ticket', t):.2f}",
                csv_safe(
                    ", ".join(
                        str(x.get("label", "")) for x in (t.extras or []) if isinstance(x, dict)
                    )
                ),
                f"{timezone.localtime(t.checked_in_at):%d.%m.%Y %H:%M}" if t.checked_in_at else "",
                *([csv_safe(room)] if show_unterkunft else []),
                *([csv_safe(waiver_cell)] if show_waiver else []),
                *[csv_safe(answers.get(q, "")) for q in question_cols],
                *[csv_safe(answers.get(key, "")) for key, _label in reg_cols],
            ]
        )
    audit_export(request, "roster", rows, resource_id=event.pk)
    return response


@login_required
@require_POST
def event_inline_edit(request):
    """Инлайн-правка события на канве — тонкий алиас единого диспетчера (UC2-4).

    Контракт/URL прежние: JSON {pk, field, value}; семантика — декларация
    INLINE_REGISTRY["event"]: title (плоско, кламп 200, пустым нельзя)/
    description; price_eur → центы, только без тиров; bump на всех ветках."""
    from apps.core.inline_edit import dispatch

    return dispatch(request, "event")


@login_required
@require_POST
def event_photo_edit(request):
    """Пер-слайд правка галереи события на канве (multipart: pk, op, image_id, image).
    op ∈ {replace, add, remove}. Зеркало catalog.product_photo_edit — Event.images тот
    же FileRef-список, общий диспетчер apply_gallery_op. 204/400."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.catalog.images import apply_gallery_op

    pk = request.POST.get("pk")
    op = request.POST.get("op", "replace")
    image_id = request.POST.get("image_id", "")
    uploaded = request.FILES.get("image")
    if not pk:
        return HttpResponseBadRequest()
    try:
        # Лок строки на read-modify-write images (анти-lost-update при параллельных правках).
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=pk)
            event.images = apply_gallery_op(
                event.images, op=op, image_id=image_id, uploaded=uploaded, folder="events"
            )
            event.save(update_fields=["images", "updated_at"])
    except (Event.DoesNotExist, ValueError):
        return HttpResponseBadRequest()
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)
    return HttpResponse(status=204)


@login_required
def event_feature(request, pk):
    """D2.4: продвижение события в агрегаторе (self-serve featured,
    generic-зеркало promotion_feature — apps.aggregator.featuring)."""
    from django.urls import reverse
    from django.utils import timezone

    from apps.aggregator import featuring
    from apps.aggregator.models import AggregatorListing

    event = get_object_or_404(Event, pk=pk)
    listable = event.is_published and event.starts_at > timezone.now()
    return featuring.render_feature_page(
        request,
        obj_title=event.title,
        kind=AggregatorListing.KIND_EVENT,
        source_ref=str(event.pk),
        listable=listable,
        not_listed_hint=_(
            "Nur veröffentlichte, kommende Veranstaltungen erscheinen im "
            "Verzeichnis und können beworben werden."
        ),
        back_url=reverse("events:detail", args=[event.pk]),
        checkout_url=reverse("events:feature-checkout", args=[event.pk]),
        nav="events",
    )


@login_required
@require_POST
def event_feature_checkout(request, pk):
    """D2.4: разовый Stripe-Checkout за продвижение события → редирект на оплату."""
    from django.urls import reverse
    from django.utils import timezone

    from apps.aggregator import featuring
    from apps.aggregator.models import AggregatorListing
    from apps.aggregator.tasks import sync_event_listing

    event = get_object_or_404(Event, pk=pk)
    return featuring.start_feature_checkout(
        request,
        kind=AggregatorListing.KIND_EVENT,
        source_ref=str(event.pk),
        title=event.title,
        listable=event.is_published and event.starts_at > timezone.now(),
        not_listable_msg=_("Nur veröffentlichte, kommende Veranstaltungen können beworben werden."),
        sync=sync_event_listing,
        feature_page_url=reverse("events:feature", args=[event.pk]),
    )


@login_required
def event_logistics(request, pk):
    """MT-4/5/6: логистика заезда, экономика и чек-лист подготовки в одном месте.

    Закупочные цены здесь показываются гиду и НИКОГДА не уезжают на витрину
    (участнику отдаётся `SupplierBooking.participant_view`).
    """

    from .logistics import SupplierBooking, TourTask
    from .tour_finance import event_margin, sync_expense

    event = get_object_or_404(Event, pk=pk)
    if request.method == "POST":
        from django.db import transaction

        # Ревью T-2: каждое действие — одна транзакция (правка записи и её расход
        # меняются вместе); строка записи блокируется от параллельной смены статуса.
        with transaction.atomic():
            error = _logistics_post(request, event, SupplierBooking, TourTask, sync_expense)
        if error:
            messages.error(request, error)
        else:
            messages.success(request, _("Saved."))
        return redirect("events:logistics", pk=event.pk)
    return render(
        request,
        "events/event_logistics.html",
        {
            "event": event,
            "bookings": event.supplier_bookings.select_related("supplier"),
            "tasks": event.prep_tasks.all(),
            "finance": event_margin(event),
            "kinds": SupplierBooking.KINDS,
            "statuses": SupplierBooking.STATUSES,
            "suppliers": _active_suppliers(),
            # KA-12 T-2: заезды с чек-листом — источник «Aus anderem Termin übernehmen».
            "task_sources": Event.objects.exclude(pk=event.pk)
            .filter(prep_tasks__isnull=False)
            .distinct()
            .order_by("-starts_at")[:20],
            "nav": "events",
        },
    )


def _logistics_post(request, event, SupplierBooking, TourTask, sync_expense):  # noqa: N803
    """POST-действия логистики. Возвращает текст ошибки или "" (успех)."""
    from django.utils import timezone

    action = request.POST.get("action", "")

    def _booking():
        # Ревью T-2: мусор вместо UUID — 404, а не ValidationError (500).
        return get_object_or_404(
            SupplierBooking.objects.select_for_update(),
            pk=_uuid_or_none(request.POST.get("id")),
            event=event,
        )

    if action == "add_booking":
        _add_supplier_booking(request, event)
    elif action == "edit_booking":
        # KA-12 T-2: поставщика можно поправить (опечатка, новая цена/дата).
        booking = _booking()
        if booking.status == SupplierBooking.STATUS_PAID and not _cents(
            request.POST.get("cost_eur")
        ):
            return _("Eine bezahlte Buchung braucht einen Betrag.")
        _add_supplier_booking(request, event, booking=booking)
        sync_expense(booking)  # оплаченная запись: расход идёт за новой суммой
    elif action == "delete_booking":
        booking = _booking()
        if booking.status == SupplierBooking.STATUS_PAID:
            # Оплаченная — расход уже в журнале: только «Storniert», не удаление.
            return _(
                "Bezahlte Buchungen werden nicht gelöscht — setzen Sie den Status auf „Storniert“."
            )
        sync_expense(booking)
        booking.delete()
    elif action == "copy_tasks":
        # KA-12 T-2: чек-лист из другого заезда — те же задачи, срок с тем же
        # отступом от старта (шаблон = прошлый тур, без отдельного хранилища).
        source = get_object_or_404(Event, pk=_uuid_or_none(request.POST.get("source")))
        if not _copy_tasks(source, event):
            return _("Keine neuen Aufgaben zum Übernehmen.")
    elif action == "booking_status":
        booking = _booking()
        target = request.POST.get("status", "")
        if target in dict(SupplierBooking.STATUSES):
            booking.status = target
            booking.save(update_fields=["status", "updated_at"])
            # Расход появляется/исчезает вместе со статусом «Bezahlt».
            sync_expense(booking)
    elif action == "booking_visibility":
        booking = _booking()
        booking.visible_to_participants = not booking.visible_to_participants
        booking.save(update_fields=["visible_to_participants", "updated_at"])
    elif action == "add_task":
        title = (request.POST.get("title") or "").strip()
        if title:
            TourTask.objects.create(
                event=event,
                title=title[:200],
                due_date=_parse_date(request.POST.get("due_date")),
            )
    elif action == "toggle_task":
        task = get_object_or_404(
            TourTask.objects.select_for_update(),
            pk=_uuid_or_none(request.POST.get("id")),
            event=event,
        )
        task.done_at = None if task.done_at else timezone.now()
        task.save(update_fields=["done_at", "updated_at"])
    return ""


def _active_suppliers():
    from apps.inventory.models import Lieferant

    return Lieferant.objects.filter(is_active=True)


_MAX_INT = 2_147_483_647  # PositiveIntegerField
_MAX_SMALL = 32_767  # PositiveSmallIntegerField


def _cents(raw) -> int:
    """Евро из формы → центы; мусор/бесконечность → 0, сверх поля — кламп (не 500)."""
    from decimal import Decimal, InvalidOperation

    try:
        value = Decimal(str(raw or "0").replace(",", "."))
        if not value.is_finite():
            return 0
        return min(max(0, int(value * 100)), _MAX_INT)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return 0


def _parse_date(raw):
    """Дата из формы: мусор → None, а не ValidationError (500) при save()."""
    from datetime import date

    try:
        return date.fromisoformat(str(raw).strip()) if raw else None
    except ValueError:
        return None


def _uuid_or_none(raw):
    from apps.stays.rate_plans import parse_uuid

    return parse_uuid(raw)


def _copy_tasks(source, event) -> int:
    from .logistics import TourTask

    if source.pk == event.pk:
        return 0
    have = set(event.prep_tasks.values_list("title", flat=True))
    shift = None
    if source.starts_at and event.starts_at:
        shift = (
            timezone.localtime(event.starts_at).date() - timezone.localtime(source.starts_at).date()
        )
    created = 0
    for task in source.prep_tasks.all():
        if task.title in have:
            continue
        due = task.due_date + shift if (task.due_date and shift is not None) else None
        TourTask.objects.create(
            event=event, title=task.title, due_date=due, sort_order=task.sort_order
        )
        created += 1
    return created


def _add_supplier_booking(request, event, booking=None) -> None:
    """Новая строка книги логистики (цена — в евро, оригинал опционально).

    KA-12 T-2: с `booking` — правка существующей строки теми же полями."""
    from decimal import Decimal, InvalidOperation

    from .logistics import SupplierBooking

    def _decimal(raw):
        try:
            value = Decimal(str(raw).replace(",", ".")) if raw not in (None, "") else None
        except (InvalidOperation, TypeError, ValueError):
            return None
        if value is None or not value.is_finite() or abs(value) >= 10**10:
            return None  # поле 12,2: сверх — None, а не DataError
        return value.quantize(Decimal("0.01"))

    supplier_id = _uuid_or_none(request.POST.get("supplier"))  # Lieferant.pk — UUID
    keep = getattr(booking, "supplier_id", None)
    if (
        supplier_id
        and supplier_id != keep
        and not _active_suppliers().filter(pk=supplier_id).exists()
    ):
        supplier_id = None  # чужой/мусорный id — без поставщика, а не 500
    fields = dict(
        kind=request.POST.get("kind") or SupplierBooking.KIND_HOTEL,
        supplier_id=supplier_id,
        supplier_name=(request.POST.get("supplier_name") or "").strip()[:200],
        day=min(_int_or_zero(request.POST.get("day")), _MAX_SMALL),
        date=_parse_date(request.POST.get("date")),
        stop=(request.POST.get("stop") or "").strip()[:200],
        qty=min(max(1, _int_or_zero(request.POST.get("qty")) or 1), _MAX_SMALL),
        cost_cents=_cents(request.POST.get("cost_eur")),
        currency=(request.POST.get("currency") or "").strip()[:3].upper(),
        amount_original=_decimal(request.POST.get("amount_original")),
        note=(request.POST.get("note") or "").strip()[:300],
    )
    if fields["kind"] not in dict(SupplierBooking.KINDS):
        fields["kind"] = SupplierBooking.KIND_OTHER
    if booking is None:
        SupplierBooking.objects.create(event=event, **fields)
        return
    for name, value in fields.items():
        setattr(booking, name, value)
    booking.save(update_fields=[*fields, "updated_at"])  # статус/видимость не трогаем


def _int_or_zero(raw) -> int:
    try:
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 0
