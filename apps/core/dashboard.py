"""AB7-B2: плитки задач блочной главной кабинета `/dashboard/`.

Крупные кнопки на ЯЗЫКЕ ЗАДАЧ (товар/категории/главная/оплата/право) с бейджем
«Nicht ausgefüllt», взятым из ЕДИНОГО реестра шагов мастера
(`onboarding.steps_with_status`): клик по бейджу ведёт на конкретный слайд
(`setup?step=<key>`), чтобы дозаполнить пропущенное. Гейты — по активным модулям
и `simple_hidden_modules` (как сайдбар кабинета), чтобы плитки совпадали с тем, что
владельцу вообще доступно.
"""


def dashboard_tiles(tenant) -> list[dict]:
    """→ [{icon, label, url_name, step, needs}] — плитки главной кабинета.

    `step` — ключ слайда мастера для дозаполнения (бейдж «Nicht ausgefüllt» ведёт на
    `setup?step=<step>`); `needs` = True, если этот шаг ещё не выполнен по реальному
    контенту (из `steps_with_status`; скрытый/неизвестный шаг → без бейджа). Плитки
    гейтятся так же, как сайдбар: модуль активен и не спрятан Простым режимом.
    """
    from django.utils.translation import gettext as _t

    from apps.core import modules as _mod
    from apps.tenants import onboarding

    hidden = _mod.simple_hidden_modules(tenant)
    status = {s["key"]: s["status"] for s in onboarding.steps_with_status(tenant)}
    offer_label, offer_url = onboarding.offer_cta(tenant)

    def _needs(step_key: str) -> bool:
        # Бейдж только когда шаг реально не выполнен; скрытые/неизвестные → без бейджа.
        return status.get(step_key, "done") != "done"

    checkout_modules = ("orders", "booking", "stays", "events", "jobs")
    tiles: list[dict] = [
        # ✏️ первый/следующий товар-услуга-номер (по архетипу — offer_cta).
        {
            "icon": "✏️",
            "label": offer_label,
            "url_name": offer_url,
            "step": "offer",
            "needs": _needs("offer"),
        },
    ]
    # 📁 Категории — только при активном catalog и не спрятанном в Простом режиме.
    if tenant.is_module_active("catalog") and "catalog" not in hidden:
        tiles.append(
            {
                "icon": "📁",
                "label": _t("Categories"),
                "url_name": "catalog:category-list",
                "step": "category",
                "needs": _needs("category"),
            }
        )
    # 🏠 Главная сайта (конструктор).
    tiles.append(
        {
            "icon": "🏠",
            "label": _t("Design homepage"),
            "url_name": "site-home",
            "step": "home",
            "needs": _needs("home"),
        }
    )
    # 💳 Оплата и доставка — при любом чекаут-модуле (как гейт слайда payment).
    if any(tenant.is_module_active(m) for m in checkout_modules):
        tiles.append(
            {
                "icon": "💳",
                "label": _t("Payment & shipping"),
                "url_name": "payment-settings",
                "step": "payment",
                "needs": _needs("payment"),
            }
        )
    # 📄 Правовые тексты и страницы.
    tiles.append(
        {
            "icon": "📄",
            "label": _t("Legal texts & pages"),
            "url_name": "legal-docs",
            "step": "texts",
            "needs": _needs("texts"),
        }
    )
    return tiles


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

    Паттерн digest.collect_digest: per-module гейты + simple_hidden + fail-safe —
    упавший источник не роняет главную. → [{key, icon, label, value, hint,
    url_name, url_query, sparkline}] (sparkline — только у Umsatz)."""
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone
    from django.utils.translation import gettext as _t

    from apps.core import modules as _mod
    from apps.core.digest import _safe

    hidden = _mod.simple_hidden_modules(tenant)
    today = timezone.localdate()
    widgets: list[dict] = []

    # 💶 Umsatz heute + 7-дневный спарклайн (finance; в Простом finance скрыт).
    if tenant.is_module_active("finance") and "finance" not in hidden:

        def _revenue_days():
            from django.db.models import Sum

            from apps.finance.models import RevenueEntry

            start = today - timedelta(days=6)
            rows = dict(
                RevenueEntry.objects.filter(date__gte=start)
                .values("date")
                .annotate(s=Sum("amount"))
                .values_list("date", "s")
            )
            return [rows.get(start + timedelta(days=i)) or Decimal("0") for i in range(7)]

        days = _safe(_revenue_days, [Decimal("0")] * 7)
        widgets.append(
            {
                "key": "umsatz",
                "icon": "💶",
                "label": _t("Umsatz heute"),
                "value": f"{days[-1]:.2f} €".replace(".", ","),
                "hint": _t("letzte 7 Tage"),
                "url_name": "finance:journal",
                "url_query": "",
                "sparkline": _sparkline_points(days),
            }
        )

    # 📦 Abholbereit (orders ready) — «заказы к выдаче».
    if tenant.is_module_active("orders") and "orders" not in hidden:

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
                "url_name": "orders:order-list",
                "url_query": "?status=ready",
                "sparkline": "",
            }
        )

    # 📣 Marketing-Puls (v1): Σ просмотров активных акций + погашения кампаний.
    if tenant.is_module_active("promotions") and "promotions" not in hidden:

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
                "url_name": "promotions:analytics",
                "url_query": "",
                "sparkline": "",
            }
        )

    # ⭐ Bewertungen — owner_overview (avg/count/unanswered — честный прокси).
    if tenant.is_module_active("reviews") and "reviews" not in hidden:

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


def hub_tiles(tenant) -> list[dict]:
    """ST-4a: 5 плиток-хабов + «Website → Studio» (план §1; SVG-иконки — тег icon).

    Каждая ведёт на СУЩЕСТВУЮЩИЙ вход (Integrationen — лёгкий лендинг ST-4a);
    гейты по модулям — плитка выключенного модуля не показывается."""
    from django.utils.translation import gettext as _t

    tiles = [
        {"key": "orders", "icon": "ic-orders", "label": _t("Bestellungen"), "url_name": "board"},
        {
            "key": "offer",
            "icon": "ic-offer",
            "label": _t("Angebot"),
            "url_name": "sellable-manage",
        },
        {
            "key": "marketing",
            "icon": "ic-marketing",
            "label": _t("Marketing"),
            "url_name": "promotions:promotion-list",
        },
        {
            "key": "integrations",
            "icon": "ic-integrations",
            "label": _t("Integrationen"),
            "url_name": "integrations-home",
        },
        {
            "key": "settings",
            "icon": "ic-settings",
            "label": _t("Einstellungen"),
            "url_name": "settings",
        },
        {
            "key": "website",
            "icon": "ic-website",
            "label": _t("Website"),
            "url_name": "site-home",
            "wide": True,
        },
    ]
    return tiles
