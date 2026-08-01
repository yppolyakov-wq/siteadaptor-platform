"""Кабинет записи по времени (Track D / D3c): /dashboard/booking/.

Календарь-день (записи по ресурсам, навигация ±), действия по FSM
(confirm/fulfill/no_show/cancel) и перенос (services.move с anti-double-book),
ручное добавление записи (сразу confirmed), управление ресурсами: создание,
недельные правила, выходные. Гейтинг — модуль «booking» из реестра.
"""

from datetime import datetime, time, timedelta

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core.fsm import IllegalTransition
from apps.core.i18n_input import (
    apply_i18n_overlay,
    apply_seq_overlay,
    extra_locales,
    i18n_inputs_for,
)

from . import services
from .models import AvailabilityRule, Booking, ClosedDate, Resource, ServiceSeasonRate
from .state_machine import BookingSM


def _eur_to_cents(raw) -> int:
    """«5» / «5,50» → центы (анти-кривой ввод → 0)."""
    try:
        return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


def _uploaded_image_ref(request, field="image", folder="services") -> dict | None:
    """A3: FileRef из загруженного фото (поле `field`) или None.

    Невалидный файл (не картинка) → None (фото просто не меняем), страница не падает."""
    uploaded = request.FILES.get(field)
    if not uploaded:
        return None
    from apps.catalog.images import save_product_image

    try:
        return save_product_image(uploaded, is_primary=True, folder=folder)
    except Exception:  # noqa: BLE001 — кривой файл не должен ронять CRUD
        return None


def _refund_deposit(request, booking):
    """Анти-фрод: вернуть депозит при отмене оплаченной брони (Stripe Connect)."""
    try:
        connect.refund(
            connect_id=request.tenant.stripe_connect_id,
            payment_intent=booking.stripe_payment_intent,
        )
        booking.payment_state = Booking.PAYMENT_REFUNDED
        booking.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Deposit refunded."))
    except stripe.error.StripeError:
        messages.error(request, _("Refund failed — please check Stripe."))


@login_required
def calendar(request):
    day = _parse_day_any(request.GET.get("tag"))
    tz = timezone.get_current_timezone()
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    bookings = (
        Booking.objects.filter(start__gte=day_start, start__lt=day_end)
        .select_related("resource", "customer")
        .order_by("resource__name", "start")
    )
    from django.urls import reverse

    from apps.core import status_labels, transition_rules

    return render(
        request,
        "booking/calendar.html",
        {
            "nav": "booking",
            "day": day,
            "prev_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1),
            "bookings": bookings,
            "resources": Resource.objects.filter(is_active=True),
            # A4: iframe-виджет записи для своего сайта.
            "embed_url": request.build_absolute_uri(reverse("storefront-termin")) + "?embed=1",
            # FB-4b: строки панели «Status-Namen» (status, дефолт, своё имя).
            "status_label_rows": status_labels.label_rows(
                getattr(request, "tenant", None), "booking", Booking.STATUSES
            ),
            # FB-3: строки панели «Statusübergänge» (правила переходов).
            "transition_rows": transition_rules.editor_rows(
                getattr(request, "tenant", None), "booking"
            ),
        },
    )


def _parse_day_any(raw):
    """Дата без ограничения горизонтом (кабинету нужна и история)."""
    from datetime import date

    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


@login_required
@require_POST
def booking_action(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    action = request.POST.get("action", "")
    back = f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}"
    if action == "move":
        tz = timezone.get_current_timezone()
        try:
            start = datetime.fromisoformat(request.POST.get("start", ""))
            if timezone.is_naive(start):  # datetime-local приходит без TZ
                start = start.replace(tzinfo=tz)
            end = start + (booking.end - booking.start)  # длительность сохраняем
            services.move(booking, start=start, end=end)
            messages.success(request, _("Booking moved."))
        except ValueError:
            messages.error(request, _("Invalid date."))
        except services.SlotTaken:
            messages.error(request, _("That time is already taken."))
        return redirect(back)
    if action in ("confirmed", "fulfilled", "no_show", "cancelled"):
        try:
            BookingSM().apply(booking, action, actor=request.user)
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        messages.success(request, _("Booking updated."))
        # анти-фрод: отмена оплаченной брони возвращает депозит
        if (
            action == "cancelled"
            and booking.payment_state == Booking.PAYMENT_PAID
            and booking.stripe_payment_intent
        ):
            _refund_deposit(request, booking)
    else:
        messages.error(request, _("Unknown action."))
    return redirect(back)


