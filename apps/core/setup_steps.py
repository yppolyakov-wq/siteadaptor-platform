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


# --- AB6.2-lang: per-language контент-поля слайдов (фидбэк владельца 2026-07-16) ---
# Базовая локаль (settings.LANGUAGE_CODE=de) хранится плоскими строками site_config;
# переводы прочих ВКЛЮЧЁННЫХ локалей — оверлеем config["i18n"][loc][field]
# (normalize сохраняет через _clean_i18n, витрина накладывает siteconfig.localize).


def _content_locales(tenant) -> list[str]:
    """Локали контент-полей слайда: базовая первой + прочие активные (пилюли)."""
    from django.conf import settings

    base = settings.LANGUAGE_CODE
    return [base] + [loc for loc in tenant.active_locales if loc != base]


def _save_overlay_fields(request, cfg: dict, fields: tuple) -> None:
    """Presence-safe запись переводов слайда в оверлей config["i18n"][loc][field]
    (инпуты name="<field>__<loc>"). Пусто = убрать перевод (фолбэк на базовую строку);
    не присланное поле не трогаем (шаг мог рендериться без этой локали)."""
    from django.conf import settings

    base = settings.LANGUAGE_CODE
    for loc in request.tenant.active_locales:
        if loc == base:
            continue
        for f in fields:
            val = request.POST.get(f"{f}__{loc}")
            if val is None:
                continue
            ov = cfg.setdefault("i18n", {}).setdefault(loc, {})
            if val.strip():
                ov[f] = val.strip()
            else:
                ov.pop(f, None)


def _i18n_panes(tenant, fields: tuple) -> list[dict]:
    """[{loc, <field>: значение…}] — панели переводов для предзаполнения слайда
    (только не-базовые активные локали; пусто = панелей нет, пилюли скрыты)."""
    from django.conf import settings

    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    i18n = cfg.get("i18n") if isinstance(cfg.get("i18n"), dict) else {}
    panes = []
    for loc in tenant.active_locales:
        if loc == settings.LANGUAGE_CODE:
            continue
        ov = i18n.get(loc) if isinstance(i18n.get(loc), dict) else {}
        panes.append({"loc": loc, **{f: ov.get(f, "") for f in fields}})
    return panes


def save_hero(request, tenant) -> None:
    """B.3: сохранить баннер мастера — hero-тексты + опц. загруженное фото (файл).
    AB6.2-lang: + переводы hero-текстов на включённых локалях (оверлей i18n)."""
    from apps.tenants import siteconfig

    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    config["hero_title"] = request.POST.get("hero_title", "").strip()
    config["hero_text"] = request.POST.get("hero_text", "").strip()
    _save_overlay_fields(request, config, ("hero_title", "hero_text"))
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


def _post_company(request):
    # AB6.2f: название/город (правятся в мастере, а не только при регистрации) +
    # контакты/часы + логотип (файл). Имя не затираем пустым (обязательное поле).
    tenant = request.tenant
    name = request.POST.get("name", "").strip()
    if name:
        tenant.name = name
    tenant.city = request.POST.get("city", "").strip()
    for field in ("address", "opening_hours", "contact_phone", "contact_email"):
        setattr(tenant, field, request.POST.get(field, "").strip())
    tenant.save(
        update_fields=[
            "name",
            "city",
            "address",
            "opening_hours",
            "contact_phone",
            "contact_email",
            "updated_at",
        ]
    )
    # Логотип — файл (реюз M1-хелпер); no-op без файла. В live-режиме файлы не шлются.
    from apps.core.views import _save_logo

    _save_logo(request)


def _ctx_company(request):
    return {"logo_url": request.tenant.logo_url}


