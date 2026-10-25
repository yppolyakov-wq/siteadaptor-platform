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

import logging

from django.utils.translation import gettext_lazy as _

from . import archetypes, status_registry, transactions

logger = logging.getLogger(__name__)

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
# X6-5 (план cabinet-cleanup §6.A6.5): ПОРЯДОК видов одинаков на всех вкладках —
# Kalender · Board · Liste; меняется только ДОСТУПНОСТЬ (календарный движок есть
# не у каждого kind). Раньше порядок плавал (order: board·liste·kalender,
# ticket: liste·board), и переключатель «прыгал» при смене вкладки.
# Дефолтный вид — отдельная ось (_KIND_DEFAULT/_ARCHETYPE_DEFAULT), не тронут.
KIND_VIEWS = {
    "stay": ("kalender", "board", "liste"),
    "booking": ("kalender", "board", "liste"),
    "order": ("kalender", "board", "liste"),
    "job": ("board", "liste"),
    "ticket": ("board", "liste"),
    "reservation": ("board", "liste"),
}

VIEW_LABELS = {
    "kalender": _("Kalender"),
    "board": _("Spalten"),
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
        if kind == "reservation" and not _has_reservations():
            # VK-8 (фидбэк владельца 2026-08-20): ЕДИНСТВЕННОЕ исключение из
            # правила SM-2a «модуль = вкладка». С волны PL (2026-08-03/04) покупка
            # по акции создаёт ОБЫЧНЫЙ заказ/бронь — витрина в `Reservation`
            # больше не пишет вовсе (форма резерва снята со всех поверхностей).
            # Модуль акций держат ради СКИДОК, поэтому вкладка была вечно пустой:
            # у кейтеринга/отеля/туров резервировать нечего. Показываем её только
            # там, где легаси-резервы реально есть, — иначе пустая вкладка читается
            # как «что-то сломано».
            continue
        out.append(kind)
    return out


def _has_reservations() -> bool:
    """Есть ли у тенанта легаси-резервы по акциям (EXISTS, fail-safe)."""
    try:
        from apps.promotions.models import Reservation

        return Reservation.objects.exists()
    except Exception:  # noqa: BLE001 — вкладка не стоит падения страницы продаж
        return False


def views_for(kind: str, tenant=None) -> tuple:
    """Доступные виды направления. SH-1 (фидбэк владельца 2026-08-20 «календарь не
    нужен, главная страница продаж — список»): у ЗАКАЗОВ календарь — это
    Auftragsbuch по дате выдачи (V3). Магазин слоты выдачи не использует, и вид
    всегда пуст, поэтому показываем его ТОЛЬКО когда слоты реально проставляются
    (данные, а не архетип: у пекарни C&C они есть, у shop — нет)."""
    views = KIND_VIEWS.get(kind, ("board",))
    if kind == "order" and tenant is not None and not _uses_pickup_slots():
        return tuple(v for v in views if v != "kalender")
    return views


def _uses_pickup_slots() -> bool:
    try:
        from apps.orders.models import Order

        return Order.objects.filter(pickup_slot__isnull=False).exists()
    except Exception:  # noqa: BLE001 — вид не стоит падения страницы продаж
        return False


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


def _stay_heute_item(s, *, today, allowed, can_desk):
    """KA-12 Z-5 (Р-9): карточка брони в «Heute» — комнаты, оплата, Meldeschein,
    отметки стойки и POST-кнопки (генерик-поля badges/actions — общие для колонок)."""
    from django.urls import reverse
    from django.utils import timezone

    from apps.core import payment_methods
    from apps.stays import front_desk

    desk = front_desk.state(s, today=today, allowed=allowed)
    rooms = ([s.room.number] if s.room_id else []) + [
        r.number for r in s.extra_rooms.all() if r.id != s.room_id
    ]
    badges = []
    if desk["unconfirmed"]:
        badges.append({"text": _("unbestätigt"), "tone": "amber"})
    if desk["checked_in_at"]:
        t = timezone.localtime(desk["checked_in_at"]).strftime("%H:%M")
        badges.append({"text": _("Eingecheckt %(time)s") % {"time": t}, "tone": "green"})
    if desk["checked_out_at"]:
        t = timezone.localtime(desk["checked_out_at"]).strftime("%H:%M")
        badges.append({"text": _("Ausgecheckt %(time)s") % {"time": t}, "tone": "green"})
    pay = str(s.get_payment_state_display())
    if s.payment_method:
        pay = f"{pay} · {payment_methods.label(s.payment_method)}"
    badges.append({"text": pay, "tone": "gray"})
    meldeschein = str(_("Meldeschein"))
    badges.append({"text": f"{meldeschein} {'✓' if s.has_registration else '—'}", "tone": "gray"})
    actions = []
    if can_desk:
        if desk["can_check_in"]:
            actions.append({"label": _("Check-in"), "action": "check_in", "danger": False})
        if desk["can_check_out"]:
            actions.append({"label": _("Check-out"), "action": "check_out", "danger": True})
    subtitle = str(s.unit)
    if rooms:
        zimmer = str(_("Zimmer"))
        subtitle = f"{subtitle} · {zimmer} {', '.join(rooms)}"
    return {
        "title": s.customer.name or s.customer.email,
        "subtitle": subtitle,
        "url": reverse("stays:booking-detail", args=[s.pk]),
        "badges": badges,
        "actions": actions,
        "action_url": reverse("stays:stay-action", args=[s.pk]),
    }


def heute_columns(tenant, user=None) -> list[dict]:
    """W10-4: kind-агностичный вид «Heute» — операционный ответ на «что сегодня»:
    заезды/выезды (stays — одна точка `front_desk.today_lists`, её же читает виджет
    главной), записи (booking), выдача/доставка (orders, status=ready). Колонки
    гейтятся модулями; KA-12 Z-5 (DF-Z4): ошибка колонки логируется и показывается
    как «Konnte nicht geladen werden», а не как пустой день."""
    from django.urls import reverse
    from django.utils import timezone

    today = timezone.localdate()
    cols = []

    def _safe(key, fn):
        """(items, error): сломанная колонка одного модуля не валит «Heute»."""
        try:
            return fn(), False
        except Exception:  # noqa: BLE001 — колонка одного модуля не валит «Heute»
            logger.exception("heute column %s failed", key)
            return [], True

    def _col(key, icon, label, fn, **extra):
        items, error = _safe(key, fn)
        return {"key": key, "icon": icon, "label": label, "items": items, "error": error, **extra}

    if tenant.is_module_active("stays"):
        from apps.core.permissions import has_perm
        from apps.stays import front_desk
        from apps.stays.models import StaySettings

        can_desk = user is not None and has_perm(user, "rezeption.edit")

        def _lists():
            return front_desk.today_lists(tenant, today), front_desk.checkin_allowed_statuses(
                tenant
            )

        lists, lists_error = _safe("stays", _lists)

        def _stay_col(name):
            if lists_error:
                raise RuntimeError("stays lists unavailable")
            qs, allowed = lists[0][name], lists[1]
            return [
                _stay_heute_item(s, today=today, allowed=allowed, can_desk=can_desk)
                for s in qs[: front_desk.LIST_LIMIT]
            ]

        checkin_hour, checkout_hour = _safe("stays_hours", StaySettings.hours)[0] or (15, 14)
        cols.append(
            _col(
                "anreise",
                "🛎",
                _("Anreisen heute"),
                lambda: _stay_col("arrivals"),
                hint=_("Check-in ab %(h)s:00") % {"h": checkin_hour},
            )
        )
        cols.append(
            _col(
                "abreise",
                "🧳",
                _("Abreisen heute"),
                lambda: _stay_col("departures"),
                hint=_("Check-out bis %(h)s:00") % {"h": checkout_hour},
            )
        )
        # W10-6: паритет со stays:today — «Im Haus» (живут сейчас).
        cols.append(_col("im_haus", "🏠", _("Im Haus"), lambda: _stay_col("in_house")))
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

        cols.append(_col("termine", "📅", _("Termine heute"), _termine))
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

        cols.append(_col("abholung", "📦", _("Abholbereit"), lambda: _ready(delivery=False)))
        lieferungen, lieferungen_error = _safe("lieferung", lambda: _ready(delivery=True))
        if lieferungen or lieferungen_error or getattr(tenant, "delivery_enabled", False):
            cols.append(
                {
                    "key": "lieferung",
                    "icon": "🚚",
                    "label": _("Lieferungen heute"),
                    "items": lieferungen,
                    "error": lieferungen_error,
                }
            )
    return cols


def legacy_redirect(request, _url_name="verkaeufe", **params):
    """W10-6: 302 с легаси-страницы продаж на Verkäufe С СОХРАНЕНИЕМ GET
    (deep-links ?status=/?von=/?tag=/?q=/?buchung= живут на цели). params
    задают вкладку/вид и перекрывают одноимённые GET-ключи; значение None
    УДАЛЯЕТ ключ (X2b: у доски параметр звался `?kind=`, у единой страницы —
    `?tab=`, тащить оба в адрес незачем). KA-12 E8.6: `_url_name` — цель (по умолчанию
    единая страница продаж; лендинги Marketing/Integrationen ведут на свои экраны)."""
    from django.http import HttpResponseRedirect
    from django.urls import reverse

    get = request.GET.copy()
    for k, v in params.items():
        if v is None:
            get.pop(k, None)
        else:
            get[k] = v
    qs = get.urlencode()
    return HttpResponseRedirect(reverse(_url_name) + (f"?{qs}" if qs else ""))


# SH-15 (фидбэк владельца 2026-08-20 «нет нигде списка клиентов», решение
# «вкладка в Продажах всем»): последняя вкладка страницы продаж — не направление
# сделок, а КЛИЕНТЫ. Данные и тело — те же, что на экране CRM (один партиал,
# один контекст), поэтому расхождению взяться неоткуда.
KUNDEN_TAB = "kunden"


def shows_customers(tenant) -> bool:
    """Вкладка клиентов есть у ВСЕХ архетипов (решение владельца 2026-08-20:
    «вкладка в Продажах всем», НЕ «включить CRM всем»). Клиент заводится любой
    продажей, поэтому список — базовая вещь; модуль crm остаётся гейтом
    расширенного CRM (карточка, теги, заметки, сегменты, экспорт)."""
    return True


def tab_descriptors(tenant, active_kind: str) -> list[dict]:
    """Вкладки направлений. VS-2a (решение владельца 2026-08-20): у 13 из 16 типов
    бизнеса направление ОДНО — ряд вкладок из одного элемента шаблон не рисует
    вовсе (заголовок страницы = имя направления). При двух+ вкладка несёт число
    АКТИВНЫХ сделок: видно, где работа, не переключаясь."""
    kinds = visible_kinds(tenant)
    counts = _active_counts(tenant, kinds) if len(kinds) > 1 else {}
    tabs = [
        {
            "kind": kind,
            "label": transactions.KIND_LABEL.get(kind, kind),
            "active": kind == active_kind,
            "count": counts.get(kind),
        }
        for kind in kinds
    ]
    return tabs


def customers_allowed(tenant, user) -> bool:
    """E6.7e: вкладка клиентов — по праву ``kunden.view`` (view_perms.QUERY_RULES —
    тот же источник, что скрывает её в меню); без него список клиентов не отдаём."""
    from apps.core import permissions, view_perms

    return shows_customers(tenant) and (
        user is None
        or not permissions.is_member(user)
        or view_perms.query_allowed(user, "verkaeufe", f"?tab={KUNDEN_TAB}")
    )


def customers_tab(tenant, active_kind: str, user=None) -> dict | None:
    """Вкладка «Kunden» — отдельно от направлений сделок: ряд вкладок остаётся
    рядом НАПРАВЛЕНИЙ (VS-2a: одинокое направление ряда не рисует), а клиенты
    примыкают к нему справа. Гейт — право ``kunden.view``."""
    if not customers_allowed(tenant, user):
        return None
    return {"kind": KUNDEN_TAB, "label": _("Kunden"), "active": active_kind == KUNDEN_TAB}


def _active_counts(tenant, kinds) -> dict:
    """{kind: число незакрытых сделок} — один COUNT на направление, fail-safe.
    «Активные» = не терминальные (реестр статусов, с учётом кастомных SM-3)."""
    out = {}
    for kind in kinds:
        try:
            model = transactions.model_for(kind)
            terminal = _terminal_statuses(kind, tenant)
            out[kind] = model.objects.exclude(status__in=terminal).count()
        except Exception:  # noqa: BLE001 — счётчик не стоит падения страницы
            continue
    return out


def _terminal_statuses(kind: str, tenant) -> list[str]:
    return [
        code
        for code, d in status_registry.all_descriptors(kind, tenant).items()
        if d.stage == "terminal"
    ]


def view_descriptors(tenant, kind: str, active_view: str) -> list[dict]:
    return [
        {
            "view": view,
            "label": VIEW_LABELS[view],
            "icon": VIEW_ICONS[view],
            "active": view == active_view,
        }
        for view in views_for(kind, tenant)
    ]


# Какие GET-фильтры тело вида ДЕЙСТВИТЕЛЬНО исполняет (остальные оно молча
# игнорирует). Ревью 2026-08-19: адрес с фильтром, который вид не понимает,
# показывал ВСЕ сделки — владелец считал их отфильтрованными (легаси-редирект
# заявок ?status=, виджет «Abholbereit» ?status=ready).
_VIEW_FILTERS = {
    # SH-14: `versand` (только доставка) исполняет список заказов.
    ("liste", "order"): frozenset({"q", "status", "versand", "abholung", "zahlung"}),
    ("liste", None): frozenset({"q", "status"}),
    ("kalender", "stay"): frozenset({"q"}),  # Belegungsplan ищет сам
}


def honored_filters(kind: str, view: str) -> frozenset:
    """Фильтры, которые исполняет тело (view, kind)."""
    return _VIEW_FILTERS.get((view, kind)) or _VIEW_FILTERS.get((view, None)) or frozenset()


def view_for_filters(kind: str, view: str, params) -> str:
    """Вид, который ИСПОЛНИТ фильтры адреса: если текущий их не понимает —
    «Liste» (единственный вид с полным набором). Явный `heute` не трогаем —
    он kind-агностичен и приходит из deep-link виджетов."""
    if view == "heute":
        return view
    wanted = {
        p
        for p in ("q", "status", "versand", "abholung", "zahlung")
        if (params.get(p) or "").strip()
    }
    if wanted and not wanted <= honored_filters(kind, view) and "liste" in KIND_VIEWS.get(kind, ()):
        return "liste"
    return view


def _contact_search(request) -> bool:
    """E6.7g: искать по e-mail клиента — только с правом видеть контакты."""
    from apps.core import contact_access as contacts

    return contacts.can_see(getattr(request, "user", None))


def order_list_queryset(params, contact_search: bool = True):
    """Выборка списка заказов по GET (KA-12 E2.2: одна точка для списка и CSV).

    Возвращает (qs, status, q, versand, sort)."""
    from django.db.models import Q

    from apps.orders import counters as order_counters
    from apps.orders.models import Order

    # W10-3: паритет с /dashboard/orders/ — фильтр статуса + поиск (код/имя/
    # email); deep-link «Abholbereit» главной ведёт сюда (?status=ready).
    qs = Order.objects.select_related("customer").prefetch_related("items")
    status = params.get("status", "")
    if status:
        qs = qs.filter(status=status)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(reference_code__icontains=q)
            | Q(external_code__icontains=q)  # SH-8: внешний номер
            | Q(customer__name__icontains=q)
            | (Q(customer__email__icontains=q) if contact_search else Q(pk__in=[]))
        )
    # SH-14: доставка — фильтр списка заказов (подпункт сайдбара «Lieferungen»).
    versand = (params.get("versand") or "").strip() == "1"
    if versand:
        # is_delivery — свойство модели, не поле: фильтруем по способу выдачи.
        qs = qs.filter(fulfillment=Order.FULFILLMENT_DELIVERY)
    # KA-12 E2.5: фильтры счётчиков главной (тот же Q, что у счётчика).
    qs = order_counters.apply_list_filters(qs, params)
    # KA-12 E2.3: сортировка по белому списку (тот же словарь, что у generic).
    sort = transactions.clean_sort("order", params.get("sort"))
    if sort:
        qs = qs.order_by(*transactions._sort_orderings("order")[sort])
    return qs, status, q, versand, sort


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
    if kind == KUNDEN_TAB:
        if not customers_allowed(tenant, getattr(request, "user", None)):
            return {}  # E6.7e: без kunden.view — без списка клиентов
        # SH-15: тот же контекст, что у экрана CRM (crm.views.customer_list_context).
        # `crm_active` гейтит ссылки на карточку/экспорт/компании: без модуля они
        # упёрлись бы в гейт путей (404) — класс дефекта из сверки 2026-08-19.
        from apps.crm.views import customer_list_context

        return {**customer_list_context(request), "crm_active": tenant.is_module_active("crm")}
    if view == "heute":
        ctx["heute_columns"] = heute_columns(tenant, getattr(request, "user", None))
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
        # VS-2c: на доске порядок — по дате события (ближайшее сверху).
        ctx["sections"] = transactions.manage_sections_for(
            tenant, only=kind, board_order=True, per_column=transactions.BOARD_COLUMN_LIMIT
        )
    elif kind == "order":  # Liste заказов — богатые строки списка orders
        from apps.orders import counters as order_counters
        from apps.orders.models import Order

        qs, status, q, versand, sort = order_list_queryset(
            request.GET, contact_search=_contact_search(request)
        )
        ctx["order_versand"] = versand
        ctx["order_counter_filter"] = order_counters.active_label(request.GET)
        ctx["list_sort"] = sort
        ctx["list_sort_options"] = transactions.list_sort_options("order")
        # SH-11 (фидбэк владельца 2026-08-20 «в списке позволить менять статус»):
        # к строке заказа привязываем переходы FSM — тот же слой, что у доски
        # (allowed_actions_for + правила владельца FB-3), поэтому список не
        # заводит СВОЮ логику переходов.
        from apps.core import pipeline, transition_rules

        subset = transition_rules.subset_for(tenant, "order")
        # KA-P4a: раньше молча 200 — 201-й заказ был не найти. Теперь страницы по 50.
        from apps.core.pagination import paginate_queryset

        page = paginate_queryset(qs, page_raw=request.GET.get("seite"))
        ctx["page"] = page
        orders = page.items
        from apps.core import status_labels

        labels = status_labels.custom_labels(tenant, "order")
        for o in orders:
            o.row_actions = transactions.allowed_actions_for("order", o.status, subset, obj=o)
            o.row_stage = pipeline.stage_for("order", o.status)
            # KA-12 E2.4: peek строки — те же данные Transaction, что у Liste/доски.
            o.tx = transactions.transaction_for("order", o, labels, subset)
        ctx["orders"] = orders
        ctx["order_peek"] = True
        # KA-12 E2.1: массовые действия — варианты = объединение переходов строк
        # страницы (JS сужает до пересечения выбранных; сервер проверит заново).
        ctx["bulk_kind"] = "order"
        ctx["bulk_options"] = _bulk_options("order", [o.row_actions for o in orders])
        # X4 (§6.A4.5): KDS/Tisch-QR — гастро-инструменты; раньше кнопки видел
        # любой архетип с модулем orders (парикмахер — «Kitchen Display»).
        # KA-12 E0.3 (KA-5a B5): тот же гейт, что у записей реестра навигации — KDS только
        # кухням (cafe/catering/restaurant), Tisch-QR только залам; пекарне/мясной — нет.
        from apps.core.nav_registry import KITCHEN_TYPES, TABLE_TYPES

        btype = getattr(tenant, "business_type", "") or ""
        ctx["show_kds"] = btype in KITCHEN_TYPES
        ctx["show_table_qr"] = btype in TABLE_TYPES
        ctx["order_statuses"] = Order.STATUSES
        ctx["order_status"] = status
        ctx["order_q"] = q
    else:  # generic Liste по нормализованным транзакциям kind
        # W7c: список — по дате СОБЫТИЯ (заезд/начало), не по дате создания:
        # «сегодняшние брони» иначе тонули под старыми, созданными позже.
        # X6-2: поиск (код/клиент) был только у заказов — теперь у всех kind.
        q = (request.GET.get("q") or "").strip()
        # X2c: фильтр статуса в generic-списке — паритет с легаси-страницей
        # заявок (там он был чипами) ДО её схлопывания (правило W10-6).
        status = (request.GET.get("status") or "").strip()
        options = transactions.status_filter_options(tenant, kind)
        if status not in {code for code, _label in options}:
            status = ""
        # KA-12 E2.3: сортировка `?sort=` по белому списку вида.
        sort = transactions.clean_sort(kind, request.GET.get("sort"))
        ctx["list_sort"] = sort
        ctx["list_sort_options"] = transactions.list_sort_options(kind)
        sections = transactions.manage_sections_for(
            tenant,
            only=kind,
            event_order=True,
            q=q,
            status=status,
            page_raw=request.GET.get("seite") or "1",
            sort=sort,
            contact_search=_contact_search(request),
        )
        ctx["section"] = sections[0] if sections else None
        ctx["page"] = ctx["section"]["page"] if ctx["section"] else None
        if ctx["section"]:
            bulk = _bulk_options(
                kind, [tx.allowed_actions for tx in ctx["section"]["transactions"]]
            )
            # Без вариантов нет панели — и чекбоксы не рисуем (ревью E2.1).
            if bulk:
                ctx["bulk_kind"] = kind
                ctx["bulk_options"] = bulk
        ctx["list_q"] = q
        ctx["list_status"] = status
        ctx["list_status_options"] = options
    return ctx