@login_required
@require_POST
def booking_create(request):
    """Ручное добавление (телефонная запись): сразу confirmed."""
    resource = get_object_or_404(Resource, pk=request.POST.get("resource"), is_active=True)
    tz = timezone.get_current_timezone()
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
        if timezone.is_naive(start):
            start = start.replace(tzinfo=tz)
        minutes = max(5, min(int(request.POST.get("minutes", "60")), 24 * 60))
    except (TypeError, ValueError):
        messages.error(request, _("Invalid date."))
        return redirect("booking:calendar")
    name = request.POST.get("name", "").strip() or _("Walk-in")
    try:
        booking = services.book(
            resource,
            start=start,
            end=start + timedelta(minutes=minutes),
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel="manual",
            auto_confirm=True,
        )
    except services.SlotTaken:
        messages.error(request, _("That time is already taken."))
        return redirect("booking:calendar")
    except services.ResourceClosed:
        messages.error(request, _("Closed on this date."))
        return redirect("booking:calendar")
    messages.success(request, _("Booking created."))
    return redirect(f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}")


@login_required
def availability_calendar(request):
    """HF-4 (фидбэк владельца 2026-07-31, п. 1): визуальный календарь доступности.

    Движок закрытия дней (`ClosedDate`) и недельного расписания
    (`AvailabilityRule`) существовал давно, но управлялся списком дат в форме —
    владелец его попросту не находил и не видел картины месяца. Здесь месяц-сетка:
    клик по дню закрывает/открывает продажи на этот день (для всего бизнеса или
    выбранного ресурса), цветом видно, где расписания нет вовсе.
    """
    import calendar as _calendar
    from datetime import date as _date

    from .models import Service

    today = timezone.localdate()
    try:
        first = _date(int(request.GET.get("year") or today.year), int(request.GET["month"]), 1)
    except (TypeError, ValueError, KeyError):
        first = today.replace(day=1)
    resources_qs = list(Resource.objects.filter(is_active=True))
    chosen = next((r for r in resources_qs if str(r.pk) == request.GET.get("resource", "")), None)

    if request.method == "POST":
        day = _parse_day_or_none(request.POST.get("date"))
        if day is None:
            messages.error(request, _("Invalid date."))
        else:
            qs = ClosedDate.objects.filter(date=day, resource=chosen)
            if qs.exists():
                qs.delete()
                messages.success(request, _("Day reopened."))
            else:
                ClosedDate.objects.create(
                    date=day, resource=chosen, reason=request.POST.get("reason", "").strip()[:120]
                )
                messages.success(request, _("Sales closed for this day."))
        return redirect(_calendar_url(first, chosen))

    # Дни месяца: закрыт вручную / нет расписания на этот день недели / открыт.
    closed = {
        c.date: c
        for c in ClosedDate.objects.filter(
            date__gte=first, date__lt=first + timedelta(days=32)
        ).filter(Q(resource=chosen) | Q(resource__isnull=True))
    }
    pool = [chosen] if chosen else resources_qs
    weekdays_with_rules = set(
        AvailabilityRule.objects.filter(resource__in=pool).values_list("weekday", flat=True)
    )
    days = []
    for num in range(1, _calendar.monthrange(first.year, first.month)[1] + 1):
        day = _date(first.year, first.month, num)
        hit = closed.get(day)
        days.append(
            {
                "date": day,
                "in_past": day < today,
                "is_today": day == today,
                # Чужой ClosedDate (всего бизнеса при выбранном ресурсе) снять
                # с этой страницы нельзя — показываем, но не предлагаем клик.
                "closed": hit is not None,
                "closed_here": hit is not None
                and hit.resource_id == (chosen.pk if chosen else None),
                "reason": hit.reason if hit else "",
                "no_rules": day.weekday() not in weekdays_with_rules,
            }
        )
    prev_first = (first - timedelta(days=1)).replace(day=1)
    next_first = (first + timedelta(days=32)).replace(day=1)
    return render(
        request,
        "booking/availability.html",
        {
            "nav": "booking",
            "cal_first": first,
            "cal_days": days,
            "cal_lead_blanks": range(first.weekday()),
            "prev_url": _calendar_url(prev_first, chosen),
            "next_url": _calendar_url(next_first, chosen),
            "resources": resources_qs,
            "chosen_resource": chosen,
            "has_rules": bool(weekdays_with_rules),
            "services": list(Service.objects.filter(is_active=True)[:50]),
        },
    )