# Хвост AB6 (решение §0b.3): чипы стандартных пунктов меню на слайде «Menü».
# Правим menus.top.items (настоящий источник шапки — resolve_menu), а НЕ nav.items:
# normalize выводит top из nav только пока `menus` НЕ материализован (после первого
# Save он материализован почти у всех). Немецкие подписи — для СОЗДАВАЕМЫХ узлов
# (реестр NAV_ITEMS несёт англ. msgid); существующие узлы держат свои label.
_MENU_CHIP_LABELS = {
    "offers": "Start / Angebote",
    "products": "Produkte",
    "booking": "Termine",
    "stays": "Übernachten",
    "events": "Veranstaltungen",
    "jobs": "Angebot anfragen",
    "inbox": "Frage stellen",
    "about": "Über uns",
}


def _menu_chip_candidates(tenant) -> list[dict]:
    """Стандартные пункты меню как кандидаты чипов: реестр NAV_ITEMS (гейт по модулю)
    + страница «Über uns». → [{key,label,type,target}] (type/target — узел menus)."""
    from apps.tenants import siteconfig as sc

    out = []
    for key, _label, _url, module in sc.NAV_ITEMS:
        if module and not tenant.is_module_active(module):
            continue
        ntype, target = sc._NAV_KEY_TO_NODE[key]
        out.append(
            {"key": key, "label": _MENU_CHIP_LABELS.get(key, key), "type": ntype, "target": target}
        )
    out.append(
        {"key": "about", "label": _MENU_CHIP_LABELS["about"], "type": "page", "target": "about"}
    )
    return out


def _post_menu(request):
    # AB6.2e: вид шапки (classic/centered/minimal). ФИКС: шапка витрины рендерит
    # menus.top.style (top_meta) — на конфиге с материализованным `menus` запись
    # только в nav.style была no-op → зеркалим в оба места.
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    changed = False
    style = request.POST.get("nav_style", "")
    if style in siteconfig.NAV_STYLES:
        cfg.setdefault("nav", {})["style"] = style
        cfg["menus"]["top"]["style"] = style
        changed = True
    # Чипы пунктов (сентинел menu_chips — presence-guard): выбранный стандартный пункт
    # включаем/добавляем в menus.top.items, снятый — выключаем (enabled=False, НЕ
    # удаляем: label/подменю владельца переживают). Кастомные узлы не трогаем.
    if request.POST.get("menu_chips"):
        chosen = set(request.POST.getlist("menu_items"))
        items = cfg["menus"]["top"]["items"]
        for c in _menu_chip_candidates(request.tenant):
            matches = [
                n for n in items if n.get("type") == c["type"] and n.get("target") == c["target"]
            ]
            want = c["key"] in chosen
            if matches:
                for n in matches:
                    n["enabled"] = want
            elif want:
                items.append(
                    {
                        "label": c["label"],
                        "type": c["type"],
                        "target": c["target"],
                        "enabled": True,
                        "icon": "",
                        "children": [],
                    }
                )
        changed = True
    if changed:
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])


def _ctx_menu(request):
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    items = cfg["menus"]["top"]["items"]

    def _on(c):
        return any(
            n.get("type") == c["type"] and n.get("target") == c["target"] and n.get("enabled", True)
            for n in items
        )

    return {
        "nav_styles": siteconfig.NAV_STYLES,
        # Стиль — из menus.top (что реально рендерит шапка), не из nav.
        "nav_style": cfg["menus"]["top"].get("style") or siteconfig.NAV_STYLES[0],
        "menu_chips": [{**c, "checked": _on(c)} for c in _menu_chip_candidates(request.tenant)],
    }


# AB6.2d: пресеты раскладки каталога/категорий для слайда «Kategorien» (мокапы в
# шаблоне по key). Подмножество LAYOUT_PRESETS, осмысленное для листинга товаров.
_CATALOG_PRESET_CARDS = (
    {"key": "cols2", "label": "2 Spalten"},
    {"key": "cols3", "label": "3 Spalten"},
    {"key": "cols4", "label": "4 Spalten"},
    {"key": "list", "label": "Liste"},
)


