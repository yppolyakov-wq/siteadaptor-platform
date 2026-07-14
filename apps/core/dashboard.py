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
