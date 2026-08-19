"""Виджеты и хаб-плитки главной кабинета `/dashboard/`.

X2a: `dashboard_tiles` (task-плитки AB7) удалены — их заменили виджеты «что
сегодня» + чек-лист готовности (ST-4a); функция висела мёртвой с 2026-07-19.
"""


def _sparkline_points(days, width=120, height=32) -> str:
    """ST-4a: точки SVG-polyline из дневных сумм (первый чарт кабинета).

    Нормируем к максимуму (все нули → плоская линия у низа); отступ 2px сверху/
    снизу, чтобы линия не резалась о край viewBox."""
    if not days:
        return ""
    mx = max(float(v) for v in days) or 1.0
    n = len(days)
    step = width / (n - 1) if n > 1 else float(width)
    pts = []
    for i, v in enumerate(days):
        x = round(i * step, 1)
        y = round(height - 2 - (float(v) / mx) * (height - 4), 1)
        pts.append(f"{x},{y}")
    return " ".join(pts)


def home_widgets(tenant) -> list[dict]:
    """ST-4a: виджеты «что сегодня» главной кабинета (план st4-admin-home-plan §1).

    Паттерн digest.collect_digest: per-module гейты + fail-safe —
    упавший источник не роняет главную. → [{key, icon, label, value, hint,
    url_name, url_query, sparkline}] (sparkline — только у Umsatz)."""
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone
    from django.utils.translation import gettext as _t

    from apps.core.digest import _safe

    today = timezone.localdate()
    widgets: list[dict] = []

    # 💶 Umsatz heute + 7-дневный спарклайн + сравнение с прошлой неделей (X3).
    if tenant.is_module_active("finance"):

        def _revenue_days(n=14):
            """Суммы по дням за n дней (последний элемент — сегодня)."""
            from django.db.models import Sum

            from apps.finance.models import RevenueEntry

            start = today - timedelta(days=n - 1)
            rows = dict(
                RevenueEntry.objects.filter(date__gte=start)
                .values("date")
                .annotate(s=Sum("amount"))
                .values_list("date", "s")
            )
            return [rows.get(start + timedelta(days=i)) or Decimal("0") for i in range(n)]

        # X3: берём 14 дней одним запросом — вторая неделя нужна для сравнения
        # «vs прошлая неделя» (паттерн SumUp: число дня отвечает «лучше/хуже»).
        fortnight = _safe(lambda: _revenue_days(14), [Decimal("0")] * 14)
        days, prev_days = fortnight[7:], fortnight[:7]
        this_week, last_week = sum(days), sum(prev_days)
        if last_week:
            delta = round(100 * (this_week - last_week) / last_week)
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "→")
            hint = _t("Woche: %(arrow)s %(delta)s %% vs. Vorwoche") % {
                "arrow": arrow,
                "delta": abs(delta),
            }
        else:
            hint = _t("letzte 7 Tage")
        widgets.append(
            {
                "key": "umsatz",
                "icon": "💶",
                "label": _t("Umsatz heute"),
                "value": f"{days[-1]:.2f} €".replace(".", ","),
                "hint": hint,
                "url_name": "finance:journal",
                "url_query": "",
                "sparkline": _sparkline_points(days),
            }
        )
    else:
        # X3: раньше виджет выручки просто ИСЧЕЗАЛ у тенанта без модуля finance
        # (а он выключен по умолчанию у ВСЕХ типов) — владелец не мог узнать, что
        # выручку нужно «включить». Честная карточка вместо пустоты.
        widgets.append(
            {
                "key": "finance_off",
                "icon": "💶",
                "label": _t("Umsatz"),
                "value": "—",
                "hint": _t("Finanzen aktivieren"),
                "url_name": "modules",
                "url_query": "",
                "sparkline": "",
            }
        )

    # 📦 Abholbereit (orders ready) — «заказы к выдаче».
    if tenant.is_module_active("orders"):

        def _ready():
            from apps.orders.models import Order

            return Order.objects.filter(status=Order.STATUS_READY).count()

        widgets.append(
            {
                "key": "ready",
                "icon": "📦",
                "label": _t("Abholbereit"),
                "value": str(_safe(_ready, 0)),
                "hint": _t("Bestellungen fertig zur Abholung"),
                # W10-3: deep-link на единую страницу (Liste заказов понимает
                # ?status= — легаси-список больше не нужен для этого).
                "url_name": "verkaeufe",
                "url_query": "?tab=order&status=ready",
                "sparkline": "",
            }
        )

    # 🛎 Anreisen heute (PMS-A2): стойка отеля/пансиона — сегодняшние заезды,
    # в hint выезды; клик ведёт на экран «Heute».
    if tenant.is_module_active("stays"):

        def _stays_today():
            from django.utils import timezone as _tz

            from apps.core import status_registry
            from apps.stays.models import StayBooking

            today = _tz.localdate()
            # SM-3: «активные» через реестр — бронь в кастом-статусе видна в виджете.
            arrivals = StayBooking.objects.filter(
                arrival=today, status__in=status_registry.active_statuses_for("stay", tenant)
            ).count()
            departures = StayBooking.objects.filter(
                departure=today, status=StayBooking.STATUS_CONFIRMED
            ).count()
            return arrivals, departures

        arrivals_n, departures_n = _safe(_stays_today, (0, 0))
        widgets.append(
            {
                "key": "stays_today",
                "icon": "🛎",
                "label": _t("Anreisen heute"),
                "value": str(arrivals_n),
                "hint": _t("Abreisen heute: %(n)s") % {"n": departures_n},
                # SM-2 (2026-08-10): сводка «Heute» живёт на самой главной —
                # виджет ведёт во вкладку броней (детальная работа — там).
                "url_name": "verkaeufe",
                "url_query": "?tab=stay",
                "sparkline": "",
            }
        )

    # 📣 Marketing-Puls (v1): Σ просмотров активных акций + погашения кампаний.
    if tenant.is_module_active("promotions"):

        def _puls():
            from django.db.models import Sum

            from apps.promotions.models import CouponCampaign, Promotion

            views = Promotion.objects.filter(status="active").aggregate(s=Sum("views"))["s"] or 0
            redeemed = CouponCampaign.objects.aggregate(s=Sum("vouchers__used_count"))["s"] or 0
            return views, redeemed

        views, redeemed = _safe(_puls, (0, 0))
        widgets.append(
            {
                "key": "puls",
                "icon": "📣",
                "label": _t("Marketing-Puls"),
                "value": str(views),
                "hint": _t("Aufrufe aktiver Angebote · %(n)s Gutscheine eingelöst")
                % {"n": redeemed},
                # W7b: /promotions/analytics/ гейтится СВОИМ модулем analytics
                # (по умолчанию выключен) — ссылка вела в 404; без модуля ведём
                # на список акций.
                "url_name": "promotions:analytics"
                if tenant.is_module_active("analytics")
                else "promotions:promotion-list",
                "url_query": "",
                "sparkline": "",
            }
        )

    # ⭐ Bewertungen — owner_overview (avg/count/unanswered — честный прокси).
    if tenant.is_module_active("reviews"):

        def _reviews():
            from apps.reviews.services import owner_overview

            return owner_overview()

        ov = _safe(_reviews, {"avg": 0, "count": 0, "unanswered": 0})
        widgets.append(
            {
                "key": "reviews",
                "icon": "⭐",
                "label": _t("Bewertungen"),
                "value": f"{ov.get('avg') or 0:.1f} ({ov.get('count') or 0})",
                "hint": _t("%(n)s ohne Antwort") % {"n": ov.get("unanswered") or 0},
                "url_name": "reviews:list",
                "url_query": "",
                "sparkline": "",
            }
        )
    return widgets