def _post_category(request):
    # AB6.2d: раскладка страницы каталога/категорий (columns) → catalog_layout.preset
    # (normalize материализует cols/mobile). Какие категории — редактор (ссылка в слайде).
    from apps.tenants import siteconfig

    preset = request.POST.get("catalog_preset", "")
    if preset in siteconfig.LAYOUT_PRESETS:
        cfg = siteconfig.normalize(request.tenant.site_config)
        cfg["catalog_layout"] = {"preset": preset}
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])


def _ctx_category(request):
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    return {
        "catalog_presets": _CATALOG_PRESET_CARDS,
        "catalog_preset": (cfg.get("catalog_layout") or {}).get("preset") or "cols3",
    }


def _post_payment(request):
    # AB6.2-payment: сохранить оплату/доставку общим диспетчером (те же sec_*-гейты, что
    # у экрана payment_settings) — секция не затирается без своего сентинела. Сохранение
    # только на «Weiter» (payment-слайд не live — не писать IBAN на каждый ввод).
    from apps.core.views import save_payment_settings

    save_payment_settings(request)


def _ctx_payment(request):
    from apps.core.views import payment_settings_context

    return payment_settings_context(request)


def _post_hero(request):
    save_hero(request, request.tenant)


# --- context: данные рендера шага ------------------------------------------------


def _ctx_business(request):
    from apps.tenants import onboarding

    return {"business_types": onboarding.business_type_cards(request)}


def _ctx_template(request):
    # AB6.2b: шаблоны витрины как визуальные карточки с мини-мокапом раскладки
    # (акцент + стек секций) — рекомендованные типу сверху; выбор одним кликом.
    from apps.tenants import sitetemplates

    return {"templates": sitetemplates.template_cards(request.tenant.business_type)}


def _ctx_hero(request):
    # B.3: текущие значения баннера для предзаполнения. AB6.2-lang: + панели переводов.
    from apps.tenants import siteconfig

    config = siteconfig.normalize(request.tenant.site_config)
    return {
        "hero_title": config["hero_title"],
        "hero_text": config["hero_text"],
        "hero_image": config["hero_image"],
        "content_locales": _content_locales(request.tenant),
        "i18n_panes": _i18n_panes(request.tenant, ("hero_title", "hero_text")),
    }


def _post_language(request):
    # AB6.2-lang: языки витрины + дефолт (реюз кабинета «Sprachen» — save_languages).
    from apps.core.views import save_languages

    if not save_languages(request):
        messages.error(request, _("Please enable at least one language."))


def _ctx_language(request):
    from apps.core.views import languages_context

    return {"languages": languages_context(request.tenant)}


def _post_texts(request):
    # AB6.2g: «Über uns» (about_*, presence-safe TEXT_FIELDS — мержим в существующий
    # конфиг, урок W6) + Impressum (LegalDoc дефолт-локали, реюз семантики legal_docs).
    # AB6.2-lang: + переводы about_* на включённых локалях (оверлей i18n).
    from apps.tenants import siteconfig

    tenant = request.tenant
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    for f in ("about_title", "about_text"):
        if request.POST.get(f) is not None:
            cfg[f] = request.POST.get(f, "").strip()
    _save_overlay_fields(request, cfg, ("about_title", "about_text"))
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=["site_config", "updated_at"])
    val = request.POST.get("impressum")
    if val is not None:
        from apps.core.models import LegalDoc

        loc = tenant.default_locale or "de"
        if val.strip():
            LegalDoc.objects.update_or_create(kind="impressum", locale=loc, defaults={"text": val})
        else:
            LegalDoc.objects.filter(kind="impressum", locale=loc).delete()


def _ctx_texts(request):
    from apps.tenants import siteconfig

    tenant = request.tenant
    cfg = siteconfig.normalize(tenant.site_config)
    impressum = ""
    try:
        from apps.core.models import LegalDoc

        doc = LegalDoc.objects.filter(
            kind="impressum", locale=tenant.default_locale or "de"
        ).first()
        impressum = doc.text if doc else ""
    except Exception:  # noqa: BLE001 — модель/таблица недоступна
        impressum = ""
    return {
        "about_title": cfg.get("about_title", ""),
        "about_text": cfg.get("about_text", ""),
        "impressum": impressum,
        "content_locales": _content_locales(tenant),
        "i18n_panes": _i18n_panes(tenant, ("about_title", "about_text")),
    }


