"""AB6.1: handler'ы шагов Onboarding-мастера — по одному на слайд.

apps.core.views.setup_view остаётся тонким диспетчером (глобальные action'ы
skip/back/live/demo_start/load_demo/clear_demo + прыжок ?step=<key>), а
сохранение полей шага (post) и контекст рендера (context) живут здесь.
Порядок/статусы шагов — реестр apps.tenants.onboarding.SETUP_STEPS (единый
источник для рельсы прогресса, а далее — чек-листа AB4 и плиток AB7).

Ключи HANDLERS обязаны совпадать с onboarding.STEP_KEYS (замок в тестах).
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.contrib import messages
from django.utils.translation import gettext as _


@dataclass(frozen=True)
class StepHandler:
    """Слайд мастера: партиал + опц. save полей (POST) и контекст рендера (GET).

    preview — показывать live-iframe витрины; live — сохранять поля по мере
    ввода (action=live → 204; файлы в live не шлются, см. JS в setup.html).
    """

    template: str
    post: Callable | None = None
    context: Callable | None = None
    preview: bool = False
    live: bool = False


def apply_business_type(tenant, business_type: str) -> None:
    """Шаг business: сохранить тип бизнеса + (при смене типа или нетронутом
    пресете) применить стартовый набор модулей вертикали. Гибрид (решение
    владельца 2026-06-12): смена типа = «я такой бизнес» → набор подстраивается
    даже у настроенного тенанта; тот же тип ручную конфигурацию не трогает.
    Общий код шага business и «Mit Beispielen starten»."""
    from apps.core import modules as registry
    from apps.tenants.models import Tenant

    if business_type not in dict(Tenant.BUSINESS_TYPES):
        return
    untouched_preset = sorted(tenant.disabled_modules or []) == sorted(
        registry.default_disabled_for(tenant.business_type)
    )
    type_changed = business_type != tenant.business_type
    tenant.business_type = business_type
    update_fields = ["business_type", "updated_at"]
    if type_changed or untouched_preset:
        tenant.disabled_modules = registry.default_disabled_for(business_type)
        update_fields.insert(1, "disabled_modules")
    tenant.save(update_fields=update_fields)


def save_hero(request, tenant) -> None:
    """B.3: сохранить баннер мастера — hero-тексты + опц. загруженное фото (файл)."""
    from apps.tenants import siteconfig

    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    config["hero_title"] = request.POST.get("hero_title", "").strip()
    config["hero_text"] = request.POST.get("hero_text", "").strip()
    uploaded = request.FILES.get("hero_image")
    if uploaded:
        from apps.catalog import images

        try:
            images.validate_image(uploaded)
            ref = images.save_product_image(uploaded, folder="hero")
            config["hero_image"] = ref["url"]
        except Exception:
            messages.error(request, _("Couldn't upload the image — please try another file."))
    tenant.site_config = siteconfig.normalize(config)
    tenant.save(update_fields=["site_config", "updated_at"])


# --- post: сохранение полей шага -------------------------------------------------


def _post_business(request):
    apply_business_type(request.tenant, request.POST.get("business_type", ""))


def _post_template(request):
    # B.2: выбор шаблона витрины (раскладка+тексты+акцент) одним кликом.
    from apps.tenants import sitetemplates

    sitetemplates.apply_template(request.tenant, request.POST.get("template", ""))


def _post_basics(request):
    tenant = request.tenant
    for field in ("address", "opening_hours", "contact_phone", "contact_email"):
        setattr(tenant, field, request.POST.get(field, "").strip())
    tenant.save(
        update_fields=["address", "opening_hours", "contact_phone", "contact_email", "updated_at"]
    )


def _post_hero(request):
    save_hero(request, request.tenant)


# --- context: данные рендера шага ------------------------------------------------


def _ctx_business(request):
    from apps.tenants import onboarding

    return {"business_types": onboarding.business_type_cards(request)}


def _ctx_template(request):
    # B.2: шаблоны витрины как визуальные карточки (рекомендованные типу — сверху).
    from apps.tenants import siteconfig, sitetemplates

    config = siteconfig.normalize(request.tenant.site_config)
    return {
        "templates": sitetemplates.templates_for(request.tenant.business_type),
        "current_sections": [s["key"] for s in config["sections"] if s["enabled"]],
    }


def _ctx_hero(request):
    # B.3: текущие значения баннера для предзаполнения.
    from apps.tenants import siteconfig

    config = siteconfig.normalize(request.tenant.site_config)
    return {
        "hero_title": config["hero_title"],
        "hero_text": config["hero_text"],
        "hero_image": config["hero_image"],
    }


def _ctx_content(request):
    from apps.promotions import presets
    from apps.tenants import demo, onboarding

    label, url = onboarding.offer_cta(request.tenant)
    return {
        "presets": presets.presets_for(request.tenant.business_type),
        "has_demo": demo.has_demo(request.tenant),  # B.1: предложить/убрать демо-контент
        # W3: CTA «добавь первое X» — по архетипу, не хардкод «Produkt».
        "offer_label": label,
        "offer_url": url,
    }


# AB6.2: карта слайдов master-slides-v3 §0d. business — escape-hatch (gate скрывает,
# но handler нужен для ?step=); stil = галерея архетип-шаблонов (бывш. template =
# «весь образ архетипа одним кликом»); menu/category/payment/texts — стабы (наполнение
# AB6.2b-g); company=бывш.basics, offer=бывш.content, home=бывш.hero.
def _ctx_start(request):
    from apps.tenants import demo

    return {"has_demo": demo.has_demo(request.tenant)}


HANDLERS = {
    "business": StepHandler(
        template="tenant/setup/_step_business.html", post=_post_business, context=_ctx_business
    ),
    # AB6.9: первый видимый слайд — «богатое» демо одним кликом (первый логический шаг).
    "start": StepHandler(
        template="tenant/setup/_step_start.html", context=_ctx_start, preview=True
    ),
    "company": StepHandler(
        template="tenant/setup/_step_company.html", post=_post_basics, preview=True, live=True
    ),
    "stil": StepHandler(
        template="tenant/setup/_step_stil.html",
        post=_post_template,
        context=_ctx_template,
        preview=True,
        live=True,
    ),
    "menu": StepHandler(template="tenant/setup/_step_menu.html", preview=True),
    # Шаг offer — демо/пресеты/CTA (action-кнопки в диспетчере); вид товара — AB6.2c.
    "offer": StepHandler(
        template="tenant/setup/_step_offer.html", context=_ctx_content, preview=True
    ),
    "category": StepHandler(template="tenant/setup/_step_category.html", preview=True),
    "home": StepHandler(
        template="tenant/setup/_step_home.html",
        post=_post_hero,
        context=_ctx_hero,
        preview=True,
        live=True,
    ),
    "payment": StepHandler(template="tenant/setup/_step_payment.html", preview=True),
    "texts": StepHandler(template="tenant/setup/_step_texts.html"),
    "done": StepHandler(template="tenant/setup/_step_done.html"),
}
