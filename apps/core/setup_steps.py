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
from django.utils.translation import gettext_lazy

from apps.core import page_presets as _page_presets


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
    # KA-12 A-3: стартовая форма заявки нового типа — только при СМЕНЕ типа и
    # только если ключа нет. Повтор того же шага не возвращает пресет, если
    # владелец снял все поля (ключ удалён панелью).
    if type_changed:
        from apps.jobs import status_presets
        from apps.jobs.anfrage_presets import with_default

        tenant.site_config, changed = with_default(tenant.site_config, business_type)
        tenant.site_config, changed_status = status_presets.with_default(
            tenant.site_config, business_type
        )
        if changed or changed_status:
            update_fields.insert(1, "site_config")
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
    # ST-1b: выбор Look'а (семейство × архетип) — приоритетнее шаблона.
    from apps.tenants import sitetemplates

    # DS-3c: сборка (Startpaket) — Look + виды вывода одним кликом (приоритетнее).
    bundle = request.POST.get("bundle", "")
    if bundle and sitetemplates.apply_bundle(request.tenant, bundle):
        return
    look = request.POST.get("look", "")
    if look and sitetemplates.apply_look(request.tenant, look):
        return
    sitetemplates.apply_template(request.tenant, request.POST.get("template", ""))


def _post_company(request):
    # AB6.2f: название/город (правятся в мастере, а не только при регистрации) +
    # контакты/часы + логотип (файл). Имя не затираем пустым (обязательное поле).
    tenant = request.tenant
    name = request.POST.get("name", "").strip()
    if name:
        tenant.name = name
    # W7a: presence-guard — поле, которого нет в POST, не обнуляем (паттерн
    # site_view/legal_docs_view; live-save шлёт FormData слайда целиком, но чужой
    # или урезанный POST не должен стирать контакты).
    if "city" in request.POST:
        tenant.city = request.POST.get("city", "").strip()
    for field in ("address", "opening_hours", "contact_phone", "contact_email"):
        if field in request.POST:
            setattr(tenant, field, request.POST.get(field, "").strip())
    fields = ["name", "city", "address", "opening_hours", "contact_phone", "contact_email"]
    # AIS-W W4-1: часы сеткой (мастер v4). Сентинел — нет сетки в POST, часы не трогаем (W0).
    if "oh_present" in request.POST:
        from apps.core.views import _parse_opening_hours

        tenant.opening_hours_structured = _parse_opening_hours(request)
        fields.append("opening_hours_structured")
    tenant.save(update_fields=[*fields, "updated_at"])
    # Логотип — файл (реюз M1-хелпер); no-op без файла. В live-режиме файлы не шлются.
    from apps.core.views import _save_logo

    _save_logo(request)


def _ctx_company(request):
    from apps.core.views import _opening_hours_rows
    from apps.tenants import onboarding

    ctx = {"logo_url": request.tenant.logo_url}
    if onboarding.is_v4(request.tenant):  # мастер v4: часы сеткой (как в «Geschäft»)
        ctx["hours_grid"] = True
        ctx["opening_hours_rows"] = _opening_hours_rows(request.tenant)
        from apps.core import setup_google

        ctx.update(setup_google.context(request))  # W4-3: «Bei Google suchen»
        from apps.tenants import onboarding

        # AIS-3: выбрали «Google-Profil» на первом шаге — подсказка над поиском.
        ctx["google_chosen"] = "google" in onboarding.had(request.tenant)
    return ctx


# --- AIS-W W4-1: шаг «Rechtliches & Veröffentlichen» --------------------------------------

#: Правовые поля шага (те же, что раздел «Rechtliches» лёгкого «Geschäft», + палата и
#: профессия для zulassungspflichtiges Handwerk).
RECHT_FIELDS = (
    "contact_email",
    "legal_form",
    "legal_representative",
    "register_court",
    "register_number",
    "vat_id",
    "tax_number",
)
TRADE_FIELDS = ("chamber", "profession")


def _recht_fields(tenant) -> tuple[str, ...]:
    from apps.tenants.models import REGULATED_TRADE_TYPES

    if tenant.business_type in REGULATED_TRADE_TYPES:
        return (*RECHT_FIELDS, *TRADE_FIELDS)
    return RECHT_FIELDS