# AB6.2c: типы сущностей, для которых слайд «Angebot» показывает мини-форму создания
# первой позиции (по primary-архетипу). jobs (Anfrage/смета) и promotions — без
# создаваемой сущности → только пресеты/CTA. Плейсхолдер имени — язык задач архетипа.
_OFFER_KINDS = ("catalog", "booking", "stays", "events")
_OFFER_NAME_PH = {
    "catalog": "z. B. Roggenbrot",
    "booking": "z. B. Haarschnitt",
    "stays": "z. B. Doppelzimmer",
    "events": "z. B. Sommerkonzert",
}


def _offer_kind(tenant) -> str | None:
    """AB6.2c: тип продаваемой сущности для мини-формы (или None, если у архетипа нет
    создаваемой позиции — jobs/promotions/выключенные модули)."""
    from apps.core import archetypes

    kind = archetypes.primary_module(tenant)
    return kind if kind in _OFFER_KINDS else None


def _parse_price_eur(raw: str):
    """'12,50 €' / '12.50' → Decimal ≥ 0, иначе None (пустое/мусор). Немецкая
    запятая-разделитель и символ € допускаются (владелец печатает как привык)."""
    from decimal import Decimal, InvalidOperation

    s = (raw or "").strip().replace("€", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        val = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return val if val >= 0 else None


def _parse_dt_local(raw: str):
    """'2026-07-20T14:30' (input datetime-local) → aware datetime, иначе None."""
    from datetime import datetime

    from django.utils import timezone

    s = (raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _offer_items(tenant) -> list[dict]:
    """AB6.2c: уже добавленные позиции primary-архетипа для списка «✏️» в слайде.
    [{name, url}] (url — родная форма правки: pk-редактор для товара/события, список-
    редактор для услуг/номеров). Fail-safe: любая ошибка → пустой список."""
    from django.urls import reverse

    kind = _offer_kind(tenant)
    if not kind:
        return []
    rows: list[dict] = []
    try:
        if kind == "catalog":
            from apps.catalog.models import Product

            for p in Product.objects.all().order_by("-created_at")[:8]:
                rows.append(
                    {
                        "name": p.name_text or "—",
                        "url": reverse("catalog:product-edit", args=[p.pk]),
                    }
                )
        elif kind == "events":
            from apps.events.models import Event

            for e in Event.objects.all().order_by("-starts_at")[:8]:
                rows.append({"name": e.title or "—", "url": reverse("events:edit", args=[e.pk])})
        elif kind == "booking":
            from apps.booking.models import Service

            url = reverse("booking:services")  # правка услуг — инлайн на списке
            for s in Service.objects.all().order_by("-created_at")[:8]:
                rows.append({"name": s.name or "—", "url": url})
        elif kind == "stays":
            from apps.stays.models import StayUnit

            url = reverse("stays:units")  # правка номеров — инлайн на списке
            for u in StayUnit.objects.all().order_by("-created_at")[:8]:
                rows.append({"name": u.name or "—", "url": url})
    except Exception:  # noqa: BLE001 — модуль выключен / нет таблицы
        return []
    return rows


def create_offer(request) -> None:
    """AB6.2c: создать первую продаваемую сущность из мини-формы слайда «Angebot».

    Тип — по primary-архетипу (товар/услуга/номер/событие); минимум полей (имя + цена,
    для события ещё дата) — детали правятся в родной форме («✏️» в списке). Остаёмся
    на слайде (action=create_offer в диспетчере). Одну позицию не роняем весь мастер."""
    tenant = request.tenant
    kind = _offer_kind(tenant)
    if not kind:
        return
    name = request.POST.get("offer_name", "").strip()
    if not name:
        messages.error(request, _("Please enter a name."))
        return
    price = _parse_price_eur(request.POST.get("offer_price", ""))
    cents = int((price * 100).to_integral_value()) if price is not None else 0
    try:
        if kind == "catalog":
            from decimal import Decimal

            from apps.catalog.models import Product

            Product.objects.create(
                name={"de": name}, base_price=price if price is not None else Decimal("0")
            )
        elif kind == "booking":
            from apps.booking.models import Service

            Service.objects.create(name=name, price_cents=cents)
        elif kind == "stays":
            from apps.stays.models import StayUnit

            StayUnit.objects.create(name=name, price_cents=cents)
        elif kind == "events":
            from datetime import timedelta

            from django.utils import timezone

            from apps.events.models import Event

            starts_at = _parse_dt_local(request.POST.get("offer_starts_at", "")) or (
                timezone.now() + timedelta(days=7)
            )
            Event.objects.create(
                title=name,
                starts_at=starts_at,
                price_cents=cents,
                status=Event.STATUS_PUBLISHED,
            )
    except Exception:  # noqa: BLE001 — не роняем мастер из-за одной позиции
        messages.error(request, _("Couldn't add it — please try again."))
        return
    messages.success(request, _("Added — edit the details anytime."))


def _ctx_content(request):
    from apps.promotions import presets
    from apps.tenants import demo, onboarding

    label, url = onboarding.offer_cta(request.tenant)
    kind = _offer_kind(request.tenant)
    return {
        "presets": presets.presets_for(request.tenant.business_type),
        "has_demo": demo.has_demo(request.tenant),  # B.1: предложить/убрать демо-контент
        # W3: CTA «добавь первое X» — по архетипу, не хардкод «Produkt».
        "offer_label": label,
        "offer_url": url,
        # AB6.2c: мини-форма первой сущности (по kind) + список уже добавленных.
        "offer_kind": kind,
        "offer_needs_date": kind == "events",
        "offer_name_ph": _OFFER_NAME_PH.get(kind, ""),
        "offer_items": _offer_items(request.tenant),
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
        template="tenant/setup/_step_company.html",
        post=_post_company,
        context=_ctx_company,
        preview=True,
        live=True,
    ),
    # AB6.2-lang: языки сайта (дефолт de) — до контент-шагов; save на «Weiter»
    # (не live: инвариант «минимум один язык» не дёргать на каждом клике).
    "language": StepHandler(
        template="tenant/setup/_step_language.html",
        post=_post_language,
        context=_ctx_language,
        preview=True,
    ),
    "stil": StepHandler(
        template="tenant/setup/_step_stil.html",
        post=_post_template,
        context=_ctx_template,
        preview=True,
        live=True,
    ),
    "menu": StepHandler(
        template="tenant/setup/_step_menu.html",
        post=_post_menu,
        context=_ctx_menu,
        preview=True,
        live=True,
    ),
    # Шаг offer — демо/пресеты/CTA (action-кнопки в диспетчере); вид товара — AB6.2c.
    "offer": StepHandler(
        template="tenant/setup/_step_offer.html", context=_ctx_content, preview=True
    ),
    "category": StepHandler(
        template="tenant/setup/_step_category.html",
        post=_post_category,
        context=_ctx_category,
        preview=True,
        live=True,
    ),
    "home": StepHandler(
        template="tenant/setup/_step_home.html",
        post=_post_hero,
        context=_ctx_hero,
        preview=True,
        live=True,
    ),
    # payment-слайд НЕ live (не писать банковские поля на каждый ввод) — save на «Weiter».
    "payment": StepHandler(
        template="tenant/setup/_step_payment.html",
        post=_post_payment,
        context=_ctx_payment,
        preview=True,
    ),
    "texts": StepHandler(
        template="tenant/setup/_step_texts.html", post=_post_texts, context=_ctx_texts
    ),
    "done": StepHandler(template="tenant/setup/_step_done.html"),
}