def _calendar_url(first, resource=None) -> str:
    url = f"{reverse('booking:availability')}?year={first.year}&month={first.month}"
    return f"{url}&resource={resource.pk}" if resource else url


def _parse_day_or_none(raw):
    from datetime import date as _date

    try:
        return _date.fromisoformat(raw or "")
    except (TypeError, ValueError):
        return None


@login_required
def resources(request):
    """Ресурсы + недельные правила + выходные — простые POST-формы."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "resource":
            name = request.POST.get("name", "").strip()
            if name:
                Resource.objects.create(
                    name=name,
                    type=request.POST.get("type", Resource.TYPE_TABLE),
                    capacity=max(1, min(int(request.POST.get("capacity", "1") or 1), 100)),
                    counts_party_size=bool(request.POST.get("counts_party_size")),
                    deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
                    require_manual_confirm=bool(request.POST.get("require_manual_confirm")),
                )
                messages.success(request, _("Resource created."))
        elif action == "rule":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            try:
                AvailabilityRule.objects.create(
                    resource=resource,
                    weekday=int(request.POST.get("weekday", "0")),
                    start_time=request.POST.get("start_time") or "09:00",
                    end_time=request.POST.get("end_time") or "18:00",
                    slot_minutes=max(5, min(int(request.POST.get("slot_minutes", "30")), 480)),
                )
                messages.success(request, _("Opening hours added."))
            except (TypeError, ValueError):
                messages.error(request, _("Invalid input."))
        elif action == "rule_delete":
            AvailabilityRule.objects.filter(pk=request.POST.get("rule")).delete()
        elif action == "closed":
            try:
                ClosedDate.objects.create(
                    date=request.POST.get("date"),
                    reason=request.POST.get("reason", "").strip()[:120],
                )
                messages.success(request, _("Closed date added."))
            except Exception:  # noqa: BLE001 — кривой ввод даты
                messages.error(request, _("Invalid date."))
        elif action == "toggle":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            resource.is_active = not resource.is_active
            resource.save(update_fields=["is_active", "updated_at"])
        elif action == "resource_settings":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            resource.deposit_cents = _eur_to_cents(request.POST.get("deposit_eur"))
            resource.require_manual_confirm = bool(request.POST.get("require_manual_confirm"))
            resource.counts_party_size = bool(request.POST.get("counts_party_size"))
            resource.save(
                update_fields=[
                    "deposit_cents",
                    "require_manual_confirm",
                    "counts_party_size",
                    "updated_at",
                ]
            )
            messages.success(request, _("Deposit settings saved."))
        elif action == "resource_profile":
            # A3: профиль мастера — должность, био, фото (загрузка/удаление).
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            resource.title = request.POST.get("title", "").strip()[:120]
            resource.bio = request.POST.get("bio", "").strip()[:2000]
            fields = ["title", "bio", "updated_at"]
            new_photo = _uploaded_image_ref(request, "photo", "staff")
            if new_photo or request.POST.get("remove_photo"):
                resource.photo = new_photo or {}
                fields.append("photo")
            resource.save(update_fields=fields)
            messages.success(request, _("Profile saved."))
        return redirect("booking:resources")

    return render(
        request,
        "booking/resources.html",
        {
            "nav": "booking",
            "resources": Resource.objects.prefetch_related("rules").order_by("-is_active", "name"),
            "closed_dates": ClosedDate.objects.filter(date__gte=timezone.localdate()),
            "types": Resource.TYPES,
            "weekdays": AvailabilityRule.WEEKDAYS,
        },
    )


def _rich_lines(raw) -> list[str]:
    """Textarea «пункт на строку» → список строк (пустые выброшены).

    Нормализатор модели (`attributes_list`) всё равно режет длину и количество —
    здесь только разбор разметки формы."""
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _rich_lines_aligned(base_raw, tr_raw) -> list[str]:
    """Перевод-textarea → список, выровненный по ВЫЖИВШИМ строкам базовой.

    Пустые строки базы выбрасываются, поэтому перевод нельзя брать «как есть»:
    удалив пункт из середины, владелец сдвинул бы все переводы ниже него на
    чужие пункты. Берём перевод по НОМЕРУ ИСХОДНОЙ строки."""
    base_lines = (base_raw or "").splitlines()
    tr_lines = (tr_raw or "").splitlines()
    out = [
        tr_lines[i].strip() if i < len(tr_lines) else ""
        for i, line in enumerate(base_lines)
        if line.strip()
    ]
    while out and not out[-1]:
        out.pop()
    return out


def _rich_faq(post, locales) -> tuple[list[dict], dict]:
    """Пары `faq_q_<i>`/`faq_a_<i>` (+ `_<loc>` для переводов) → база и оверлеи.

    База и переводы разбираются ОДНИМ проходом: пара без вопроса отбрасывается
    (очистка вопроса = удаление пункта), и вместе с ней должен исчезнуть её
    перевод — иначе после удаления пункта из середины оставшиеся переводы
    съехали бы на соседние вопросы. Переводы пустых ключей не пишем: `overlay_seq`
    возьмёт на их месте базу.
    """
    base, per_locale = [], {loc: [] for loc in locales}
    i = 0
    while True:
        q = post.get(f"faq_q_{i}")
        a = post.get(f"faq_a_{i}")
        if q is None and a is None:
            break
        q, a = (q or "").strip(), (a or "").strip()
        if q:
            base.append({"q": q, "a": a})
            for loc in locales:
                tq = (post.get(f"faq_q_{i}_{loc}") or "").strip()
                ta = (post.get(f"faq_a_{i}_{loc}") or "").strip()
                per_locale[loc].append({k: v for k, v in (("q", tq), ("a", ta)) if v})
        i += 1
    for loc in locales:  # хвост пустых переводов не несёт информации
        while per_locale[loc] and not per_locale[loc][-1]:
            per_locale[loc].pop()
    return base, per_locale


def _rich_seq_lines(overlay, locale: str, length: int) -> list[str]:
    """Перевод списка строк на локаль, дополненный до длины базового списка.

    Ввод обязан быть выровнен по строкам базовой textarea — иначе после Save
    перевод «съедет» на соседний пункт."""
    items = (overlay or {}).get(locale) if isinstance(overlay, dict) else None
    items = list(items) if isinstance(items, (list, tuple)) else []
    items = [i if isinstance(i, str) else "" for i in items[:length]]
    return items + [""] * (length - len(items))


def _faq_rows(service, locales) -> list[dict]:
    """Строки редактора FAQ: существующие пары + одна пустая (слоты дорастают
    после Save — тот же приём, что в редакторе Finder, без JS)."""
    base = service.faq_list
    overlay = service.faq_i18n if isinstance(service.faq_i18n, dict) else {}
    rows = []
    for i, item in enumerate(base + [{"q": "", "a": ""}]):
        tr = []
        for loc in locales:
            items = overlay.get(loc)
            src = items[i] if isinstance(items, (list, tuple)) and i < len(items) else {}
            src = src if isinstance(src, dict) else {}
            tr.append(
                {
                    "locale": loc,
                    "q_name": f"faq_q_{i}_{loc}",
                    "a_name": f"faq_a_{i}_{loc}",
                    "q": src.get("q", ""),
                    "a": src.get("a", ""),
                }
            )
        rows.append(
            {
                "q_name": f"faq_q_{i}",
                "a_name": f"faq_a_{i}",
                "q": item.get("q", ""),
                "a": item.get("a", ""),
                "i18n": tr,
            }
        )
    return rows


@login_required
def services_view(request, pk=None):
    """Услуги с ценой+длительностью (G10): CRUD простыми POST-формами.

    Фидбэк 2026-07-30: с `pk` — страница ОДНОЙ услуги (как stays:unit-edit),
    без pk — список; POST со страницы услуги возвращает на неё же."""
    from .models import Service

    def _apply_rich(service, tenant) -> list[str]:
        """Богатая карточка (UA4-3): пункты «Details» + FAQ и их переводы.

        Оба блока — под сентинелами: `action=update` шлётся и из компактной
        строки списка, где этих полей нет, а без guard'а такой Save стирал бы
        наполнение (инвариант W0)."""
        changed = []
        if request.POST.get("attributes_present"):
            base_raw = request.POST.get("attributes")
            service.attributes = _rich_lines(base_raw)
            changed.append("attributes")
            per_locale = {
                loc: _rich_lines_aligned(base_raw, request.POST[f"attributes_{loc}"])
                for loc in extra_locales(tenant)
                if f"attributes_{loc}" in request.POST
            }
            if apply_seq_overlay(service, "attributes_i18n", per_locale, tenant):
                changed.append("attributes_i18n")
        if request.POST.get("faq_present"):
            service.faq, per_locale = _rich_faq(request.POST, extra_locales(tenant))
            changed.append("faq")
            if apply_seq_overlay(service, "faq_i18n", per_locale, tenant):
                changed.append("faq_i18n")
        return changed

    def _int(raw, default, lo, hi):
        try:
            return max(lo, min(int(raw), hi))
        except (TypeError, ValueError):
            return default

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            name = request.POST.get("name", "").strip()
            if name:
                service = Service(
                    name=name,
                    description=request.POST.get("description", "").strip(),  # A3
                    image=_uploaded_image_ref(request, "image", "services")
                    or {},  # A3: фото услуги
                    duration_minutes=_int(request.POST.get("duration"), 30, 5, 1440),
                    price_cents=_eur_to_cents(request.POST.get("price_eur")),
                    deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
                    is_video=bool(request.POST.get("is_video")),  # LS-1
                )
                # L3d: переводы неосновных локалей (name_<loc>/description_<loc>)
                apply_i18n_overlay(service, request.POST, getattr(request, "tenant", None))
                _apply_rich(service, getattr(request, "tenant", None))
                service.save()
                messages.success(request, _("Service created."))
        elif action == "update":  # инлайн: длительность + цена + описание (депозит — при создании)
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            service.duration_minutes = _int(request.POST.get("duration"), 30, 5, 1440)
            service.price_cents = _eur_to_cents(request.POST.get("price_eur"))
            service.description = request.POST.get("description", "").strip()  # A3
            fields = ["duration_minutes", "price_cents", "description", "updated_at"]
            # L3d: name правится тоже — но только если поле явно прислано
            # (presence-guard: старые клиенты формы без name не затронуты).
            new_name = request.POST.get("name")
            if new_name is not None and new_name.strip():
                service.name = new_name.strip()
                fields.append("name")
            # LS-1: чекбокс «видео» — только при сентинеле (unchecked не шлётся;
            # presence-guard спасает флаг от чужих клиентов формы без чекбокса).
            if request.POST.get("is_video_present"):
                service.is_video = bool(request.POST.get("is_video"))
                fields.append("is_video")
            fields += apply_i18n_overlay(service, request.POST, getattr(request, "tenant", None))
            fields += _apply_rich(service, getattr(request, "tenant", None))
            # A3: новое фото заменяет старое; чекбокс «удалить» очищает.
            new_image = _uploaded_image_ref(request, "image", "services")
            if new_image or request.POST.get("remove_image"):
                service.image = new_image or {}
                fields.append("image")
            service.save(update_fields=fields)
            messages.success(request, _("Service saved."))
        elif action == "toggle":
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            service.is_active = not service.is_active
            service.save(update_fields=["is_active", "updated_at"])
        elif action == "season_add":  # HF-5: цена услуги на диапазон дат
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            start = _parse_day_or_none(request.POST.get("start_date"))
            end = _parse_day_or_none(request.POST.get("end_date"))
            price_cents = _eur_to_cents(request.POST.get("price_eur"))
            if start is None or end is None or end < start:
                messages.error(request, _("Invalid date."))
            elif price_cents <= 0:
                # Ревью HF-5: пустое/нулевое поле цены молча делало услугу в эти
                # даты БЕСПЛАТНОЙ — ноль доезжал до брони. Хочет бесплатно —
                # ставит 0 в базовой цене услуги, а не в сезонном окне.
                messages.error(request, _("Please enter a price for these dates."))
            else:
                ServiceSeasonRate.objects.create(
                    service=service,
                    label=request.POST.get("label", "").strip()[:120],
                    start_date=start,
                    end_date=end,
                    price_cents=price_cents,
                )
                messages.success(request, _("Seasonal price saved."))
        elif action == "season_delete":
            ServiceSeasonRate.objects.filter(pk=request.POST.get("season")).delete()
            messages.success(request, _("Seasonal price removed."))
        if pk:
            return redirect("booking:service-edit", pk=pk)
        return redirect("booking:services")

    if pk:
        service_page = get_object_or_404(Service, pk=pk)
        services = [service_page]
    else:
        service_page = None
        services = list(Service.objects.order_by("-is_active", "name"))
    locales = extra_locales(getattr(request, "tenant", None))
    for svc in services:  # L3d: данные per-locale инпутов готовим в Python
        svc.i18n_inputs = i18n_inputs_for(svc, getattr(request, "tenant", None))
        svc.seasons = list(svc.season_rates.all())  # HF-5: цены на диапазоны дат
        # UA4-3-ввод: пункты «Details» — textarea (строка = пункт), переводы —
        # textarea на локаль, выровненная по строкам базовой.
        attrs = svc.attributes_list
        svc.attributes_text = "\n".join(attrs)
        svc.attributes_i18n_inputs = [
            {
                "locale": loc,
                "input_name": f"attributes_{loc}",
                "value": "\n".join(
                    _rich_seq_lines(svc.attributes_i18n, loc, len(attrs)),
                ),
            }
            for loc in locales
        ]
        # FAQ — пары полей: разделитель внутри свободного текста ломался бы на
        # первом же ответе с переносом строки. Одна пустая пара — чтобы добавить.
        svc.faq_rows = _faq_rows(svc, locales)
    return render(
        request,
        "booking/services.html",
        {
            "service_page": service_page,
            "nav": "booking",
            "services": services,
            # Фидбэк 2026-07-30 («на сайте пишет: нет доступных»): без рабочих часов
            # слоты не генерируются вообще. Показываем причину ЗДЕСЬ, где владелец
            # правит услугу, — иначе он ищет «календарь услуги», которого нет.
            "has_hours": AvailabilityRule.objects.exists(),
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
        },
    )


@login_required
def passes_view(request):
    """Mehrfachkarten / 10er-Karten (G9): выпуск, баланс, ручное погашение."""
    from datetime import date as _date

    from .models import Pass, PassPlan, Service

    def _int(raw, default, lo, hi):
        try:
            return max(lo, min(int(raw), hi))
        except (TypeError, ValueError):
            return default

    def _cents(raw):
        try:
            return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
        except (TypeError, ValueError):
            return 0

    def _vu(raw):  # valid_until: пусто/кривое → бессрочно (None)
        try:
            return _date.fromisoformat(raw or "")
        except (TypeError, ValueError):
            return None

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "issue":
            name = request.POST.get("name", "").strip()
            if name:
                services.issue_pass(
                    name=name,
                    email=request.POST.get("email", "").strip(),
                    phone=request.POST.get("phone", "").strip(),
                    label=request.POST.get("label", "").strip() or "Mehrfachkarte",
                    credits=_int(request.POST.get("credits"), 10, 1, 100),
                    valid_until=_vu(request.POST.get("valid_until")),
                )
                messages.success(request, _("Pass issued."))
            else:
                messages.error(request, _("Please enter the customer's name."))
        elif action == "redeem":  # ручное погашение (walk-in / при визите)
            card = get_object_or_404(Pass, pk=request.POST.get("pass"))
            try:
                services.redeem_pass(card)
                messages.success(request, _("One visit redeemed."))
            except services.PassInvalid:
                messages.error(request, _("This pass has no visits left or has expired."))
        elif action == "toggle":
            card = get_object_or_404(Pass, pk=request.POST.get("pass"))
            card.is_active = not card.is_active
            card.save(update_fields=["is_active", "updated_at"])
        elif action == "plan_add":  # A3: тариф для онлайн-продажи
            label = request.POST.get("label", "").strip() or "Mehrfachkarte"
            svc = Service.objects.filter(pk=request.POST.get("service") or None).first()
            PassPlan.objects.create(
                label=label[:120],
                credits=_int(request.POST.get("credits"), 10, 1, 100),
                price_cents=_cents(request.POST.get("price")),
                valid_days=_int(request.POST.get("valid_days"), 0, 0, 3650),
                service=svc,
            )
            messages.success(request, _("Card plan added."))
        elif action == "plan_toggle":
            plan = get_object_or_404(PassPlan, pk=request.POST.get("plan"))
            plan.is_active = not plan.is_active
            plan.save(update_fields=["is_active", "updated_at"])
        return redirect("booking:passes")

    return render(
        request,
        "booking/passes.html",
        {
            "nav": "booking",
            "passes": Pass.objects.select_related("customer")[:300],
            "plans": PassPlan.objects.select_related("service"),
            "services": Service.objects.filter(is_active=True),
        },
    )


# --- A3: инлайн-правка услуги на канве витрины (?preview=1) ---
def _bump_storefront(request):
    """SE-5a: правка данных (не site_config) кэш не бампит — сбрасываем явно."""
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)


@login_required
@require_POST
def service_inline_edit(request):
    """Инлайн-правка услуги на канве — тонкий алиас единого диспетчера (UC2-4).

    Контракт/URL прежние: JSON {pk, field, value}; семантика — декларация
    INLINE_REGISTRY["service"]: name (плоско, кламп 120, пустым нельзя)/
    description; price_eur → центы; bump на всех ветках."""
    from apps.core.inline_edit import dispatch

    return dispatch(request, "service")


@login_required
@require_POST
def service_photo_edit(request):
    """UC4-3: галерея услуги на канве витрины (multipart: pk, op ∈ {replace, add,
    remove}, image_id, image). Хранение — тот же JSONField `image`: легаси-dict
    читается шимом Service.images, ЗАПИСЬ — всегда списком (без миграции). Реюз
    catalog.images.apply_gallery_op (Pillow + storage + primary-логика). 204/400."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.catalog.images import apply_gallery_op

    from .models import Service

    pk = request.POST.get("pk")
    op = request.POST.get("op", "replace")
    image_id = request.POST.get("image_id", "")
    uploaded = request.FILES.get("image")
    if not pk:
        return HttpResponseBadRequest()
    try:
        # Блокируем строку на время read-modify-write JSON-поля (lost update).
        with transaction.atomic():
            service = Service.objects.select_for_update().get(pk=pk)
            service.image = apply_gallery_op(
                service.images, op=op, image_id=image_id, uploaded=uploaded, folder="services"
            )
            service.save(update_fields=["image", "updated_at"])
    except (Service.DoesNotExist, ValueError):
        return HttpResponseBadRequest()
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    _bump_storefront(request)
    return HttpResponse(status=204)