def _post_recht(request):
    """Правовые данные Impressum. Presence-safe: поле, которого нет в POST, не трогаем."""
    from apps.core import tg_login

    tenant = request.tenant
    if tg_login.is_tg_session(request):
        # SEC-A11: из Telegram-сессии правовые данные не меняются.
        messages.error(request, _("Rechtliche Angaben nur nach Anmeldung per E-Mail."))
        return False
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    values = {
        field: request.POST.get(field, "").strip()[
            : tenant._meta.get_field(field).max_length or 200
        ]
        for field in _recht_fields(tenant)
        if field in request.POST
    }
    email = values.get("contact_email")
    if email:
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, _("Bitte eine gültige E-Mail-Adresse eingeben."))
            return False
    if values.get("legal_form") and values["legal_form"] not in dict(tenant.LEGAL_FORMS):
        values.pop("legal_form")  # подмена значения формы — не пишем мусор в Impressum
    for field, value in values.items():
        setattr(tenant, field, value)
    changed = list(values)
    if "tax_choice" in request.POST:
        from apps.finance import ustva

        if ustva.apply_regime(tenant, request.POST.get("tax_choice", "")):
            changed += ["small_business", "tax_regime"]
    if changed:
        tenant.save(update_fields=[*changed, "updated_at"])
        messages.success(request, _("Gespeichert."))
    return True


def _ctx_recht(request):
    from apps.core import tg_login
    from apps.core.lite_cabinet import LiteBusinessForm, impressum_missing
    from apps.finance import ustva
    from apps.tenants import onboarding
    from apps.tenants.models import REGULATED_TRADE_TYPES

    tenant = request.tenant
    labels = {
        **LiteBusinessForm.Meta.labels,
        "chamber": gettext_lazy("Zuständige Kammer"),
        "profession": gettext_lazy("Berufsbezeichnung"),
    }
    choices = {"legal_form": [("", "—"), *tenant._meta.get_field("legal_form").choices]}
    fields = [
        {
            "name": f,
            "label": labels.get(f, f),
            # Пустой e-mail Impressum подсказываем почтой входа: владелец видит её в поле
            # и сохраняет вместе с формой (без молчаливой записи).
            "value": getattr(tenant, f, "")
            or (getattr(request.user, "email", "") if f == "contact_email" else ""),
            "choices": choices.get(f),
        }
        for f in _recht_fields(tenant)
    ]
    return {
        "recht_fields": fields,
        "tax_choices": ustva.REGIME_CHOICES,
        "tax_current": ustva.regime_of(tenant),
        "regulated": tenant.business_type in REGULATED_TRADE_TYPES,
        "trade_missing": tenant.business_type in REGULATED_TRADE_TYPES
        and not (tenant.chamber and tenant.profession),
        "impressum_preview": tenant.impressum_text(),
        "impressum_missing": [] if tenant.published_at else impressum_missing(tenant),
        "published": tenant.published_at is not None,
        "blockers": [] if tenant.published_at else onboarding.publish_blockers(tenant),
        "tg_locked": tg_login.is_tg_session(request),
        "preview_url": "/impressum/",
    }


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
    {"key": "cols2", "label": gettext_lazy("2 Spalten")},
    {"key": "cols3", "label": gettext_lazy("3 Spalten")},
    {"key": "cols4", "label": gettext_lazy("4 Spalten")},
    {"key": "list", "label": gettext_lazy("Liste")},
)


# ST-2: листинги других модулей — та же раскладка по чекбоксу слайда category
# (зеркало «Apply to all» билдера; пишем ТОЛЬКО активным модулям).
_OTHER_LISTING_KEYS = (
    ("events", "events_index_layout"),
    ("stays", "stay_index_layout"),
    ("booking", "service_index_layout"),
)


def _post_category(request):
    # AB6.2d: раскладка страницы каталога/категорий (columns) → catalog_layout.preset
    # (normalize материализует cols/mobile). Какие категории — редактор (ссылка в слайде).
    from apps.tenants import siteconfig

    preset = request.POST.get("catalog_preset", "")
    if preset in siteconfig.LAYOUT_PRESETS:
        cfg = siteconfig.normalize(request.tenant.site_config)
        cfg["catalog_layout"] = {"preset": preset}
        if request.POST.get("apply_all_listings"):
            for module, key in _OTHER_LISTING_KEYS:
                if request.tenant.is_module_active(module):
                    cfg[key] = {"preset": preset}
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])