def _bulk_options(kind: str, row_actions) -> list[dict]:
    """KA-12 E2.1: объединение переходов строк (без целей, которые массово не ставим)."""
    from apps.core.bulk_actions import NOT_BULK

    seen: dict = {}
    for actions in row_actions:
        for a in actions or ():
            if a["target"] not in seen and a["target"] not in NOT_BULK.get(kind, ()):
                seen[a["target"]] = a
    return list(seen.values())


def create_target(kind: str, customers: bool = False) -> str:
    """W10-3/KA-12 E8.8: куда ведёт «＋» направления (пусто — у kind нет формы создания:
    walk-in формы живут в телах календарных движков). Один источник для тулбара
    Verkäufe и мобильного таб-бара."""
    from django.urls import reverse

    if customers:
        return reverse("crm:customer-create")
    if kind == "stay":
        return reverse("stays:stay-new")
    if kind == "booking":
        return reverse("verkaeufe") + "?tab=booking&view=kalender#neu"
    if kind == "job":
        return reverse("jobs:new")  # X2c: ручная заявка (звонок/визит)
    return ""


def tabbar_create_target(tenant, user=None) -> str:
    """KA-12 E8.8: «＋» таб-бара — создать по главному направлению тенанта; где формы
    нет (заказы/билеты) — быстрая акция, если модуль акций включён; иначе кнопки нет.
    Без запросов: primary_module читает конфиг тенанта."""
    kind = _MODULE_KIND.get(archetypes.primary_module(tenant) or "", "")
    url = create_target(kind)
    if not url and tenant.is_module_active("promotions"):
        from django.urls import reverse

        url = reverse("promotions:promotion-quick")
    from apps.core import view_perms

    # E6.7e: «＋» ведёт к созданию — кнопка только при праве записи этого экрана.
    return url if view_perms.url_allowed(user, url, "POST") else ""
