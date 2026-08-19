"""Единая страница продаж «Verkäufe» — вкладки по kind + виды (2026-08-03).

Решения владельца (план `docs/unified-sales-page-plan-2026-08-03.md §4`):
вкладки (не стек); полные виды, неактивные вкладки не грузятся (переключение —
обычная навигация `?tab=`); первая вкладка = kind primary-модуля и видна
ВСЕГДА, прочие — только при наличии продаж (`transactions.kinds_with_sales`).
W10-2 (решение Р-4, 2026-08-05): `reservation` подчиняется ОБЩЕМУ правилу
«вкладка с первой продажей» — заявки клиентов больше не спрятаны в Marketing
(вход оттуда остаётся дублем до W11).

Дефолтный вид зависит от АРХЕТИПА, не от kind (рыночная норма: салону —
календарь, Handwerker'у — пайплайн, магазину — список; план §1).
"""

from django.utils.translation import gettext_lazy as _

from . import archetypes, status_registry, transactions

# Модуль → kind сделки. `_PRIORITY` архетипов оперирует модулями; продажи
# каталога живут в модуле orders (catalog в _PRIORITY — это ОН).
_MODULE_KIND = {
    "events": "ticket",
    "stays": "stay",
    "booking": "booking",
    "jobs": "job",
    "catalog": "order",
    "promotions": "reservation",
}

# kind → доступные виды по порядку отображения. `kalender` есть только там, где
# существует календарный движок (stay: Belegungsplan, booking: Tagesplan,
# order: Auftragsbuch по дате выдачи — V3).
KIND_VIEWS = {
    "stay": ("kalender", "board", "liste"),
    "booking": ("kalender", "board", "liste"),
    "order": ("board", "liste", "kalender"),
    "job": ("board", "liste"),
    "ticket": ("liste", "board"),
    "reservation": ("liste", "board"),
}

VIEW_LABELS = {
    "kalender": _("Kalender"),
    "board": _("Board"),
    "liste": _("Liste"),
}
VIEW_ICONS = {"kalender": "📅", "board": "🧮", "liste": "📃"}

# Архетипный дефолт вида на kind (план §3.3/§3.5): у kind primary-модуля —
# рыночная норма архетипа; у вторичных — собственная норма kind.
_KIND_DEFAULT = {
    "stay": "kalender",
    "booking": "kalender",
    "order": "liste",
    "job": "board",
    "ticket": "liste",
    "reservation": "liste",
}
# Точечные overrides: (business_type, kind) → вид. Гастро-C&C живёт очередью
# (KDS-паттерн), ритейл-заказы — списком.
_ARCHETYPE_DEFAULT = {
    ("restaurant", "order"): "board",
    ("cafe", "order"): "board",
}


def default_view(tenant, kind: str) -> str:
    view = _ARCHETYPE_DEFAULT.get((getattr(tenant, "business_type", ""), kind))
    return view or _KIND_DEFAULT.get(kind, "board")


def visible_kinds(tenant) -> list[str]:
    """Вкладки страницы: primary-kind первым, дальше — kind КАЖДОГО активного
    модуля в порядке `_PRIORITY`.

    SM-2 (решение владельца 2026-08-10): вкладка на каждый активный модуль
    СРАЗУ, не «с первой продажей» — верхний уровень продаж = модули бизнеса.
    Прежний гейт «kinds_with_sales» прятал направление, пока не пришла первая
    продажа, и владелец не видел, куда она придёт."""
    primary = _MODULE_KIND.get(archetypes.primary_module(tenant))
    # W7c (аудит 2026-08-05): маппинг catalog→order кросс-модульный (catalog core,
    # orders может быть выключен) — без гейта у тенанта business_type=other
    # открывалась вкладка «Bestellungen» при выключенном модуле заказов, а её
    # «Alte Ansicht» вела в 404.
    if primary and not tenant.is_module_active(transactions.KIND_MODULE[primary]):
        primary = None
    out = []
    if primary:
        out.append(primary)
    for module in archetypes._PRIORITY:
        kind = _MODULE_KIND[module]
        if kind in out or not tenant.is_module_active(transactions.KIND_MODULE[kind]):
            continue
        out.append(kind)
    return out