def _ctx_category(request):
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    return {
        "catalog_presets": _CATALOG_PRESET_CARDS,
        "catalog_preset": (cfg.get("catalog_layout") or {}).get("preset") or "cols3",
        # ST-2: чекбокс «для всех списков» — только если есть другие листинги.
        "category_other_listings": any(
            request.tenant.is_module_active(m) for m, _k in _OTHER_LISTING_KEYS
        ),
    }


def _post_payment(request):
    # AB6.2-payment: сохранить оплату/доставку общим диспетчером (те же sec_*-гейты, что
    # у экрана payment_settings) — секция не затирается без своего сентинела. Сохранение
    # только на «Weiter» (payment-слайд не live — не писать IBAN на каждый ввод).
    from django.contrib import messages

    from apps.core.views import save_payment_settings

    errors = save_payment_settings(request)
    for error in errors:
        messages.error(request, error)
    return False if errors else None


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
    # ST-1b: + 3 Look'а архетипа (живые scaled-iframe ?preview=1&look=).
    from apps.tenants import sitetemplates

    return {
        "templates": sitetemplates.template_cards(request.tenant.business_type),
        "looks": sitetemplates.looks_for(request.tenant.business_type),
        # DS-3c: сборки (Startpakete) — карточки НАД Look-галереей.
        "bundles": sitetemplates.bundles_for(request.tenant.business_type, request.tenant),
    }


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


# AB6.10 → ST-2: шаблоны страницы «Über uns» уехали в общий реестр пресетов
# страниц (apps/core/page_presets.py, host "info", префикс pb-about- сохранён).
# Alias — для замков/истории; слайд работает через generic-апплаер.
_ABOUT_PRESETS = _page_presets.PAGE_PRESETS["info"]["presets"]


def _post_about(request):
    # AB6.10: «Über uns» — тексты (presence-safe + i18n-оверлей, как texts раньше) +
    # шаблон страницы (ST-2 generic: пресет блоков info-хоста, идемпотентно по
    # префиксу id; блоки владельца целы).
    from apps.tenants import siteconfig

    tenant = request.tenant
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    for f in ("about_title", "about_text"):
        if request.POST.get(f) is not None:
            cfg[f] = request.POST.get(f, "").strip()
    _save_overlay_fields(request, cfg, ("about_title", "about_text"))
    if request.POST.get("about_preset"):
        _page_presets.apply_page_preset(cfg, "info", request.POST.get("about_preset"))
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=["site_config", "updated_at"])


def _ctx_about(request):
    from apps.tenants import siteconfig

    tenant = request.tenant
    cfg = siteconfig.normalize(tenant.site_config)
    current = _page_presets.current_preset(cfg, "info")
    return {
        "about_title": cfg.get("about_title", ""),
        "about_text": cfg.get("about_text", ""),
        "about_presets": [{**p, "checked": p["key"] == current} for p in _ABOUT_PRESETS],
        "content_locales": _content_locales(tenant),
        "i18n_panes": _i18n_panes(tenant, ("about_title", "about_text")),
        # Превью слайда — сама страница «Über uns» (шаблон виден сразу).
        "preview_url": "/ueber-uns/",
    }


def _post_texts(request):
    # AB6.2g→AB6.10: слайд слим-нут до правового (about уехал на слайд `about`):
    # Impressum → LegalDoc дефолт-локали (реюз семантики legal_docs, presence-safe).
    val = request.POST.get("impressum")
    if val is not None:
        from apps.core.models import LegalDoc

        loc = request.tenant.default_locale or "de"
        if val.strip():
            LegalDoc.objects.update_or_create(kind="impressum", locale=loc, defaults={"text": val})
        else:
            LegalDoc.objects.filter(kind="impressum", locale=loc).delete()


def _ctx_texts(request):
    tenant = request.tenant
    impressum = ""
    try:
        from apps.core.models import LegalDoc

        doc = LegalDoc.objects.filter(
            kind="impressum", locale=tenant.default_locale or "de"
        ).first()
        impressum = doc.text if doc else ""
    except Exception:  # noqa: BLE001 — модель/таблица недоступна
        impressum = ""
    return {"impressum": impressum}


