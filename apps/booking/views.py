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
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core.fsm import IllegalTransition

from . import services
from .models import AvailabilityRule, Booking, ClosedDate, Resource
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


@login_required
def services_view(request):
    """Услуги с ценой+длительностью (G10): CRUD простыми POST-формами."""
    from .models import Service

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
                Service.objects.create(
                    name=name,
                    description=request.POST.get("description", "").strip(),  # A3
                    image=_uploaded_image_ref(request, "image", "services")
                    or {},  # A3: фото услуги
                    duration_minutes=_int(request.POST.get("duration"), 30, 5, 1440),
                    price_cents=_eur_to_cents(request.POST.get("price_eur")),
                    deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
                )
                messages.success(request, _("Service created."))
        elif action == "update":  # инлайн: длительность + цена + описание (депозит — при создании)
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            service.duration_minutes = _int(request.POST.get("duration"), 30, 5, 1440)
            service.price_cents = _eur_to_cents(request.POST.get("price_eur"))
            service.description = request.POST.get("description", "").strip()  # A3
            fields = ["duration_minutes", "price_cents", "description", "updated_at"]
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
        return redirect("booking:services")

    return render(
        request,
        "booking/services.html",
        {"nav": "booking", "services": Service.objects.order_by("-is_active", "name")},
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
_SERVICE_INLINE_FIELDS = {"name", "description"}


def _bump_storefront(request):
    """SE-5a: правка данных (не site_config) кэш не бампит — сбрасываем явно."""
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)


@login_required
@require_POST
def service_inline_edit(request):
    """Инлайн-правка услуги прямо на витрине: JSON {pk, field, value},
    field ∈ {name, description, price_eur}. Поля плоские (Service не i18n-dict).
    Имя пустым не сохраняем. Зеркало events.event_inline_edit. 204/400."""
    import json

    from django.core.exceptions import ValidationError
    from django.http import HttpResponse, HttpResponseBadRequest

    from .models import Service

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    pk = data.get("pk")
    field = data.get("field")
    value = data.get("value", "")
    if not pk or field not in (_SERVICE_INLINE_FIELDS | {"price_eur"}):
        return HttpResponseBadRequest()
    try:
        service = Service.objects.get(pk=pk)
    except (Service.DoesNotExist, ValidationError, ValueError):
        return HttpResponseBadRequest()

    if field == "price_eur":
        from decimal import Decimal, InvalidOperation

        raw = str(value).strip().replace(",", ".")
        try:
            euros = Decimal(raw)
        except (InvalidOperation, ValueError):
            return HttpResponseBadRequest()
        if euros < 0 or euros > Decimal("1000000"):
            return HttpResponseBadRequest()
        service.price_cents = int((euros * 100).quantize(Decimal("1")))
        service.save(update_fields=["price_cents", "updated_at"])
        _bump_storefront(request)
        return HttpResponse(status=204)

    value = value.strip() if isinstance(value, str) else ""
    if field == "name" and not value:  # пустое имя не сохраняем
        return HttpResponseBadRequest()
    setattr(service, field, value[:120] if field == "name" else value)
    service.save(update_fields=[field, "updated_at"])
    _bump_storefront(request)
    return HttpResponse(status=204)


@login_required
@require_POST
def service_photo_edit(request):
    """Заменить фото услуги на канве витрины (multipart: pk + image). У услуги фото —
    одиночный FileRef-словарь (Service.image), не список → просто перезаписываем. 204/400."""
    from django.core.exceptions import ValidationError
    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.catalog.images import save_product_image

    from .models import Service

    pk = request.POST.get("pk")
    uploaded = request.FILES.get("image")
    if not pk or not uploaded:
        return HttpResponseBadRequest()
    try:
        service = Service.objects.get(pk=pk)
    except (Service.DoesNotExist, ValidationError, ValueError):
        return HttpResponseBadRequest()
    try:
        new_ref = save_product_image(uploaded, is_primary=True, sort_order=0, folder="services")
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    service.image = new_ref
    service.save(update_fields=["image", "updated_at"])
    _bump_storefront(request)
    return HttpResponse(status=204)