def resolve_view(tenant, kind: str, requested: str = "") -> str:
    """Вид вкладки: явный `?view=` → сохранённый выбор → архетипный дефолт.
    Недоступный для kind вид молча падает на первый доступный."""
    allowed = KIND_VIEWS.get(kind, ("board",))
    saved = (tenant.site_config or {}).get("sales_views", {})
    for candidate in (
        requested,
        saved.get(kind) if isinstance(saved, dict) else "",
        default_view(tenant, kind),
    ):
        if candidate in allowed:
            return candidate
    return allowed[0]


def heute_columns(tenant) -> list[dict]:
    """W10-4: kind-агностичный вид «Heute» — операционный ответ на «что сегодня»:
    заезды/выезды (stays, семантика = виджет PMS-A2), записи (booking), выдача/
    доставка (orders, status=ready). Колонки гейтятся модулями и fail-safe
    (сломанный блок не валит страницу); карточка ведёт на родную деталь."""
    from django.urls import reverse
    from django.utils import timezone

    today = timezone.localdate()
    cols = []

    def _safe(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 — колонка одного модуля не валит «Heute»
            return []

    if tenant.is_module_active("stays"):
        from apps.stays.models import StayBooking

        def _stay_items(qs):
            return [
                {
                    "title": s.customer.name or s.customer.email,
                    "subtitle": str(s.unit),
                    "url": reverse("stays:booking-detail", args=[s.pk]),
                }
                for s in qs.select_related("customer", "unit")[:50]
            ]

        cols.append(
            {
                "key": "anreise",
                "icon": "🛎",
                "label": _("Anreisen heute"),
                # SM-3: «активные» через реестр — заезд в кастом-статусе виден в Heute.
                "items": _safe(
                    lambda: _stay_items(
                        StayBooking.objects.filter(
                            arrival=today,
                            status__in=status_registry.active_statuses_for("stay", tenant),
                        )
                    )
                ),
            }
        )
        cols.append(
            {
                "key": "abreise",
                "icon": "🧳",
                "label": _("Abreisen heute"),
                "items": _safe(
                    lambda: _stay_items(
                        StayBooking.objects.filter(
                            departure=today, status=StayBooking.STATUS_CONFIRMED
                        )
                    )
                ),
            }
        )
        # W10-6: паритет со stays:today — «Im Haus» (живут сейчас) обязателен
        # ДО редиректа легаси-страницы (аудит-урок «не схлопывать до паритета»).
        cols.append(
            {
                "key": "im_haus",
                "icon": "🏠",
                "label": _("Im Haus"),
                "items": _safe(
                    lambda: _stay_items(
                        StayBooking.objects.filter(
                            arrival__lt=today,
                            departure__gt=today,
                            status=StayBooking.STATUS_CONFIRMED,
                        )
                    )
                ),
            }
        )
    if tenant.is_module_active("booking"):
        from apps.booking.models import Booking

        def _termine():
            out = []
            qs = (
                Booking.objects.filter(
                    start__date=today,
                    status__in=status_registry.active_statuses_for("booking", tenant),
                )
                .select_related("customer", "resource", "service")
                .order_by("start")[:50]
            )
            for b in qs:
                when = timezone.localtime(b.start).strftime("%H:%M")
                what = str(b.service) if b.service_id else str(b.resource)
                out.append(
                    {
                        "title": f"{when} · {b.customer.name or b.customer.email}",
                        "subtitle": what,
                        "url": reverse("booking:booking-detail", args=[b.pk]),
                    }
                )
            return out

        cols.append(
            {"key": "termine", "icon": "📅", "label": _("Termine heute"), "items": _safe(_termine)}
        )
    if tenant.is_module_active("orders"):
        from apps.orders.models import Order

        def _ready(delivery: bool):
            out = []
            qs = Order.objects.filter(status="ready").select_related("customer")[:100]
            for o in qs:
                if bool(o.is_delivery) is not delivery:
                    continue
                out.append(
                    {
                        "title": o.reference_code,
                        "subtitle": o.customer.name if o.customer_id else "",
                        "url": reverse("orders:order-detail", args=[o.pk]),
                    }
                )
            return out[:50]

        cols.append(
            {
                "key": "abholung",
                "icon": "📦",
                "label": _("Abholbereit"),
                "items": _safe(lambda: _ready(delivery=False)),
            }
        )
        lieferungen = _safe(lambda: _ready(delivery=True))
        if lieferungen or getattr(tenant, "delivery_enabled", False):
            cols.append(
                {
                    "key": "lieferung",
                    "icon": "🚚",
                    "label": _("Lieferungen heute"),
                    "items": lieferungen,
                }
            )
    return cols


def legacy_redirect(request, **params):
    """W10-6: 302 с легаси-страницы продаж на Verkäufe С СОХРАНЕНИЕМ GET
    (deep-links ?status=/?von=/?tag=/?q=/?buchung= живут на цели). params
    задают вкладку/вид и перекрывают одноимённые GET-ключи; значение None
    УДАЛЯЕТ ключ (X2b: у доски параметр звался `?kind=`, у единой страницы —
    `?tab=`, тащить оба в адрес незачем)."""
    from django.http import HttpResponseRedirect
    from django.urls import reverse

    get = request.GET.copy()
    for k, v in params.items():
        if v is None:
            get.pop(k, None)
        else:
            get[k] = v
    qs = get.urlencode()
    return HttpResponseRedirect(reverse("verkaeufe") + (f"?{qs}" if qs else ""))


def tab_descriptors(tenant, active_kind: str) -> list[dict]:
    return [
        {
            "kind": kind,
            "label": transactions.KIND_LABEL.get(kind, kind),
            "active": kind == active_kind,
        }
        for kind in visible_kinds(tenant)
    ]


def view_descriptors(tenant, kind: str, active_view: str) -> list[dict]:
    return [
        {
            "view": view,
            "label": VIEW_LABELS[view],
            "icon": VIEW_ICONS[view],
            "active": view == active_view,
        }
        for view in KIND_VIEWS.get(kind, ("board",))
    ]


def body_context(request, kind: str, view: str) -> dict:
    """X3: контекст ТЕЛА поверхности продаж (движок по (view, kind)).

    Один источник для страницы `Verkäufe` и для главной кабинета, которая
    показывает ту же рабочую петлю архетипа (вариант B плана cabinet-cleanup).
    Возвращает dict; для stay-календаря может вернуть HttpResponse — это
    fetch-фрагмент карточки брони (`?box=1`), вызывающий обязан его отдать.
    """
    from apps.core import transactions

    tenant = request.tenant
    ctx: dict = {}
    if view == "heute":
        ctx["heute_columns"] = heute_columns(tenant)
    elif view == "kalender" and kind == "stay":
        from apps.stays.views import calendar_context as stays_calendar_context

        sub = stays_calendar_context(request)
        if not isinstance(sub, dict):  # ?box=1 — fetch-фрагмент карточки брони
            return sub
        ctx = {**sub, **ctx}
    elif view == "kalender" and kind == "booking":
        from apps.booking.views import calendar_context as booking_calendar_context

        ctx = {**booking_calendar_context(request), **ctx}
    elif view == "kalender" and kind == "order":  # V3: Auftragsbuch
        from apps.orders.views import auftragsbuch_context

        ctx = {**auftragsbuch_context(request), **ctx}
    elif view == "board":
        ctx["sections"] = transactions.manage_sections_for(tenant, only=kind)
    elif kind == "order":  # Liste заказов — богатые строки списка orders
        from django.db.models import Q

        from apps.orders.models import Order

        # W10-3: паритет с /dashboard/orders/ — фильтр статуса + поиск (код/имя/
        # email); deep-link «Abholbereit» главной ведёт сюда (?status=ready).
        qs = Order.objects.select_related("customer").prefetch_related("items")
        status = request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(reference_code__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__email__icontains=q)
            )
        ctx["orders"] = qs[:200]
        ctx["order_statuses"] = Order.STATUSES
        ctx["order_status"] = status
        ctx["order_q"] = q
    else:  # generic Liste по нормализованным транзакциям kind
        # W7c: список — по дате СОБЫТИЯ (заезд/начало), не по дате создания:
        # «сегодняшние брони» иначе тонули под старыми, созданными позже.
        sections = transactions.manage_sections_for(tenant, limit=200, only=kind, event_order=True)
        ctx["section"] = sections[0] if sections else None
    return ctx