# AB6.2c: типы сущностей, для которых слайд «Angebot» показывает мини-форму создания
# первой позиции (по primary-архетипу). jobs (Anfrage/смета) и promotions — без
# создаваемой сущности → только пресеты/CTA. Плейсхолдер имени — язык задач архетипа.
_OFFER_KINDS = ("catalog", "booking", "stays", "events")
_OFFER_NAME_PH = {
    "catalog": gettext_lazy("z. B. Roggenbrot"),
    "booking": gettext_lazy("z. B. Haarschnitt"),
    "stays": gettext_lazy("z. B. Doppelzimmer"),
    "events": gettext_lazy("z. B. Sommerkonzert"),
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

            # Фидбэк 2026-07-30: у услуги своя страница — per-pk ссылка.
            for s in Service.objects.all().order_by("-created_at")[:8]:
                rows.append(
                    {"name": s.name or "—", "url": reverse("booking:service-edit", args=[s.pk])}
                )
        elif kind == "stays":
            from apps.stays.models import StayUnit

            # Фидбэк 2026-07-30: у номера своя страница — per-pk ссылка.
            for u in StayUnit.objects.all().order_by("-created_at")[:8]:
                rows.append({"name": u.name or "—", "url": reverse("stays:unit-edit", args=[u.pk])})
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
            from apps.stays.models import StaySettings, StayUnit

            StayUnit.objects.create(name=name, price_cents=cents)
            # Lücken-Deal из первичных настроек (чекбокс слайда; дефолты 3/25,
            # включаем только если владелец ещё не настраивал).
            if request.POST.get("gap_deal"):
                stay_settings = StaySettings.load()
                if stay_settings.gap_max_nights == 0:
                    stay_settings.gap_max_nights = 3
                    stay_settings.gap_discount_percent = 25
                    stay_settings.save(
                        update_fields=["gap_max_nights", "gap_discount_percent", "updated_at"]
                    )
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


# AB6.10: слайд «Produktseite» — вид детальной страницы primary-сущности (v1 по
# решению владельца 2026-07-11: стиль карточек site_defaults + скрытие секций
# реестра detail_sections; полные пресеты раскладки — отдельный L-трек).
_CARD_STYLE_PRESETS = (
    {
        "key": "klar",
        "label": gettext_lazy("Klar"),
        "hint": gettext_lazy("ohne Rahmen, viel Weißraum"),
        "defaults": {"card_radius": 0, "card_shadow": False, "card_bg": "", "card_padding": 0},
    },
    {
        "key": "weich",
        "label": gettext_lazy("Weich"),
        "hint": gettext_lazy("runde Ecken, leichter Schatten"),
        "defaults": {"card_radius": 16, "card_shadow": True, "card_bg": "", "card_padding": 0},
    },
    {
        "key": "karte",
        "label": gettext_lazy("Karte"),
        "hint": gettext_lazy("Kachel mit Fläche und Innenabstand"),
        "defaults": {
            "card_radius": 12,
            "card_shadow": True,
            "card_bg": "#ffffff",
            "card_padding": 12,
        },
    },
)

# Превью слайда «Produktseite»: деталь ПЕРВОЙ сущности primary-модуля.
_DETAIL_PREVIEW = {
    "catalog": ("apps.catalog.models", "Product", {"is_active": True}, "storefront-product"),
    "booking": (
        "apps.booking.models",
        "Service",
        {"is_active": True},
        "storefront-service-detail",
    ),
    "stays": ("apps.stays.models", "StayUnit", {"is_active": True}, "storefront-unterkunft-unit"),
    "events": ("apps.events.models", "Event", {}, "storefront-event"),
}


def _detail_preview_url(tenant) -> str:
    """URL детали первой сущности primary-модуля (или "" → превью показывает главную)."""
    import importlib

    from django.urls import reverse

    route = _DETAIL_PREVIEW.get(_offer_kind(tenant) or "")
    if not route:
        return ""
    mod_path, cls_name, flt, url_name = route
    try:
        model = getattr(importlib.import_module(mod_path), cls_name)
        obj = model.objects.filter(**flt).first()
        return reverse(url_name, args=[obj.pk]) if obj else ""
    except Exception:  # noqa: BLE001 — модуль выключен / нет таблицы
        return ""


def _post_detail(request):
    # AB6.10: стиль карточек (глобальные site_defaults → --sf-*) + видимость секций
    # детали primary-модуля (cfg["<module>_detail"]["hidden"] — семантика page_inspector).
    from apps.core import detail_sections
    from apps.tenants import siteconfig

    tenant = request.tenant
    module = _offer_kind(tenant)
    if not module:
        return
    cfg = siteconfig.normalize(tenant.site_config)
    preset = next(
        (p for p in _CARD_STYLE_PRESETS if p["key"] == request.POST.get("card_style")), None
    )
    if preset is not None:
        # STU-11 (ревью, класс W6): пресет описывает ЧЕТЫРЕ ключа вида карточки, а
        # присваивание заменяло `site_defaults` целиком — клик по плитке молча уносил
        # всё остальное (ширину текста, форму карточки, вид выбора вариантов, шаблон
        # категории, hero_widget). Ловушка была самоусиливающейся: `current` ниже
        # сравнивал ВЕСЬ словарь с пресетом, поэтому у владельца с любым лишним ключом
        # ни одна плитка не подсвечена — его прямо приглашали кликнуть. Мержим.
        cfg["site_defaults"] = {**(cfg.get("site_defaults") or {}), **preset["defaults"]}
    key = siteconfig.detail_section_config_key(module)
    nd = siteconfig.normalize_detail_sections(cfg.get(key), module)
    hideable = [s.key for s in detail_sections.sections_for(module) if s.hideable]
    nd["hidden"] = sorted(k for k in hideable if not request.POST.get(f"ds_{k}"))
    cfg[key] = nd
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=["site_config", "updated_at"])


