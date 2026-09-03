"""Кабинет владельца: акции (CRUD + переходы статусов) и брони (управление).

Статусы акций двигаем только через PromotionSM; брони — через services
(confirm/fulfill/cancel) поверх ReservationSM. Все вьюхи требуют логина.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.catalog.images import delete_stored_image, save_product_image
from apps.core.documents import document_language
from apps.core.fsm import IllegalTransition
from apps.loyalty.models import LoyaltyCard, LoyaltyProgram, Voucher

from . import group_styles, services
from .forms import LoyaltyProgramForm, PromotionForm, VoucherCreateForm
from .models import Customer, Promotion, Reservation
from .poster import build_shop_poster_pdf
from .presets import preset_initial, presets_for
from .state_machine import PromotionSM

PROMO_STATUSES = ["draft", "scheduled", "active", "paused", "ended", "archived"]
RESERVATION_STATUSES = ["pending", "confirmed", "fulfilled", "cancelled", "expired"]


def _bump_storefront(request):
    """Сброс кэша витрины тенанта — правка сразу видна на публичной."""
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)


@login_required
@require_POST
def promotion_inline_edit(request):
    """Инлайн-правка акции на канве — тонкий алиас единого диспетчера (UC2-4).

    Контракт/URL прежние: JSON {pk, field, value}; семантика — декларация
    INLINE_REGISTRY["promotion"]: title → i18n['de'] (пустым нельзя, БЕЗ bump —
    как раньше), price_override/compare_at_price (Decimal), discount_percent
    (0..100, 0 → очистить), ends_at (ISO → aware). Поля движка
    (status/available_quantity) в реестре НЕТ — анти-оверселл-гейт цел."""
    from apps.core.inline_edit import dispatch

    return dispatch(request, "promotion")


@login_required
@require_POST
def promotion_photo_edit(request):
    """UE3-2: править галерею АКЦИИ прямо на канве витрины (multipart).

    POST: pk, op ∈ {replace, add, remove}, image_id (replace/remove), image
    (файл для replace/add). Реюз catalog.images.apply_gallery_op (Pillow +
    storage + primary-логика; folder="promotions" — как _handle_promo_uploads).
    Фолбэк карточки на фото товара цел: primary_image решает сама (пустая
    галерея акции → фото товара; replace в пустую добавляет главное).
    Сброс кэша витрины. Только владелец. 204/400.
    """
    from django.db import transaction
    from django.http import HttpResponseBadRequest

    from apps.catalog.images import apply_gallery_op

    pk = request.POST.get("pk")
    op = request.POST.get("op", "replace")
    image_id = request.POST.get("image_id", "")
    uploaded = request.FILES.get("image")
    if not pk:
        return HttpResponseBadRequest()
    try:
        # Блокируем строку на время read-modify-write JSON-поля images (lost update).
        with transaction.atomic():
            promo = Promotion.objects.select_for_update().get(pk=pk)
            promo.images = apply_gallery_op(
                promo.images, op=op, image_id=image_id, uploaded=uploaded, folder="promotions"
            )
            promo.save(update_fields=["images", "updated_at"])
    except (Promotion.DoesNotExist, ValueError):
        return HttpResponseBadRequest()
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    _bump_storefront(request)
    return HttpResponse(status=204)


# подписи для кнопок переходов акции
# X6-3: подписи переходов были ГОЛЫМИ английскими литералами — на немецком
# экране кабинета печатались как есть (и не переводились на 5 локалей).
_PROMO_ACTION_LABELS = {
    "scheduled": gettext_lazy("Einplanen"),
    "active": gettext_lazy("Jetzt aktivieren"),
    "paused": gettext_lazy("Pausieren"),
    "ended": gettext_lazy("Beenden"),
    "archived": gettext_lazy("Archivieren"),
}

# X6-3 (ловушка черновика): статус показывали сырым кодом («draft»), и владелец
# не понимал, почему созданная акция не видна клиентам.
# Ревью 2026-08-19: единственный источник подписей — choices модели, иначе
# словарь-сателлит расходится с экранами (аналитика печатала сырой код).
PROMO_STATUS_LABELS = dict(Promotion.STATUSES)


def promo_status_label(status: str):
    return PROMO_STATUS_LABELS.get(status, status)


def _promo_actions(promo):
    """Доступные переходы акции как [(target, label)]."""
    return [
        (t, _PROMO_ACTION_LABELS.get(t, t)) for t in PromotionSM().allowed_targets(promo.status)
    ]


def _handle_promo_uploads(request, promo) -> None:
    """Сохраняет загруженные файлы в promo.images (FileRef-envelope)."""
    files = request.FILES.getlist("images")
    if not files:
        return
    images = list(promo.images or [])
    has_primary = any(img.get("is_primary") for img in images)
    for f in files:
        try:
            ref = save_product_image(
                f, is_primary=not has_primary, sort_order=len(images), folder="promotions"
            )
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
            continue
        has_primary = True
        images.append(ref)
    promo.images = images
    promo.save(update_fields=["images", "updated_at"])


@login_required
def promotion_list(request):
    promos = Promotion.objects.select_related("product").all()
    status = request.GET.get("status", "")
    if status:
        promos = promos.filter(status=status)

    # D2.2: вход в self-serve featured из списка — бейдж «beworben bis …» /
    # «Bewerben ★» на active-акциях (один public-запрос по листингам).
    from apps.billing import featured as billing_featured

    featured_enabled = billing_featured.is_enabled()
    promos = list(promos)
    if featured_enabled and promos:
        from django.db import connection
        from django.utils import timezone as tz

        from apps.aggregator.models import AggregatorListing

        until_by_uuid = dict(
            AggregatorListing.objects.filter(
                tenant_schema=connection.schema_name,
                promo_uuid__in=[p.id for p in promos],
            ).values_list("promo_uuid", "featured_until")
        )
        now = tz.now()
        for p in promos:
            until = until_by_uuid.get(p.id)
            p.featured_until_agg = until
            p.is_featured_agg = bool(until and until > now)

    # X6-3: человеческая подпись статуса на строке (сырой код «draft» ни о чём
    # не говорит владельцу — исследование 2026-08-18 §3, «ловушка черновика»).
    for p in promos:
        p.status_label = promo_status_label(p.status)
    return render(
        request,
        "promotions/promotion_list.html",
        {
            "promotions": promos,
            # X6-3: фильтр показывал сырые коды статусов — даём подписи.
            "statuses": [(st, promo_status_label(st)) for st in PROMO_STATUSES],
            "status": status,
            "featured_enabled": featured_enabled,
            "nav": "promotions",
            # VF-20b: перекрёстный вход в Кампании (соседняя задача — «разослать
            # персональные коды»). Гейт по модулю кампаний (crm) — fail-closed,
            # иначе ссылка вела бы в 404 гейта путей.
            "campaigns_active": bool(
                getattr(request, "tenant", None) and request.tenant.is_module_active("crm")
            ),
            # DL-13 C3: текущий режим страницы /aktionen/ (панель «gliedern»).
            "promo_grouping": _promo_grouping(request),
            "promo_layout": _promo_layout(request),  # DL-16.2 A3
            # DL-20: шаблон страницы КАЖДОЙ группы (модели группы нет — ключ словаря
            # site_config["promo_groups"] совпадает с ключом фасета `?gruppe=`).
            "group_page_styles": group_styles.GROUP_PAGE_STYLES,
            "promo_group_rows": _promo_group_rows(request),
            # DL-21.2: шаблон обзорной страницы /aktionen/.
            "promo_page_style": _promo_page_style(request),
            "promo_page_styles": group_styles.PROMO_PAGE_STYLES,
        },
    )


def _promo_grouping(request) -> str:
    from apps.tenants import siteconfig

    raw = getattr(getattr(request, "tenant", None), "site_config", None)
    raw = raw if isinstance(raw, dict) else {}
    return siteconfig.normalize_promo_grouping(raw.get("promo_grouping"))


def _promo_group_rows(request):
    """DL-20: живые группы владельца + выбранный шаблон страницы каждой.

    Список строится по САМИМ акциям, а не по словарю настроек: группа —
    свободный текст, и запись, осиротевшая после переименования, не должна
    показываться владельцу как существующая группа.
    """
    from apps.tenants import siteconfig

    raw = getattr(getattr(request, "tenant", None), "site_config", None)
    raw = raw if isinstance(raw, dict) else {}
    saved = siteconfig.normalize_promo_groups(raw.get("promo_groups"))
    names = sorted(
        {g for g in Promotion.objects.exclude(group="").values_list("group", flat=True) if g}
    )
    return [{"name": g, "style": saved.get(g, "")} for g in names]


def _promo_page_style(request) -> str:
    from apps.tenants import siteconfig

    raw = getattr(getattr(request, "tenant", None), "site_config", None)
    raw = raw if isinstance(raw, dict) else {}
    return siteconfig.normalize_promo_page_style(raw.get("promo_page_style"))


def _promo_layout(request) -> str:
    from apps.tenants import siteconfig

    raw = getattr(getattr(request, "tenant", None), "site_config", None)
    raw = raw if isinstance(raw, dict) else {}
    return siteconfig.normalize_promo_layout(raw.get("promo_layout"))


@login_required
@require_POST
def promotion_page_mode(request):
    """DL-13 C3: режим страницы /aktionen/ — по группам владельца ("") или
    «по времени» ("time": Endet heute · diese Woche · länger · dauerhaft).

    Targeted-write ключа promo_grouping (паттерн set_presence_view): остальной
    site_config цел; "" = отсутствие ключа (presence-minimal, golden целы)."""
    from apps.tenants import siteconfig

    tenant = request.tenant
    cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
    mode = siteconfig.normalize_promo_grouping(request.POST.get("mode", ""))
    if mode:
        cfg["promo_grouping"] = mode
    else:
        cfg.pop("promo_grouping", None)
    # DL-16.2 (A3): раскладка групп — сетка ("") или ленты-слайдеры ("slider")
    layout = siteconfig.normalize_promo_layout(request.POST.get("layout", ""))
    if layout:
        cfg["promo_layout"] = layout
    else:
        cfg.pop("promo_layout", None)
    # DL-21.2: шаблон обзорной страницы — presence по полю (плитки шлют hidden всегда).
    if "page_style" in request.POST:
        _ps = siteconfig.normalize_promo_page_style(request.POST.get("page_style", ""))
        if _ps:
            cfg["promo_page_style"] = _ps
        else:
            cfg.pop("promo_page_style", None)
    # DL-20: шаблон страницы каждой группы. Поля приходят как `group_style:<имя>`;
    # пустое значение = «как на всём сайте» (записи в словаре нет → presence-minimal).
    groups = dict(siteconfig.normalize_promo_groups(cfg.get("promo_groups")))
    for key, value in request.POST.items():
        if not key.startswith("group_style:"):
            continue
        name = key[len("group_style:") :].strip()
        if not name:
            continue
        if (value or "").strip():
            groups[name] = value.strip()
        else:
            groups.pop(name, None)
    groups = siteconfig.normalize_promo_groups(groups)
    if groups:
        cfg["promo_groups"] = groups
    else:
        cfg.pop("promo_groups", None)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, _("Ansicht der Aktionsseite gespeichert."))
    return redirect("promotions:promotion-list")


# C2: цели QR-печатки — (url-name, модуль-гейт, заголовок, подпись). Невалидная/
# неактивная цель падает на витрину (home). Канал атрибуции остаётся schaufenster.
_POSTER_TARGETS = {
    "home": ("storefront-home", "", None, None),
    "termin": (
        "storefront-termin",
        "booking",
        gettext_lazy("Scan & book an appointment"),
        gettext_lazy("Pick a free slot and book in 30 seconds — with your phone."),
    ),
    "sortiment": (
        "storefront-products",
        "catalog",
        gettext_lazy("Scan & order"),
        gettext_lazy("Browse our range and order right away — with your phone."),
    ),
    "unterkunft": (
        "storefront-unterkunft",
        "stays",
        gettext_lazy("Scan & book a room"),
        gettext_lazy("Check availability and book right away — with your phone."),
    ),
    "veranstaltung": (
        "storefront-events",
        "events",
        gettext_lazy("Scan & grab tickets"),
        gettext_lazy("See upcoming events and book tickets."),
    ),
}


@login_required
def shop_poster_pdf(request):
    """A4-постер с QR для печати (Track B4 + C2). Кабинет — на субдомене
    бизнеса, поэтому адрес берём с того же хоста. ?ziel= выбирает цель QR
    (меню/бронь/номера/события; гейт по модулям), цвет — фирменный."""
    tenant = getattr(request, "tenant", None)
    business_name = getattr(tenant, "name", "") or "Unser Shop"
    ziel = request.GET.get("ziel", "home")
    if ziel not in _POSTER_TARGETS:  # мусор → витрина (и в имени файла тоже)
        ziel = "home"
    url_name, module, headline, subline = _POSTER_TARGETS[ziel]
    if module and (tenant is None or not tenant.is_module_active(module)):
        ziel, (url_name, module, headline, subline) = "home", _POSTER_TARGETS["home"]
    target_url = request.build_absolute_uri(reverse(url_name))
    # I18N-7b: постер печатает владелец — язык кабинета или явный `?lang=`
    # (напр. турецкий постер для турецкого квартала).
    with translation.override(document_language(request)):
        pdf = build_shop_poster_pdf(
            business_name,
            target_url,
            headline=str(headline) if headline else None,
            subline=str(subline) if subline else None,
            accent_hex=getattr(tenant, "primary_color", "") or "",
        )
    resp = HttpResponse(pdf, content_type="application/pdf")
    slug = getattr(tenant, "slug", "") or "shop"
    resp["Content-Disposition"] = f'attachment; filename="schaufenster-poster-{slug}-{ziel}.pdf"'
    return resp


def _promo_i18n_groups(form, request):
    """Ф1: группы i18n-полей акции (title/description) для переключателя языка формы."""
    from apps.core.i18n_input import i18n_form_groups

    ctx = i18n_form_groups(form, getattr(request, "tenant", None), fields=("title", "description"))
    # Метка группы — flat+overlay, поэтому её переводы идут отдельным списком
    # (свёрнутый блок под полем `group`), а не во вкладках языка.
    ctx["group_i18n_fields"] = [
        form[f"group_{loc}"]
        for loc in getattr(form, "_group_locales", [])
        if f"group_{loc}" in form.fields
    ]
    return ctx


@login_required
def promotion_create(request):
    # request.tenant может отсутствовать (напр. в unit-тестах через RequestFactory),
    # поэтому достаём его защитно — пресеты просто схлопнутся к универсальным.
    tenant = getattr(request, "tenant", None)
    business_type = getattr(tenant, "business_type", "") or ""
    initial = {}
    if request.method == "GET" and request.GET.get("preset"):
        initial = preset_initial(business_type, request.GET["preset"])
    # W11-4: префилл цели из «Aktion erstellen» строки Angebote (?service=/…).
    if request.method == "GET":
        for key in ("product", "service", "stay_unit", "combo"):
            if request.GET.get(key):
                initial[key] = request.GET[key]
    form = PromotionForm(
        request.POST or None,
        request.FILES or None,
        initial=initial or None,
        tenant=getattr(request, "tenant", None),
    )
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        _handle_promo_uploads(request, promo)
        return redirect("promotions:promotion-edit", pk=promo.pk)
    return render(
        request,
        "promotions/promotion_form.html",
        {
            "form": form,
            "is_create": True,
            "nav": "promotions",
            "presets": presets_for(business_type),
            **_promo_i18n_groups(form, request),
        },
    )


@login_required
def promotion_edit(request, pk):
    promo = get_object_or_404(Promotion, pk=pk)
    form = PromotionForm(
        request.POST or None,
        request.FILES or None,
        instance=promo,
        tenant=getattr(request, "tenant", None),
    )
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        _handle_promo_uploads(request, promo)
        return redirect("promotions:promotion-edit", pk=promo.pk)
    # атрибуция: брони по каналам привлечения
    channel_stats = list(
        promo.reservations.values("source_channel").annotate(n=Count("id")).order_by("-n")
    )
    # предустановленные каналы для генерации QR
    preset_channels = ["instagram", "facebook", "flyer", "schaufenster", "website"]
    from apps.billing import featured as billing_featured

    return render(
        request,
        "promotions/promotion_form.html",
        {
            "form": form,
            "is_create": False,
            "promotion": promo,
            "actions": _promo_actions(promo),
            "status_label": promo_status_label(promo.status),  # X6-3
            "channel_stats": channel_stats,
            "preset_channels": preset_channels,
            "waitlist_count": promo.waitlist.count(),
            "stats": _promo_stats(promo),
            # Платное продвижение в агрегаторе (P2.4b): карточка-ссылка на странице
            # акции. Листинг есть, только пока акция active.
            "featured_listing": _featured_listing(promo),
            "featured_enabled": billing_featured.is_enabled(),
            "nav": "promotions",
            **_promo_i18n_groups(form, request),
        },
    )


def _featured_listing(promo):
    """Листинг агрегатора этой акции (SHARED/public) или None.

    Листинг материализуется, только пока акция active (sync_listing);
    featured_until на нём — то, что продаёт P2.4b. Ключ — (схема тенанта,
    promo_uuid). В unit-тестах без tenant-миддлвари схемы листинга нет → None.
    """
    from django.db import connection

    from apps.aggregator.models import AggregatorListing

    return AggregatorListing.objects.filter(
        tenant_schema=connection.schema_name, promo_uuid=promo.id
    ).first()


@login_required
def promotion_share(request, pk):
    """ST-6b: экран «Teilen» акции — статус публикаций по каналам + идемпотентная
    кнопка «Jetzt überall veröffentlichen» (тот же веер, что при активации;
    дублей Publication нет) + входы «остальных каналов»: e-mail-кампания
    (ТОЛЬКО переход — UWG §7, ничего не рассылаем) и ★ Feature."""
    from apps.billing import featured as billing_featured

    promo = get_object_or_404(Promotion, pk=pk)
    publishing_on = request.tenant.is_module_active("publishing")
    if request.method == "POST":
        if not publishing_on or promo.status != "active":
            messages.error(request, _("Nur aktive Aktionen können geteilt werden."))
        else:
            from apps.publishing import services as publishing_services

            n = publishing_services.republish_promotion(promo)
            messages.success(
                request, _("In %(n)s Kanäle eingereiht — Veröffentlichung läuft.") % {"n": n}
            )
        return redirect("promotions:promotion-share", pk=promo.pk)

    publications, pending_channels = [], []
    if publishing_on:
        from apps.publishing.models import Channel, Publication

        publications = list(Publication.objects.filter(promotion=promo).select_related("channel"))
        have = {p.channel_id for p in publications}
        pending_channels = [c for c in Channel.objects.filter(is_enabled=True) if c.id not in have]
    return render(
        request,
        "promotions/promotion_share.html",
        {
            "nav": "promotions",
            "promo": promo,
            "publications": publications,
            "pending_channels": pending_channels,
            "publishing_on": publishing_on,
            "featured_enabled": billing_featured.is_enabled() and promo.status == "active",
        },
    )


@login_required
def promotion_feature(request, pk):
    """Страница продвижения акции в агрегаторе (P2.4b): планы, цена, статус."""
    from apps.billing import featured as billing_featured

    promo = get_object_or_404(Promotion, pk=pk)
    listing = _featured_listing(promo)
    return render(
        request,
        "promotions/promotion_feature.html",
        {
            "promotion": promo,
            "listing": listing,
            "plans": billing_featured.get_plans(),
            "featured_enabled": billing_featured.is_enabled(),
            "is_listed": promo.status == "active" and listing is not None,
            "checkout_status": request.GET.get("status", ""),
            "nav": "promotions",
        },
    )


@login_required
@require_POST
def promotion_feature_checkout(request, pk):
    """Разовый Stripe-Checkout за продвижение акции → редирект на оплату (P2.4b)."""
    from apps.billing import featured as billing_featured
    from apps.billing import services as billing_services

    promo = get_object_or_404(Promotion, pk=pk)
    days_raw = request.POST.get("days", "")
    plan = billing_featured.get_plan(int(days_raw)) if days_raw.isdigit() else None
    if not billing_featured.is_enabled() or plan is None:
        messages.error(request, _("Empfehlung ist derzeit nicht verfügbar."))
        return redirect("promotions:promotion-feature", pk=pk)
    if promo.status != "active":
        messages.error(request, _("Nur aktive Aktionen können beworben werden."))
        return redirect("promotions:promotion-feature", pk=pk)

    # Гарантируем листинг к моменту оплаты (синк мог не успеть отработать);
    # featured_until при ресинке сохраняется (P2.4a).
    from django.db import connection

    from apps.aggregator.tasks import sync_listing

    sync_listing(connection.schema_name, str(promo.id))

    base = request.build_absolute_uri(reverse("promotions:promotion-feature", args=[promo.pk]))
    url = billing_services.create_featured_checkout_session(
        request.tenant,
        promo_uuid=str(promo.id),
        days=plan.days,
        title=promo.get_i18n("title") or "Aktion",
        success_url=f"{base}?status=success",
        cancel_url=f"{base}?status=cancel",
    )
    return redirect(url)


def _conversion(n_res, views):
    return round(n_res / views * 100, 1) if views else None


def _promo_stats(promo) -> dict:
    """Аналитика акции: просмотры, сделки, конверсия.

    P7 «ценовой слой»: акция закрывается СТАНДАРТНЫМИ сделками (заказ/бронь) —
    считаем их через `price_layer.deal_counts`; легаси-резервы остаются в
    статистике, пока живы (история цела). Конверсия — по всем сделкам."""
    from .price_layer import deal_counts

    by_status = dict(promo.reservations.values_list("status").annotate(n=Count("id")).order_by())
    total = sum(by_status.values())
    deals = deal_counts(promo)
    return {
        "views": promo.views,
        "by_status": by_status,
        "total": total,
        "fulfilled": by_status.get("fulfilled", 0),
        "deals": deals,
        "conversion": _conversion(total + deals["total"], promo.views),
    }


@login_required
def analytics_overview(request):
    promos = Promotion.objects.annotate(
        n_res=Count("reservations"),
        n_fulfilled=Count("reservations", filter=Q(reservations__status="fulfilled")),
    ).order_by("-views")
    # P7 «ценовой слой»: сделки новых рельсов — bulk без N+1: брони услуг/номеров
    # двумя агрегатами по FK, заказы — один проход по строкам с promo-маркером.
    from apps.booking.models import Booking
    from apps.orders.models import OrderItem
    from apps.stays.models import StayBooking

    deal_map: dict = {}  # str(promo_pk) → сделок
    for pid, n in (
        Booking.objects.filter(promotion__isnull=False)
        .exclude(status=Booking.STATUS_CANCELLED)
        .values_list("promotion_id")
        .annotate(n=Count("id"))
    ):
        deal_map[str(pid)] = deal_map.get(str(pid), 0) + n
    for pid, n in (
        StayBooking.objects.filter(promotion__isnull=False)
        .exclude(status=StayBooking.STATUS_CANCELLED)
        .values_list("promotion_id")
        .annotate(n=Count("id"))
    ):
        deal_map[str(pid)] = deal_map.get(str(pid), 0) + n
    order_seen = set()  # (promo_id, order_id) — заказ считаем один раз
    for order_id, mods in (
        OrderItem.objects.filter(modifiers__icontains='"promo"')
        .exclude(order__status="cancelled")
        .values_list("order_id", "modifiers")
    ):
        for m in mods or ():
            pid = m.get("promo") if isinstance(m, dict) else None
            if pid and (pid, order_id) not in order_seen:
                order_seen.add((pid, order_id))
                deal_map[str(pid)] = deal_map.get(str(pid), 0) + 1
    rows = [
        {
            "promo": p,
            "views": p.views,
            "n_res": p.n_res,
            "n_fulfilled": p.n_fulfilled,
            "n_deals": deal_map.get(str(p.pk), 0),
            "conversion": _conversion(p.n_res + deal_map.get(str(p.pk), 0), p.views),
        }
        for p in promos
    ]
    return render(request, "promotions/analytics.html", {"rows": rows, "nav": "analytics"})


@login_required
def promotion_image_delete(request, pk, image_id):
    promo = get_object_or_404(Promotion, pk=pk)
    if request.method == "POST":
        images = list(promo.images or [])
        kept, removed_primary = [], False
        for img in images:
            if img.get("id") == image_id:
                delete_stored_image(img)
                removed_primary = img.get("is_primary", False)
            else:
                kept.append(img)
        if removed_primary and kept:
            kept[0]["is_primary"] = True
        promo.images = kept
        promo.save(update_fields=["images", "updated_at"])
    return redirect("promotions:promotion-edit", pk=pk)


@login_required
def promotion_image_primary(request, pk, image_id):
    promo = get_object_or_404(Promotion, pk=pk)
    if request.method == "POST":
        images = list(promo.images or [])
        for img in images:
            img["is_primary"] = img.get("id") == image_id
        promo.images = images
        promo.save(update_fields=["images", "updated_at"])
    return redirect("promotions:promotion-edit", pk=pk)


@login_required
def promotion_transition(request, pk):
    promo = get_object_or_404(Promotion, pk=pk)
    if request.method == "POST":
        target = request.POST.get("target", "")
        try:
            PromotionSM().apply(promo, target, actor=request.user)
            messages.success(request, _("Status: %(target)s") % {"target": target})
        except IllegalTransition:
            messages.error(
                request, _("Transition to %(target)s is not allowed.") % {"target": target}
            )
    return redirect("promotions:promotion-edit", pk=pk)


@login_required
def reservation_list(request):
    qs = Reservation.objects.select_related("promotion", "customer").all()
    status = request.GET.get("status", "")
    promotion_id = request.GET.get("promotion", "")
    if status:
        qs = qs.filter(status=status)
    if promotion_id:
        qs = qs.filter(promotion_id=promotion_id)
    # X1: фильтр печатал сырые коды («pending»/«confirmed»); отдаём пары
    # (код, подпись) — те же имена, что в колонке статуса (тег status_label):
    # собственное имя владельца (FB-4b) → встроенная подпись → код.
    from apps.core import transactions

    labels = transactions.builtin_status_labels("reservation")
    tenant = getattr(request, "tenant", None)  # fail-safe: тест-рендер без тенанта
    own = (
        ((getattr(tenant, "site_config", None) or {}).get("status_labels") or {}).get("reservation")
    ) or {}
    status_choices = [
        (code, own.get(code) or labels.get(code, code)) for code in RESERVATION_STATUSES
    ]
    return render(
        request,
        "promotions/reservation_list.html",
        {
            "reservations": qs[:200],
            "statuses": status_choices,
            "status": status,
            "promotions": Promotion.objects.all(),
            "selected_promotion": promotion_id,
            "nav": "reservations",
        },
    )


def _reservation_status_label(status: str) -> str:
    """X1: подпись статуса резерва для сообщений (сырой код в тексте не показываем)."""
    from apps.core import transactions

    return str(transactions.builtin_status_labels("reservation").get(status, status))


def _reservation_failed(action: str, status: str) -> str:
    """X1: полные немецкие фразы на каждое действие — без склейки английских кодов
    (правило i18n проекта: не собирать предложение из кусков)."""
    label = _reservation_status_label(status)
    texts = {
        "confirm": _("Reservierung kann im Status „%(status)s“ nicht bestätigt werden."),
        "fulfill": _("Reservierung kann im Status „%(status)s“ nicht eingelöst werden."),
        "cancel": _("Reservierung kann im Status „%(status)s“ nicht storniert werden."),
    }
    template = texts.get(action, _("Aktion im Status „%(status)s“ nicht möglich."))
    return template % {"status": label}


@login_required
def reservation_action(request, pk):
    res = get_object_or_404(Reservation, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        handler = {
            "confirm": services.confirm,
            "fulfill": services.fulfill,
            "cancel": services.cancel,
        }.get(action)
        if handler is None:
            messages.error(request, _("Unknown action."))
        else:
            try:
                handler(res, actor=request.user)
                # i18n: явные полные сообщения на действие (нельзя склеивать «{action}ed»)
                _res_done = {
                    "confirm": _("Reservation confirmed."),
                    "fulfill": _("Reservation fulfilled."),
                    "cancel": _("Reservation cancelled."),
                }
                messages.success(request, _res_done.get(action, _("Reservation updated.")))
            except IllegalTransition:
                # X1: было английское f-сообщение со СКЛЕЙКОЙ кода действия и сырого
                # статуса — единственная английская фраза среди переведённых соседей.
                messages.error(request, _reservation_failed(action, res.status))
    return redirect("promotions:reservation-list")


# ---------------------------------------------------------------------------
# Погашение брони (Einlösen): скан QR / ручной ввод кода → выдача
# ---------------------------------------------------------------------------


@login_required
def redeem_home(request):
    """Страница погашения: браузерный сканер + ручной ввод кода."""
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().upper()
        if code:
            return redirect("promotions:redeem-detail", code=code)
        messages.error(request, _("Bitte einen Code eingeben."))
    return render(request, "promotions/redeem.html", {"nav": "redeem"})


@login_required
def redeem_detail(request, code):
    code = code.strip().upper()
    res = (
        Reservation.objects.select_related("promotion", "customer")
        .filter(reference_code=code)
        .first()
    )
    # авто-погашение по скану (если включено у бизнеса): сотрудник открыл QR →
    # бронь сразу выдаётся. Идемпотентно (повторный скан выданной — no-op).
    auto = getattr(getattr(request, "tenant", None), "auto_redeem_on_scan", False)
    if res is not None and auto and res.status in ("pending", "confirmed"):
        try:
            if res.status == "pending":
                services.confirm(res, actor=request.user)
            services.fulfill(res, actor=request.user)
            res.refresh_from_db()
            messages.success(request, _("%(code)s: ausgegeben ✓ (Auto)") % {"code": code})
        except IllegalTransition:
            pass
    return render(
        request,
        "promotions/redeem_detail.html",
        {"reservation": res, "code": code, "nav": "redeem"},
    )


@login_required
def redeem_action(request, code):
    code = code.strip().upper()
    res = get_object_or_404(Reservation, reference_code=code)
    if request.method == "POST":
        action = request.POST.get("action", "")
        handler = {
            "confirm": services.confirm,
            "fulfill": services.fulfill,
            "cancel": services.cancel,
        }.get(action)
        if handler is None:
            messages.error(request, _("Unknown action."))
        else:
            try:
                handler(res, actor=request.user)
                # X1: было «CODE: confirm ✓» — английский код действия в немецком UI.
                _done = {
                    "confirm": _("%(code)s: bestätigt ✓"),
                    "fulfill": _("%(code)s: eingelöst ✓"),
                    "cancel": _("%(code)s: storniert ✓"),
                }
                messages.success(
                    request, _done.get(action, _("%(code)s: aktualisiert ✓")) % {"code": code}
                )
            except IllegalTransition:
                messages.error(request, _reservation_failed(action, res.status))
    return redirect("promotions:redeem-detail", code=code)


# ---------------------------------------------------------------------------
# Ваучеры / промокоды
# ---------------------------------------------------------------------------

# Модульный словарь → gettext_LAZY: обычный gettext вычислился бы один раз при
# импорте и заморозил язык первого запроса.
_VOUCHER_ERRORS = {
    "not_found": gettext_lazy("Code nicht gefunden."),
    "inactive": gettext_lazy("Voucher deaktiviert."),
    "expired": gettext_lazy("Voucher abgelaufen."),
    "used_up": gettext_lazy("Voucher bereits eingelöst."),
}


@login_required
def voucher_list(request):
    form = VoucherCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d_eur = form.cleaned_data.get("discount_eur")
        min_eur = form.cleaned_data.get("min_order_eur")
        created = services.generate_vouchers(
            label=form.cleaned_data["label"],
            count=form.cleaned_data["count"],
            max_uses=form.cleaned_data["max_uses"],
            expires_at=form.cleaned_data.get("expires_at"),
            discount_percent=form.cleaned_data.get("discount_percent"),
            discount_cents=int(d_eur * 100) if d_eur else None,
            min_order_cents=int(min_eur * 100) if min_eur else 0,
        )
        messages.success(request, _("%(count)d Voucher erstellt.") % {"count": len(created)})
        return redirect("promotions:voucher-list")
    # B1.3: проданные Geschenkgutscheine (движок G1) — покупатель/номинал/
    # оплата/погашение; код выпускается webhook'ом после оплаты.
    from apps.loyalty.models import GiftVoucher

    gift_sales = GiftVoucher.objects.select_related("voucher").order_by("-created_at")[:100]
    return render(
        request,
        "promotions/vouchers.html",
        {
            "form": form,
            "vouchers": Voucher.objects.all()[:200],
            "gift_sales": gift_sales,
            "nav": "vouchers",
        },
    )


@login_required
def voucher_redeem(request):
    if request.method == "POST":
        try:
            voucher = services.redeem_voucher(request.POST.get("code", ""))
            uses = f" ({voucher.used_count}/{voucher.max_uses})" if voucher.max_uses else ""
            messages.success(request, f"{voucher.code}: {voucher.label} ✓{uses}")
        except services.VoucherError as exc:
            messages.error(request, _VOUCHER_ERRORS.get(exc.reason, exc.reason))
        return redirect("promotions:voucher-redeem")

    code = (request.GET.get("code") or "").strip().upper()
    voucher = Voucher.objects.filter(code=code).first() if code else None
    # авто-погашение по скану, если включено у бизнеса
    auto = getattr(getattr(request, "tenant", None), "auto_redeem_on_scan", False)
    if voucher is not None and auto and voucher.is_redeemable:
        try:
            voucher = services.redeem_voucher(code)
            messages.success(request, f"{voucher.code}: {voucher.label} ✓ (Auto)")
        except services.VoucherError as exc:
            messages.error(request, _VOUCHER_ERRORS.get(exc.reason, exc.reason))
            voucher = Voucher.objects.filter(code=code).first()
    return render(
        request,
        "promotions/voucher_redeem.html",
        {"code": code, "voucher": voucher, "nav": "vouchers"},
    )


# ---------------------------------------------------------------------------
# Лояльность (штампы)
# ---------------------------------------------------------------------------


@login_required
def loyalty_list(request):
    form = LoyaltyProgramForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Programm erstellt."))
        return redirect("promotions:loyalty-list")
    return render(
        request,
        "promotions/loyalty.html",
        {"form": form, "programs": LoyaltyProgram.objects.all(), "nav": "loyalty"},
    )


def _resolve_card(program, *, token="", email=""):
    if token:
        return (
            LoyaltyCard.objects.filter(program=program, token=token)
            .select_related("customer")
            .first()
        )
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is None:
            customer = Customer.objects.create(email=email, name="")
        return services.get_or_create_card(program, customer)
    return None


@login_required
def loyalty_stamp(request, program_id):
    program = get_object_or_404(LoyaltyProgram, pk=program_id)

    if request.method == "POST":
        card = (
            LoyaltyCard.objects.filter(pk=request.POST.get("card_id"))
            .select_related("program")
            .first()
        )
        if card is not None:
            try:
                card, reward = services.add_stamp(card)
                msg = _("Stempel +1 (%(n)s/%(total)s)") % {
                    "n": card.stamps,
                    "total": program.stamps_required,
                }
                if reward is not None:
                    msg += _(" — Belohnung: %(label)s [%(code)s]") % {
                        "label": reward.label,
                        "code": reward.code,
                    }
                messages.success(request, msg)
            except services.LoyaltyError:
                messages.error(request, _("Zu schnell — bitte kurz warten."))
            return redirect(
                f"{reverse('promotions:loyalty-stamp', args=[program.pk])}?card={card.token}"
            )
        messages.error(request, _("Karte nicht gefunden."))
        return redirect("promotions:loyalty-stamp", program_id=program.pk)

    card = _resolve_card(
        program,
        token=(request.GET.get("card") or "").strip(),
        email=(request.GET.get("email") or "").strip().lower(),
    )
    return render(
        request,
        "promotions/loyalty_stamp.html",
        {"program": program, "card": card, "nav": "loyalty"},
    )


@login_required
def coupon_campaigns(request):
    """B4/CM-9: купон-кампании по сегментам — персональный код каждому клиенту
    сегмента + письмо. Только подтвердившим opt-in (UWG §7)."""
    from django.db.models import Count, Sum

    from .forms import CouponCampaignForm
    from .models import CouponCampaign
    from .newsletter import consented_customers, segment_customers, send_coupon_campaign

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            form = CouponCampaignForm(request.POST)
            if form.is_valid():
                d = form.cleaned_data
                CouponCampaign.objects.create(
                    name=d["name"],
                    tag=(d.get("tag") or "").strip().lower(),
                    inactive_days=d.get("inactive_days"),
                    top_ltv=d.get("top_ltv"),
                    discount_percent=d.get("discount_percent"),
                    discount_cents=int(d["discount_eur"] * 100) if d.get("discount_eur") else None,
                    min_order_cents=int(d["min_order_eur"] * 100) if d.get("min_order_eur") else 0,
                    valid_days=d["valid_days"],
                    subject=d["subject"],
                    body=(d.get("body") or "").strip(),
                )
                messages.success(request, _("Kampagne gespeichert."))
            else:
                messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
        elif action == "send":
            campaign = get_object_or_404(
                CouponCampaign,
                pk=request.POST.get("campaign"),
                kind=CouponCampaign.KIND_MANUAL,
            )
            n = send_coupon_campaign(campaign, base_url=request.build_absolute_uri("/").rstrip("/"))
            messages.success(request, _("Kampagne an %(n)s Empfänger gesendet.") % {"n": n})
        elif action == "delete":
            CouponCampaign.objects.filter(
                pk=request.POST.get("campaign"), status=CouponCampaign.STATUS_DRAFT
            ).delete()
        elif action == "winback":
            # B4.4: настройки авто-win-back живут на кампании kind=auto_winback.
            obj = CouponCampaign.objects.filter(kind=CouponCampaign.KIND_AUTO_WINBACK).first()
            if obj is None:
                obj = CouponCampaign.objects.create(
                    kind=CouponCampaign.KIND_AUTO_WINBACK,
                    name="Auto Win-back",
                    subject="Wir vermissen Sie – Ihr persönlicher Gutschein",
                    status=CouponCampaign.STATUS_PAUSED,
                )
            try:
                obj.inactive_days = max(1, int(request.POST.get("inactive_days") or 60))
                obj.discount_percent = max(
                    1, min(100, int(request.POST.get("discount_percent") or 10))
                )
                obj.valid_days = max(1, min(365, int(request.POST.get("valid_days") or 30)))
            except (TypeError, ValueError):
                messages.error(request, _("Bitte gültige Zahlen eingeben."))
                return redirect("promotions:coupon-campaigns")
            obj.subject = (request.POST.get("subject") or obj.subject).strip()[:200]
            obj.status = (
                CouponCampaign.STATUS_ACTIVE
                if request.POST.get("enabled")
                else CouponCampaign.STATUS_PAUSED
            )
            obj.save(
                update_fields=[
                    "inactive_days",
                    "discount_percent",
                    "valid_days",
                    "subject",
                    "status",
                    "updated_at",
                ]
            )
            messages.success(request, _("Auto Win-back gespeichert."))
        elif action == "birthday":
            # PMS-B2: настройки «Geburtstagsgruß» на кампании-синглтоне.
            obj = CouponCampaign.objects.filter(kind=CouponCampaign.KIND_BIRTHDAY).first()
            if obj is None:
                obj = CouponCampaign.objects.create(
                    kind=CouponCampaign.KIND_BIRTHDAY,
                    name="Geburtstagsgruß",
                    subject="Alles Gute zum Geburtstag – Ihr Geschenk wartet",
                    status=CouponCampaign.STATUS_PAUSED,
                )
            try:
                obj.discount_percent = max(
                    1, min(100, int(request.POST.get("discount_percent") or 10))
                )
                obj.valid_days = max(1, min(365, int(request.POST.get("valid_days") or 30)))
            except (TypeError, ValueError):
                messages.error(request, _("Bitte gültige Zahlen eingeben."))
                return redirect("promotions:coupon-campaigns")
            obj.subject = (request.POST.get("subject") or obj.subject).strip()[:200]
            obj.status = (
                CouponCampaign.STATUS_ACTIVE
                if request.POST.get("enabled")
                else CouponCampaign.STATUS_PAUSED
            )
            obj.save(
                update_fields=["discount_percent", "valid_days", "subject", "status", "updated_at"]
            )
            messages.success(request, _("Geburtstagsgruß gespeichert."))
        return redirect("promotions:coupon-campaigns")

    campaigns = list(
        CouponCampaign.objects.annotate(
            issued=Count("vouchers", distinct=True),
            redeemed=Sum("vouchers__used_count"),
        )[:100]
    )
    # Драфтам показываем живой размер сегмента (список капнут — приемлемо).
    for c in campaigns:
        if c.status == CouponCampaign.STATUS_DRAFT:
            c.segment_count = segment_customers(
                tag=c.tag, inactive_days=c.inactive_days, top_ltv=c.top_ltv
            ).count()

    # B4.3: prefill из CRM («Kampagne für diese Auswahl» передаёт ?tag=).
    form = CouponCampaignForm(initial={"tag": (request.GET.get("tag") or "").strip()})
    return render(
        request,
        "promotions/coupon_campaigns.html",
        {
            "nav": "campaigns",
            "campaigns": campaigns,
            "consented": consented_customers().count(),
            "form": form,
            "winback": CouponCampaign.objects.filter(kind=CouponCampaign.KIND_AUTO_WINBACK).first(),
            # PMS-B2: панель «Geburtstagsgruß» + счётчик клиентов с датой рождения.
            "birthday": CouponCampaign.objects.filter(kind=CouponCampaign.KIND_BIRTHDAY).first(),
            "birthday_known": consented_customers().exclude(birthday=None).count(),
            # VF-20b: обратный вход в Акции (экран кампаний был тупиком — ни одной
            # ссылки наружу). Гейт по модулю акций — fail-closed.
            "promotions_active": bool(
                getattr(request, "tenant", None) and request.tenant.is_module_active("promotions")
            ),
        },
    )


@login_required
def newsletter_campaigns(request):
    """G3: рассылки гостям — список кампаний + создание/отправка. Отправляем только
    подтвердившим opt-in (UWG §7)."""
    from .models import NewsletterCampaign
    from .newsletter import consented_customers

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            subject = (request.POST.get("subject") or "").strip()[:200]
            body = (request.POST.get("body") or "").strip()
            if subject and body:
                NewsletterCampaign.objects.create(subject=subject, body=body)
                messages.success(request, _("Entwurf gespeichert."))
            else:
                messages.error(request, _("Bitte Betreff und Text eingeben."))
        elif action == "send":
            from .newsletter import send_campaign

            campaign = get_object_or_404(NewsletterCampaign, pk=request.POST.get("campaign"))
            n = send_campaign(campaign, base_url=request.build_absolute_uri("/").rstrip("/"))
            messages.success(request, _("Newsletter an %(n)s Empfänger gesendet.") % {"n": n})
        elif action == "delete":
            NewsletterCampaign.objects.filter(
                pk=request.POST.get("campaign"), status=NewsletterCampaign.STATUS_DRAFT
            ).delete()
        return redirect("promotions:newsletter")

    return render(
        request,
        "promotions/newsletter.html",
        {
            "nav": "newsletter",  # W7b: своя вкладка в Marketing-хабе
            "campaigns": list(NewsletterCampaign.objects.all()[:100]),
            "consented": consented_customers().count(),
        },
    )