def _ctx_detail(request):
    from apps.core import detail_sections
    from apps.tenants import siteconfig

    tenant = request.tenant
    module = _offer_kind(tenant)
    cfg = siteconfig.normalize(tenant.site_config)
    sd = siteconfig.normalize_site_defaults(cfg.get("site_defaults"))
    # STU-11: сравниваем ТОЛЬКО ключи пресета. Полное сравнение словаря давало «ни одна
    # плитка не выбрана» любому, у кого есть хоть один посторонний ключ site_defaults.
    current = next(
        (
            p["key"]
            for p in _CARD_STYLE_PRESETS
            if all(sd.get(k) == v for k, v in p["defaults"].items())
        ),
        "",
    )
    hidden = siteconfig.detail_section_hidden(cfg, module) if module else set()
    return {
        "card_styles": [{**p, "checked": p["key"] == current} for p in _CARD_STYLE_PRESETS],
        "detail_sections": [
            {"key": s.key, "label": s.label, "on": s.key not in hidden}
            for s in (detail_sections.sections_for(module) if module else ())
            if s.hideable
        ],
        "preview_url": _detail_preview_url(tenant),
    }


# AB6.2: карта слайдов master-slides-v3 §0d. business — escape-hatch (gate скрывает,
# но handler нужен для ?step=); stil = галерея архетип-шаблонов (бывш. template =
# «весь образ архетипа одним кликом»); menu/category/payment/texts — стабы (наполнение
# AB6.2b-g); company=бывш.basics, offer=бывш.content, home=бывш.hero.
def _ctx_start(request):
    from apps.tenants import demo

    return {"has_demo": demo.has_demo(request.tenant)}


# AIS-W W4-2: шаг v4 «Angebot prüfen» — строки «Name — Preis» → таблица проверки → пачка.
_PRUEFEN_KIND_LABELS = {
    "waren": gettext_lazy("Waren"),
    "speisekarte": gettext_lazy("Speisekarte"),
    "termine": gettext_lazy("Termine"),
    "zimmer": gettext_lazy("Zimmer"),
    "tickets": gettext_lazy("Veranstaltungen"),
    "anfragen": gettext_lazy("Leistungen auf Anfrage"),
}
_PRUEFEN_HINTS = {
    "waren": gettext_lazy("Format: Name — Preis, z. B. „Roggenbrot — 3,50 €“"),
    "speisekarte": gettext_lazy("Format: Name — Preis, z. B. „Cappuccino — 3,40 €“"),
    "termine": gettext_lazy("Format: Name — Dauer — Preis, z. B. „Haarschnitt — 30 Min — 26 €“"),
    "zimmer": gettext_lazy(
        "Format: Name — Gäste — Preis/Nacht, z. B. „Doppelzimmer — 2 Gäste — 89 €“"
    ),
    "tickets": gettext_lazy(
        "Format: Name — Datum Uhrzeit — Preis, z. B. „Konzert — 20.07. 19 Uhr — 25 €“"
    ),
    "anfragen": gettext_lazy(
        "Eine Leistung pro Zeile, Preis optional. Ohne Preis steht „Preis auf Anfrage“ — "
        "Kunden fragen über das Formular an."
    ),
}


def _de_amount(value) -> str:
    return "" if value is None else f"{value:.2f}".replace(".", ",", 1)


def _pruefen_row(line) -> dict:
    from django.utils import timezone

    price = _de_amount(line.price)
    return {
        "idx": line.idx,
        "on": not line.errors,
        "name": line.name,
        "price": f"ab {price}" if line.price_from and price else price,
        "duration": str(line.duration_min or ""),
        "guests": str(line.guests or ""),
        "starts_at": (
            timezone.localtime(line.starts_at).strftime("%d.%m.%Y %H:%M") if line.starts_at else ""
        ),
        "example": line.example,
        "errors": line.errors,
        "warnings": line.warnings,
    }


def _ctx_pruefen(request):
    from apps.core import (
        directions,
        offer_batch,
        offer_examples,
        offer_lines,
        offer_pdf,
        offer_photo,
        offer_sentence,
    )

    tenant = request.tenant
    kinds = offer_batch.offer_kinds(tenant, request.user)
    draft = offer_batch.get_draft(request) or {}
    kind = draft.get("kind") if draft.get("kind") in kinds else None
    wanted = request.GET.get("kind")
    kind = kind or (wanted if wanted in kinds else None) or (kinds[0] if kinds else "")
    rows, notes, review = [], [], bool(kind and draft.get("batch") and draft.get("kind") == kind)
    rooms = _pruefen_rooms() if "zimmer" in kinds else []
    chosen = set(offer_batch.chosen_directions(tenant))
    active = {d.key for d in directions.active(tenant)}
    defaults = set(directions.defaults_for(tenant.business_type))
    picked = chosen or active | defaults
    choices = [
        {"key": d.key, "label": d.label, "blurb": d.blurb, "checked": d.key in picked}
        for d in offer_batch.direction_choices(tenant)
    ]
    if review:
        examples = frozenset(offer_examples.lines_for(tenant.business_type, kind))
        try:
            parsed = offer_lines.parse_lines(draft.get("text", ""), kind, examples=examples)
        except offer_lines.OfferTextTooLong:
            parsed = offer_lines.Parsed(lines=[])
        rows = [_pruefen_row(x) for x in parsed.lines]
        notes = parsed.notes
    from apps.tenants import onboarding

    have = set(onboarding.had(tenant))
    text = draft.get("text", "") if draft.get("kind") == kind else ""
    # AIS-3: «Nichts davon» — образцы сразу в поле (как «Beispiele einfügen»; в базу — ничего).
    from_sentence = False
    if not text and not review and kind and not _offer_items(tenant):
        # AIS-2: свои слова владельца сильнее образцов «Nichts davon»
        said = offer_sentence.lines_for_kind(onboarding.sentence_lines(tenant), kind)
        if said:
            text, from_sentence = said, True
        elif "none" in have:
            text = "\n".join(offer_examples.lines_for(tenant.business_type, kind))
    return {
        "pruefen_kinds": [{"key": k, "label": _PRUEFEN_KIND_LABELS[k]} for k in kinds],
        "pruefen_kind": kind,
        "pruefen_hint": _PRUEFEN_HINTS.get(kind, ""),
        "pruefen_text": text,
        "photo_chosen": "photo" in have,
        "quelle_import": _quelle_import_card(request),
        "pruefen_review": review,
        "pruefen_batch": draft.get("batch", ""),
        "pruefen_rows": rows,
        "pruefen_notes": notes,
        "pruefen_ok": sum(1 for r in rows if r["on"]),
        "pruefen_bad": sum(1 for r in rows if r["errors"]),
        "pruefen_max": offer_lines.MAX_LINES,
        "offer_items": [] if "zimmer" in kinds else _offer_items(tenant),
        "pruefen_rooms": rooms,
        "pruefen_directions": choices,
        "pruefen_directions_open": not kinds
        or (tenant.business_type in offer_batch.ASK_TYPES and not chosen),
        "pruefen_directions_summary": ", ".join(str(c["label"]) for c in choices if c["checked"]),
        "pruefen_rooms_missing": any(not r["has_photo"] for r in rooms),
        # W4-4: фото меню → строки (кнопка только при включённой задаче ИИ).
        "pruefen_scan_kinds": offer_photo.kinds_for(kinds),
        "pruefen_scan_photo": offer_photo.enabled(),  # AIS-4: без ИИ блок принимает только PDF
        "pruefen_scan_pdf_ai": offer_pdf.enabled(),
        "pruefen_scan_state": offer_photo.state(request),  # только чтение (GET)
        "pruefen_from_photo": review and draft.get("source") == "photo",
        "pruefen_from_pdf": review and draft.get("source") == "pdf",
        "pruefen_from_sentence": from_sentence,
        "pruefen_scan_max": offer_photo.MAX_PHOTOS,
        "ai_label": offer_photo.AI_LABEL,
    }


def _pruefen_rooms() -> list[dict]:
    """Номера для «Schon angelegt» с отметкой фото (без фото — нет онлайн-брони)."""
    from django.urls import reverse

    from apps.stays.models import StayUnit

    return [
        {
            "pk": u.pk,
            "name": u.name or "—",
            "has_photo": bool(u.images),
            "meta": u.max_guests,
            "price": _de_amount(u.price_cents / 100) if u.price_cents else "",
            "url": reverse("stays:unit-edit", args=[u.pk]),
        }
        for u in StayUnit.objects.filter(is_active=True).order_by("-created_at")[:12]
    ]


def _quelle_options(request) -> list[dict]:
    """AIS-3: карточки «Was haben Sie schon?» — только доступные этому бизнесу (гейты те же,
    что у самих потоков: без ключа Google/ИИ карточки нет вовсе)."""
    from apps.core import offer_photo, setup_google
    from apps.tenants import onboarding

    tenant = request.tenant
    chosen = set(onboarding.had(tenant))
    opts = [
        ("website", _("Eigene Website"), _("Wir lesen Produkte, Preise und Kontaktdaten.")),
        (
            "google",
            _("Google-Profil"),
            _("Adresse, Telefon und Öffnungszeiten — Sie suchen im nächsten Schritt."),
        ),
        (
            "photo",
            _("Foto der Speisekarte oder Preisliste"),
            _("1–3 Fotos. Wir lesen Namen und Preise."),
        ),
        ("none", _("Nichts davon"), _("Wir zeigen Beispiele — Sie ändern sie.")),
    ]
    from apps.core.roles import is_owner

    available = {
        # импорт с сайта — только владельцу (как экран импорта)
        "website": is_owner(request.user),
        "google": setup_google.enabled(tenant),
        "photo": offer_photo.enabled(),
        "none": True,
    }
    return [
        {
            "key": k,
            "label": label,
            "hint": hint,
            "checked": k in chosen,
            "ai": k == "photo",
            "url": k == "website",
        }
        for k, label, hint in opts
        if available[k]
    ]


def _wizard_run(tenant):
    """Прогон импорта, запущенный из мастера (любой статус) — или None."""
    from apps.tenants import onboarding

    run_id = onboarding.import_run_id(tenant)
    if not run_id:
        return None
    from django.core.exceptions import ValidationError

    from apps.imports.models import SiteImportRun

    try:
        return SiteImportRun.objects.filter(pk=run_id).first()
    except (ValueError, ValidationError):  # мусор в state — прогона нет
        return None


def _quelle_run(tenant):
    """Живой прогон мастера (упавший — «прогона нет»: можно запустить заново)."""
    run = _wizard_run(tenant)
    return None if run is None or run.status == run.STATUS_FAILED else run


def _quelle_import_card(request) -> dict | None:
    """AIS-3: карточка статуса импорта на шаге «Angebot»."""
    from apps.tenants import onboarding

    if "website" not in onboarding.had(request.tenant):
        return None
    run = _wizard_run(request.tenant)
    if run is None:
        return None
    from django.urls import reverse

    from apps.imports.site import verify

    if run.status == run.STATUS_FAILED:
        state = "failed"
    elif run.status in run.ACTIVE:
        state = "running"
    elif run.status == run.STATUS_APPLIED:
        state = "applied"
    else:
        state = "ready" if verify.is_verified(run) else "verify"
    back = reverse("setup") + "?step=pruefen"
    return {
        "state": state,
        "host": run.host,
        "count": run.items.count(),
        "url": reverse("imports:website-run", args=[run.pk]) + "?next=" + back,
    }


def _ctx_quelle(request):
    from apps.tenants import onboarding

    tenant = request.tenant
    return {
        "quelle_options": _quelle_options(request),
        "quelle_url": request.session.get("quelle_url") or tenant.website_url or "",
        "quelle_sentence": onboarding.sentence(tenant),
        "quelle_sentence_max": onboarding.SENTENCE_MAX,
    }


def _save_sentence(request) -> None:
    """AIS-2: фраза → строки для «Angebot prüfen» (в базу ничего). Планировщик (и ИИ)
    зовётся только по «Weiter» и только при изменённой фразе или пустом прежнем результате
    (лимит/сбой ИИ не застревают навсегда); поле, которого нет в POST, состояние не трогает;
    «Zurück»/«Überspringen» фразу не обрабатывают."""
    from apps.core import offer_sentence
    from apps.tenants import onboarding

    if "sentence" not in request.POST or request.POST.get("action") in ("back", "skip", "live"):
        return
    tenant = request.tenant
    text = (request.POST.get("sentence") or "").strip()[: onboarding.SENTENCE_MAX]
    if text and text == onboarding.sentence(tenant) and onboarding.sentence_lines(tenant):
        return
    if not text and not onboarding.sentence(tenant):
        return
    if not text:
        onboarding.set_sentence(tenant, "", [])
        return
    result = offer_sentence.build(tenant, request.user, text)
    onboarding.set_sentence(tenant, text, result.lines)
    if result.note:
        messages.info(request, str(result.note))


def _post_quelle(request):
    """AIS-3: запомнить выбор — и только (бизнес-данные пишут шаги, куда он ведёт).

    «Eigene Website» запускает ТОТ ЖЕ импорт, что экран кабинета (`start_run`: проверка
    адреса, SSRF-защита при обходе, лимиты, подтверждение владения ДО применения). Мастер не
    ждёт прогона: статус покажет шаг «Angebot». Выбор сохраняется ДО запуска — забытая
    галочка согласия не стирает остальные отметки."""
    from apps.tenants import onboarding

    tenant = request.tenant
    _save_sentence(request)  # AIS-2: до ветки website — забытое согласие фразу не теряет
    allowed = {o["key"] for o in _quelle_options(request)}
    keys = [k for k in request.POST.getlist("had") if k in allowed]
    # Чужие варианты (сотруднику Website не показан) — не наши, выбор владельца не теряем.
    keys += [k for k in onboarding.had(tenant) if k not in allowed]
    keys = onboarding.set_had(tenant, keys)
    if "website" not in keys:
        request.session.pop("quelle_url", None)
        return None
    if "website" not in allowed or _quelle_run(tenant):
        return None  # прогон уже есть (или вариант не наш) — второй не стартуем
    from apps.imports.site import service

    url = (request.POST.get("site_url") or "").strip()[:500]
    request.session["quelle_url"] = url  # ввод не теряется при ошибке
    if request.POST.get("consent") != "1":
        messages.error(request, _("Bitte bestätigen Sie, dass Sie Inhaber der Website sind."))
        return False
    try:
        run = service.start_run(user=request.user, url=url)
    except service.StartError as exc:
        run = _active_run()  # прогон уже идёт (напр. запущен из кабинета) — берём его
        if run is None:
            messages.error(request, str(exc))
            return False
    request.session.pop("quelle_url", None)
    onboarding.set_had(tenant, keys, import_run=run.pk)
    return None


def _active_run():
    from apps.imports.models import SiteImportRun

    return SiteImportRun.objects.filter(status__in=SiteImportRun.ACTIVE).first()


HANDLERS = {
    "business": StepHandler(
        template="tenant/setup/_step_business.html", post=_post_business, context=_ctx_business
    ),
    # AB6.9: первый видимый слайд — «богатое» демо одним кликом (первый логический шаг).
    "start": StepHandler(
        template="tenant/setup/_step_start.html", context=_ctx_start, preview=True
    ),
    "quelle": StepHandler(
        template="tenant/setup/_step_quelle.html", post=_post_quelle, context=_ctx_quelle
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
    "pruefen": StepHandler(template="tenant/setup/_step_pruefen.html", context=_ctx_pruefen),
    # AB6.10: вид страницы товара — стиль карточек + секции детали; превью открывает
    # деталь первой сущности (preview_url в контексте).
    "detail": StepHandler(
        template="tenant/setup/_step_detail.html",
        post=_post_detail,
        context=_ctx_detail,
        preview=True,
        live=True,
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
    # AB6.10: «Über uns» — тексты + шаблон страницы (пресеты блоков info-хоста);
    # превью показывает саму /ueber-uns/.
    "about": StepHandler(
        template="tenant/setup/_step_about.html",
        post=_post_about,
        context=_ctx_about,
        preview=True,
        live=True,
    ),
    "texts": StepHandler(
        template="tenant/setup/_step_texts.html", post=_post_texts, context=_ctx_texts
    ),
    "recht": StepHandler(
        template="tenant/setup/_step_recht.html",
        post=_post_recht,
        context=_ctx_recht,
        preview=True,
    ),
    "done": StepHandler(template="tenant/setup/_step_done.html"),
}
