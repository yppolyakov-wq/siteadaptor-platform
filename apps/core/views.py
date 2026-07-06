"""Общие tenant-facing вьюхи (живут в схеме арендатора)."""

import json as _json
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import detail_sections
from apps.tenants import domains
from apps.tenants.forms import BusinessSettingsForm
from apps.tenants.models import CustomDomain


@login_required
def extras_view(request):
    """#7: универсальные доп-услуги (Extra) — CRUD на одной странице.

    Один движок на все архетипы (stays/booking/events); scope ограничивает
    применимость. Сейчас на витрине подключены stays."""
    from apps.core.models import Extra

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "add":
            label = request.POST.get("label", "").strip()[:120]
            if label:
                try:
                    cents = max(
                        0, round(float(request.POST.get("price", "0").replace(",", ".")) * 100)
                    )
                except (TypeError, ValueError):
                    cents = 0
                extra = Extra.objects.create(
                    label=label,
                    price_cents=cents,
                    scope=request.POST.get("scope", Extra.SCOPE_ALL),
                    per_night=bool(request.POST.get("per_night")),
                )
                _set_extra_image(request, extra)  # A5: опц. фото при создании
                messages.success(request, _("Extra added."))
        elif action == "set_image":  # A5: загрузить/заменить фото доп-услуги
            extra = get_object_or_404(Extra, pk=request.POST.get("extra"))
            if _set_extra_image(request, extra):
                messages.success(request, _("Photo updated."))
            else:
                messages.error(request, _("Couldn't upload the image — please try another file."))
        elif action == "toggle":
            extra = get_object_or_404(Extra, pk=request.POST.get("extra"))
            extra.is_active = not extra.is_active
            extra.save(update_fields=["is_active", "updated_at"])
        elif action == "delete":
            Extra.objects.filter(pk=request.POST.get("extra")).delete()
            messages.success(request, _("Extra removed."))
        return redirect("extras")

    return render(
        request,
        "tenant/extras.html",
        {
            "nav": "extras",
            "extras": Extra.objects.all(),
            "scopes": Extra.SCOPES,
        },
    )


def _set_extra_image(request, extra) -> bool:
    """A5: сохранить загруженное фото доп-услуги в extra.image (FileRef). True при
    успехе; False — файла нет или он невалиден (CRUD не роняем)."""
    uploaded = request.FILES.get("image")
    if not uploaded:
        return False
    from django.core.exceptions import ValidationError

    from apps.catalog import images

    try:
        images.validate_image(uploaded)
        ref = images.save_product_image(uploaded, folder="extras")
    except (ValidationError, ValueError, OSError):
        return False
    extra.image = ref
    extra.save(update_fields=["image", "updated_at"])
    return True


@login_required
def dashboard(request):
    """Главная кабинета владельца."""
    from apps.tenants import onboarding

    state = onboarding.get_state(request.tenant)
    # AB5 (анти-Битрикс): свежезарегистрированный владелец, ещё не тронувший
    # мастер (нетронутое состояние: шаг 1, без пропусков, не завершён), попадает
    # сразу в Onboarding-Wizard, а не в пустой кабинет. Любое действие в мастере
    # (Weiter/Überspringen/Zurück) уводит из нетронутого состояния и снимает
    # редирект — навигация остального кабинета не гейтится.
    if not state["completed"] and state["step"] == 1 and not state["skipped"]:
        return redirect("setup")

    setup_done, setup_total = onboarding.progress(request.tenant)
    return render(
        request,
        "tenant/dashboard.html",
        {
            "nav": "dashboard",
            "setup_done": setup_done,
            "setup_total": setup_total,
            "setup_completed": onboarding.get_state(request.tenant)["completed"],
            "readiness": onboarding.completeness(request.tenant),  # AB4: чек-лист готовности
        },
    )


@login_required
def setup_view(request):
    """Onboarding-Wizard (Track D / D0c): пошаговая настройка после регистрации.

    ≤5 шагов, одно решение на шаг, «Überspringen» на каждом; состояние в
    Tenant.site_config["onboarding"] (apps.tenants.onboarding) — мастер
    резюмируется с текущего шага.
    """
    from apps.core import modules as registry
    from apps.promotions import presets
    from apps.tenants import demo, onboarding, siteconfig
    from apps.tenants.models import Tenant

    tenant = request.tenant
    state = onboarding.get_state(tenant)
    step = state["step"]

    if request.method == "POST":
        # AB3-v2 «живое превью»: сохранить поля текущего шага БЕЗ перехода дальше
        # (debounced fetch при вводе/выборе) — iframe-превью сразу перечитывает витрину.
        is_live = request.POST.get("action") == "live"
        if request.POST.get("action") == "skip":
            onboarding.advance(tenant, skip=True)
            return redirect("setup")
        if request.POST.get("action") == "back":
            onboarding.back(tenant)
            return redirect("setup")
        # B.1 (анти-Битрикс): наполнить сайт демо-контентом прямо из мастера, чтобы
        # после онбординга витрина была НЕ пустой (обратимо). Остаёмся на шаге 4.
        if request.POST.get("action") == "load_demo":
            if demo.load_demo(tenant):
                messages.success(request, _("Example content added — your site isn't empty."))
            return redirect("setup")
        if request.POST.get("action") == "clear_demo":
            if demo.clear_demo(tenant):
                messages.info(request, _("Example content removed."))
            return redirect("setup")
        if step == 1:
            business_type = request.POST.get("business_type", "")
            if business_type in dict(Tenant.BUSINESS_TYPES):
                # Гибрид (решение владельца 2026-06-12): набор блоков должен
                # подходить типу — при СМЕНЕ типа пресет вертикали применяется
                # заново (магазину Booking выключится). Если тип не менялся,
                # ручную/легаси конфигурацию не трогаем (hotfix run 122) —
                # кроме случая, когда набор ещё равен пресету (нечего терять).
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
        elif step == 2:
            # B.2: выбор шаблона витрины (раскладка+тексты+акцент) одним кликом.
            from apps.tenants import sitetemplates

            sitetemplates.apply_template(tenant, request.POST.get("template", ""))
        elif step == 3:
            enabled_keys = set(request.POST.getlist("modules"))
            tenant.disabled_modules = [
                spec.key for spec in registry.optional_modules() if spec.key not in enabled_keys
            ]
            tenant.save(update_fields=["disabled_modules", "updated_at"])
        elif step == 4:
            for field in ("address", "opening_hours", "contact_phone", "contact_email"):
                setattr(tenant, field, request.POST.get(field, "").strip())
            tenant.save(
                update_fields=[
                    "address",
                    "opening_hours",
                    "contact_phone",
                    "contact_email",
                    "updated_at",
                ]
            )
        elif step == 5:
            # B.3: баннер — заголовок/подзаголовок hero + опц. загрузка фото файлом.
            _save_hero(request, tenant)
        # Шаг 6 — демо/пресеты (action-кнопки выше); «Weiter» просто двигает дальше.
        if is_live:
            from django.http import HttpResponse

            return HttpResponse(status=204)  # остаёмся на шаге; превью перечитает витрину
        onboarding.advance(tenant)
        return redirect("setup")

    context = {"nav": "dashboard", "step": step, "total": onboarding.TOTAL_STEPS, "state": state}
    if step == 1:
        context["business_types"] = onboarding.business_type_cards()
    elif step == 2:
        # B.2: шаблоны витрины как визуальные карточки (рекомендованные типу — сверху).
        from apps.tenants import sitetemplates

        config = siteconfig.normalize(tenant.site_config)
        active = [s["key"] for s in config["sections"] if s["enabled"]]
        context["templates"] = sitetemplates.templates_for(tenant.business_type)
        context["current_sections"] = active
    elif step == 3:

        def _row(spec):
            return {
                "spec": spec,
                "enabled": spec.key not in (tenant.disabled_modules or []),
                "recommended": tenant.business_type in spec.recommended_for,
                "suited_label": registry.suited_label(spec),
            }

        optional = registry.optional_modules()
        # Гибрид: подходящие типу — сверху, остальные — «Weitere Bausteine».
        context["module_rows"] = [
            _row(spec) for spec in optional if registry.is_suited_for(spec, tenant.business_type)
        ]
        context["other_module_rows"] = [
            _row(spec)
            for spec in optional
            if not registry.is_suited_for(spec, tenant.business_type)
        ]
    elif step == 5:
        # B.3: текущие значения баннера для предзаполнения.
        config = siteconfig.normalize(tenant.site_config)
        context["hero_title"] = config["hero_title"]
        context["hero_text"] = config["hero_text"]
        context["hero_image"] = config["hero_image"]
    elif step == 6:
        context["presets"] = presets.presets_for(tenant.business_type)
        context["has_demo"] = demo.has_demo(tenant)  # B.1: предложить/убрать демо-контент
    return render(request, "tenant/setup.html", context)


def _read_cblock_data(post, bid: str, btype: str) -> dict:
    """D.2b: собрать data C-блока из полей формы `cb_<id>_<field>` (normalize чистит)."""

    def f(name):
        return post.get(f"cb_{bid}_{name}", "").strip()

    # UC6-2: стиль текста (align/size/color) — text и image_text; normalize
    # держит только валидные не-дефолтные значения (_text_style).
    style = {"align": f("align"), "size": f("size"), "color": f("color")}
    if btype == "text":
        return {"title": f("title"), "body": f("body"), **style}
    if btype == "image":
        # UC6-4: rounded — скругление фото (normalize валидирует).
        return {"url": f("url"), "caption": f("caption"), "rounded": f("rounded")}
    if btype == "image_text":
        return {
            "url": f("url"),
            "title": f("title"),
            "body": f("body"),
            "side": f("side"),
            "rounded": f("rounded"),
            **style,
        }
    if btype == "button":
        return {"label": f("label"), "url": f("url")}
    if btype == "promo":
        # UE1 (D2=LIVE): promo_pk — просто строка; show_button — чекбокс.
        return {
            "promo_pk": f("promo_pk"),
            "align": f("align"),
            "badge_pos": f("badge_pos"),
            "show_button": post.get(f"cb_{bid}_show_button") == "on",
            "button_label": f("button_label"),
        }
    return {}


def _promos_for_blocks(request):
    """UE1: [(pk, подпись)] активных/запланированных промо для селектора блока.
    Fail-safe: без модуля promotions/ошибке — пустой список (блок просто пуст)."""
    try:
        from apps.promotions.models import Promotion

        return [
            (str(p.pk), p.title_text or str(p.pk))
            for p in Promotion.objects.filter(status__in=("active", "scheduled")).order_by(
                "-created_at"
            )[:50]
        ]
    except Exception:  # noqa: BLE001
        return []


def _insert_after_section(sections: list, block: dict, after: str) -> None:
    """SE-4c: вставить block сразу ПОСЛЕ секции с key/id == after (инсертер «+» на
    канвасе). Пусто/не найдено → в конец. Общий путь для add_block и use_block_template."""
    after = (after or "").strip()
    if after:
        for i, s in enumerate(sections):
            if s.get("id") == after or s.get("key") == after:
                sections.insert(i + 1, block)
                return
    sections.append(block)


def _save_hero(request, tenant):
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


def _save_logo(request) -> None:
    """M1: загрузить лого бизнеса (Tenant.logo_url) — в шапке витрины вместо
    текстового имени. Реюз catalog.images (валидация Pillow + storage)."""
    from django.core.exceptions import ValidationError

    from apps.catalog.images import save_product_image

    uploaded = request.FILES.get("logo")
    if not uploaded:
        return
    try:
        ref = save_product_image(uploaded, folder="logo")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return
    request.tenant.logo_url = ref["url"]
    request.tenant.save(update_fields=["logo_url", "updated_at"])
    messages.success(request, _("Logo updated."))


def _delete_logo(request) -> None:
    """M1: убрать лого — в шапке снова текстовое имя бизнеса."""
    request.tenant.logo_url = ""
    request.tenant.save(update_fields=["logo_url", "updated_at"])
    messages.success(request, _("Logo removed."))


def _hero_slide_from_post(request, existing_image: str = "") -> dict:
    """M2: слайд баннера из формы — текст + опц. фото (файл приоритетнее URL)."""
    slide = {
        "image": existing_image,
        "title": request.POST.get("hero_s_title", "").strip(),
        "text": request.POST.get("hero_s_text", "").strip(),
        "button_label": request.POST.get("hero_s_btn_label", "").strip(),
        "button_url": request.POST.get("hero_s_btn_url", "").strip(),
    }
    uploaded = request.FILES.get("hero_s_image")
    url = request.POST.get("hero_s_image_url", "").strip()
    if uploaded:
        from django.core.exceptions import ValidationError

        from apps.catalog.images import save_product_image

        try:
            slide["image"] = save_product_image(uploaded, folder="hero")["url"]
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    elif url:
        slide["image"] = url
    return slide


def _hero_slide_index(request) -> int:
    try:
        return int(request.POST.get("slide_index", ""))
    except (ValueError, TypeError):
        return -1


def _save_hero_slide(request) -> None:
    """M2: создать/обновить слайд баннера (site_config['heroes'], ≤6). slide_index пуст → добавить."""
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    heroes = list(cfg.get("heroes") or [])
    idx = _hero_slide_index(request)
    existing = heroes[idx]["image"] if 0 <= idx < len(heroes) else ""
    slide = _hero_slide_from_post(request, existing_image=existing)
    if 0 <= idx < len(heroes):
        heroes[idx] = slide
    elif len(heroes) < siteconfig._MAX_HEROES:
        heroes.append(slide)
    else:
        messages.info(request, _("Slide limit reached (max 6)."))
        return
    cfg["heroes"] = heroes
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, _("Banner slide saved."))


def _delete_hero_slide(request) -> None:
    """M2: удалить слайд баннера по индексу."""
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    heroes = list(cfg.get("heroes") or [])
    idx = _hero_slide_index(request)
    if 0 <= idx < len(heroes):
        heroes.pop(idx)
        cfg["heroes"] = heroes
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, _("Slide removed."))


def _move_hero_slide(request) -> None:
    """M2: переставить слайд баннера (up/down)."""
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    heroes = list(cfg.get("heroes") or [])
    idx = _hero_slide_index(request)
    j = idx + (-1 if request.POST.get("dir") == "up" else 1)
    if 0 <= idx < len(heroes) and 0 <= j < len(heroes):
        heroes[idx], heroes[j] = heroes[j], heroes[idx]
        cfg["heroes"] = heroes
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])


def _parse_opening_hours(request) -> dict:
    """Структурные часы из формы (P1b): по дню оба поля заполнены → интервал."""
    out = {}
    for wd in range(7):
        o = (request.POST.get(f"oh_{wd}_open") or "").strip()
        c = (request.POST.get(f"oh_{wd}_close") or "").strip()
        if o and c:
            out[str(wd)] = [o, c]
    from apps.tenants import openinghours

    return openinghours.normalize(out)  # валидация (open<close, формат)


def _opening_hours_rows(tenant) -> list:
    """7 строк для редактора часов: (индекс, DE-метка, open, close)."""
    from apps.tenants import openinghours

    hours = openinghours.normalize(tenant.opening_hours_structured)
    rows = []
    for wd in range(7):
        rng = hours.get(str(wd)) or ["", ""]
        rows.append(
            {"wd": wd, "label": openinghours.WEEKDAYS_DE[wd], "open": rng[0], "close": rng[1]}
        )
    return rows


@login_required
def settings_view(request):
    """Настройки бизнеса: контакты, часы работы (структурно) и правовые тексты."""
    form = BusinessSettingsForm(request.POST or None, instance=request.tenant)
    if request.method == "POST" and form.is_valid():
        tenant = form.save(commit=False)
        tenant.opening_hours_structured = _parse_opening_hours(request)
        tenant.save()
        messages.success(request, "Gespeichert.")
        return redirect("settings")
    return render(
        request,
        "tenant/settings.html",
        {
            "form": form,
            "nav": "settings",
            "opening_hours_rows": _opening_hours_rows(request.tenant),
        },
    )


@login_required
def languages_view(request):
    """L2 (Волна L): кабинет «Sprachen» — какие языки витрины включены + дефолт.

    Владелец включает подмножество языков из системного реестра `settings.LANGUAGES`
    (что вообще есть в платформе) и выбирает дефолтный. Пишет `Tenant.enabled_locales`
    / `default_locale` (без миграции — поля уже есть). Витрина/оверлей/переключатель
    сразу отражают это через резолвер `Tenant.active_locales` (L1). Генерик по N
    локалям — новая локаль в реестре появляется здесь без правки кода. Инварианты:
    минимум один язык включён; дефолт ∈ включённые.
    """
    registry = [code for code, _label in settings.LANGUAGES]
    tenant = request.tenant
    if request.method == "POST":
        # Порядок — как в реестре (стабильно), дубли/не-реестр отфильтрованы.
        chosen = set(request.POST.getlist("locales"))
        enabled = [code for code in registry if code in chosen]
        if not enabled:
            messages.error(request, _("Please enable at least one language."))
        else:
            default = request.POST.get("default_locale", "")
            if default not in enabled:
                default = enabled[0]  # инвариант: дефолт ∈ включённые
            tenant.enabled_locales = enabled
            tenant.default_locale = default
            tenant.save(update_fields=["enabled_locales", "default_locale"])
            messages.success(request, _("Saved."))
            return redirect("languages")
    lang_names = dict(settings.LANGUAGES)
    current = set(tenant.active_locales)
    languages = [
        {
            "code": code,
            "label": lang_names.get(code, code.upper()),
            "enabled": code in current,
            "is_default": code == tenant.default_locale,
        }
        for code in registry
    ]
    return render(request, "tenant/languages.html", {"languages": languages, "nav": "languages"})


@login_required
def legal_docs_view(request):
    """L5/E-2: кабинет «Recht» — правовые тексты витрины per-locale (LegalDoc).

    4 вида (Impressum/Datenschutz/Widerruf/AGB) × активные локали тенанта.
    Пустая textarea = строка удаляется → работает фолбэк-цепочка legal.py
    (плоское поле настроек / автотекст); для AGB пусто = страницы /agb/ нет.
    Presence-guard: трогаем только присланные поля (name=doc_<kind>_<locale>).
    """
    from apps.core.legal import legal_text
    from apps.core.models import LegalDoc

    tenant = request.tenant
    locales = tenant.active_locales
    if request.method == "POST":
        for kind, _label in LegalDoc.KIND_CHOICES:
            for loc in locales:
                val = request.POST.get(f"doc_{kind}_{loc}")
                if val is None:
                    continue
                if val.strip():
                    LegalDoc.objects.update_or_create(kind=kind, locale=loc, defaults={"text": val})
                else:
                    LegalDoc.objects.filter(kind=kind, locale=loc).delete()
        messages.success(request, _("Saved."))
        return redirect("legal-docs")
    docs = {(d.kind, d.locale): d.text for d in LegalDoc.objects.filter(locale__in=locales)}
    lang_names = dict(settings.LANGUAGES)
    kinds = [
        {
            "kind": kind,
            "label": label,
            "has_fallback": kind != "agb",
            "cells": [
                {
                    "locale": loc,
                    "locale_label": lang_names.get(loc, loc.upper()),
                    "text": docs.get((kind, loc), ""),
                    # что покажет витрина при пустом поле (превью фолбэка)
                    "fallback": "" if kind == "agb" else legal_text(tenant, kind, locale=loc),
                }
                for loc in locales
            ],
        }
        for kind, label in LegalDoc.KIND_CHOICES
    ]
    return render(request, "tenant/legal_docs.html", {"kinds": kinds, "nav": "legal-docs"})


def _upload_gallery_images(request) -> None:
    """Сохранить загруженные фото в site_config['gallery'] (M20 ⑤b).

    Переиспользуем catalog.images.save_product_image (валидация Pillow + storage);
    галерея — FileRef-список в site_config, как Product.images.
    """
    from django.core.exceptions import ValidationError

    from apps.catalog.images import save_product_image
    from apps.tenants import siteconfig

    files = request.FILES.getlist("images")
    if not files:
        return
    cfg = siteconfig.normalize(request.tenant.site_config)
    gallery = list(cfg.get("gallery") or [])
    for f in files:
        if len(gallery) >= siteconfig._MAX_GALLERY:
            messages.info(request, "Galerie-Limit erreicht.")
            break
        try:
            gallery.append(save_product_image(f, sort_order=len(gallery), folder="gallery"))
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
    cfg["gallery"] = gallery
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, "Bilder hochgeladen.")


def _delete_gallery_image(request, image_id: str) -> None:
    """Удалить одно фото галереи (из storage + site_config)."""
    from apps.catalog.images import delete_stored_image
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    gallery, removed = [], None
    for ref in cfg.get("gallery") or []:
        if ref.get("id") == image_id:
            removed = ref
        else:
            gallery.append(ref)
    if removed is not None:
        delete_stored_image(removed)
        cfg["gallery"] = gallery
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Bild gelöscht.")


@login_required
def site_view(request):
    """Конструктор витрины v1 (Track C2): секции главной + тексты hero/about.

    Сверху — галерея шаблонов (ранний срез M20, apps.tenants.sitetemplates):
    выбор готовой раскладки в один клик поверх того же секционного движка.
    """
    from apps.tenants import demo, siteconfig, sitetemplates, storefront

    if request.method == "POST":
        # Применение шаблона витрины (галерея).
        if request.POST.get("action") == "apply_template":
            if sitetemplates.apply_template(request.tenant, request.POST.get("template", "")):
                messages.success(request, "Vorlage übernommen.")
            else:
                messages.error(request, "Unbekannte Vorlage.")
            return redirect("site")
        # Демо-контент (M20): отдельные кнопки загрузки/удаления.
        if request.POST.get("action") == "load_demo":
            if demo.load_demo(request.tenant):
                messages.success(request, "Demo-Inhalte geladen.")
            else:
                messages.info(request, "Demo-Inhalte sind bereits vorhanden.")
            return redirect("site")
        if request.POST.get("action") == "clear_demo":
            if demo.clear_demo(request.tenant):
                messages.success(request, "Demo-Inhalte gelöscht.")
            else:
                messages.info(request, "Keine Demo-Inhalte vorhanden.")
            return redirect("site")
        # Галерея (M20 ⑤b): загрузка/удаление фото (multipart, отдельно от save).
        if request.POST.get("action") == "upload_gallery":
            _upload_gallery_images(request)
            return redirect("site")
        if request.POST.get("action") == "delete_gallery_image":
            _delete_gallery_image(request, request.POST.get("image_id", ""))
            return redirect("site")
        # S2b: композиция главной (порядок/видимость секций + тизеры архетипов)
        # живёт на отдельной странице «Startseite» (home_builder_view). Здесь —
        # дизайн/контент/навигация; секции и оверрайды тизеров переносим как есть.
        current = siteconfig.normalize(request.tenant.site_config)
        config = {"sections": current["sections"], "archetypes": current["archetypes"]}
        for field in siteconfig.TEXT_FIELDS:
            config[field] = request.POST.get(field, "")
        config["hero_style"] = "accent" if request.POST.get("hero_accent") == "on" else "plain"
        config["hero_image"] = request.POST.get("hero_image", "").strip()
        config["font"] = request.POST.get("font", "system")  # P2a: шрифт витрины
        # S7b: навигация витрины правится в билдере меню (/dashboard/site/menu/).
        # Легаси-nav здесь только переносим (из него выводится menus для тенантов,
        # ещё не трогавших билдер) — пустая форма «Site» не должна его гасить.
        config["nav"] = current["nav"]
        # Контент-секции (M20 ⑤a/M20d): CTA / отзывы / FAQ / process / team / trust.
        # Единый парсер — общий с конструктором главной и live-preview-черновиком.
        config.update(siteconfig.parse_content_sections(request.POST.get))
        # T1: видео в галерее — один URL (YouTube/Vimeo/файл).
        config["gallery_video"] = request.POST.get("gallery_video", "").strip()
        # T2c: быстрый заказ («+»/модалка) на карточках — тумблер владельца.
        config["quick_add"] = request.POST.get("quick_add") == "on"
        # Не затираем состояние Onboarding-Wizard (D0c) и реестр демо — тот же JSON.
        previous = (
            request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
        )
        if isinstance(previous.get("onboarding"), dict):
            config["onboarding"] = previous["onboarding"]
        if isinstance(previous.get("demo"), dict):
            config["demo"] = previous["demo"]
        if isinstance(previous.get("gallery"), list):
            config["gallery"] = previous["gallery"]  # фото грузятся отдельной формой
        request.tenant.site_config = siteconfig.normalize(config)
        update_fields = ["site_config", "updated_at"]
        # Акцентный цвет (#rrggbb) → Tenant.primary_color (читает витрина для hero).
        accent = request.POST.get("accent_color", "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) and accent != request.tenant.primary_color:
            request.tenant.primary_color = accent
            update_fields.insert(1, "primary_color")
        request.tenant.save(update_fields=update_fields)
        messages.success(request, "Gespeichert.")
        return redirect("site")

    config = siteconfig.normalize(request.tenant.site_config)
    labels = {key: label for key, label, _default in siteconfig.SECTIONS}
    # Защита (prod 500): config["sections"] может содержать repeatable-блоки
    # (text/image/…, добавленные инсертером «+») и неизвестные ключи — их нет в
    # labels. Пропускаем их, как делает home_builder_view (иначе KeyError → 500).
    sections = [
        {
            "key": s["key"],
            "label": labels[s["key"]],
            "enabled": s["enabled"],
            "order": index,
        }
        for index, s in enumerate(config["sections"], start=1)
        if s["key"] in labels
    ]
    business_type = request.tenant.business_type
    site_templates = [
        {
            "key": t["key"],
            "label": t["label"],
            "description": t["description_de"],
            "recommended": business_type in t["recommended_for"],
            # для мини-превью раскладки: ключ (стиль) + человеческая подпись
            "sections": [{"key": s, "label": labels[s]} for s in t["sections"]],
            "accent": t.get("accent", ""),
            "hero_style": t.get("hero_style", "plain"),
        }
        for t in sitetemplates.templates_for(business_type)
    ]
    # Навигация витрины (M20 ④): пункты в порядке владельца + метки/гейтинг.
    nav_labels = {key: label for key, label, _u, _m in siteconfig.NAV_ITEMS}
    nav_modules_map = {key: mod for key, _l, _u, mod in siteconfig.NAV_ITEMS}
    nav_items = [
        {
            "key": item["key"],
            "label": nav_labels[item["key"]],
            "enabled": item["enabled"],
            "order": index,
            "module": nav_modules_map[item["key"]] or "",
        }
        for index, item in enumerate(config["nav"]["items"], start=1)
    ]
    return render(
        request,
        "tenant/site.html",
        {
            "nav": "site",
            "sections": sections,
            "config": config,
            "site_templates": site_templates,
            # S2: тизер-архетипы для блока «Unsere Bereiche» (заголовок/описание/видимость).
            "archetype_specs": storefront.teaser_specs(request.tenant),
            "nav_items": nav_items,
            "nav_style": config["nav"]["style"],
            "nav_sticky": config["nav"]["sticky"],
            "nav_styles": siteconfig.NAV_STYLES,
            "font_choices": list(siteconfig.FONTS),
            "faq_text": siteconfig.pairs_to_text(config["faq"], "q", "a"),
            "testimonials_text": siteconfig.pairs_to_text(config["testimonials"], "name", "text"),
            "trust_marks_text": "\n".join(config["trust"]["marks"]),
            "process_text": siteconfig.pairs_to_text(config["process"], "title", "text"),
            "team_text": "\n".join(
                f"{m['name']} | {m['role']}".rstrip(" |") for m in config["team"]
            ),
            "usp_text": siteconfig.usp_to_text(config["usp_bar"]),
            "has_demo": demo.has_demo(request.tenant),
        },
    )


# SE-9c → UC1-3: иконки секций переехали в реестр (siteconfig.SECTION_ICONS —
# KEYS+LABELS+ICONS вместе); вьюха читает их через siteconfig. Дефолт — 🧩.


def _safe_preview_page(raw):
    """T-6.1: стартовая страница канвы из ?page= (deep-link «Edit design» с витрины).

    Только внутренний path витрины: абсолютные URL/схемы, протокол-relative
    (``//…``), бэкслэши и DENY-зона кабинета (killswitch канвы, см. T-6)
    откатываются на главную.
    """
    from apps.core.middleware import StorefrontFrameOptionsMiddleware

    raw = (raw or "").split("?")[0]
    if (
        not raw.startswith("/")
        or raw.startswith("//")
        or "\\" in raw
        or raw.startswith(StorefrontFrameOptionsMiddleware._BLOCK_PREFIXES)
    ):
        return "/"
    return raw


@login_required
def home_builder_view(request):
    """Конструктор главной (S2b): порядок/видимость блоков главной + тизеры
    архетипов. Отдельная страница — «подключать/выключать выведение блоков».

    Контент блоков (тексты hero/about, FAQ, галерея, цвета, шрифты, навигация)
    правится на «Site»; здесь — только композиция главной. Сохранение мёржит в
    текущий site_config (остальные настройки не затрагиваются).
    """
    from apps.tenants import siteconfig, storefront

    if request.method == "POST":
        # M20e: медиа галереи — отдельные multipart-формы (upload/delete), общие
        # с «Site» хелперы; обрабатываем до основной формы композиции.
        if request.POST.get("action") == "upload_gallery":
            _upload_gallery_images(request)
            return redirect("site-home")
        if request.POST.get("action") == "delete_gallery_image":
            _delete_gallery_image(request, request.POST.get("image_id", ""))
            return redirect("site-home")
        # M1: лого бизнеса (multipart) — в шапку витрины.
        if request.POST.get("action") == "upload_logo":
            _save_logo(request)
            return redirect("site-home")
        if request.POST.get("action") == "delete_logo":
            _delete_logo(request)
            return redirect("site-home")
        # M2: слайды баннера (heroes[]) — создать/обновить/удалить/переставить (multipart).
        if request.POST.get("action") == "save_hero_slide":
            _save_hero_slide(request)
            return redirect("site-home")
        if request.POST.get("action") == "delete_hero_slide":
            _delete_hero_slide(request)
            return redirect("site-home")
        if request.POST.get("action") == "move_hero_slide":
            _move_hero_slide(request)
            return redirect("site-home")
        # M3: обложка раздела (archetypes[key].hero_image) — загрузка прямо из билдера.
        if request.POST.get("action") == "upload_cover_hero":
            _upload_cover_hero(request, request.POST.get("archetype", ""))
            return redirect("site-home")
        # D.2b: добавить пустой C-блок (text/image/…) — появится в списке для правки.
        # E.3: необязательный `add_after` (ключ фикс-секции или id C-блока) — вставить
        # новый блок сразу ПОСЛЕ него (инсертер «+» на канвасе); иначе — в конец.
        if request.POST.get("action") == "add_block":
            btype = request.POST.get("block_type", "")
            if btype in siteconfig.REPEATABLE_BLOCKS:
                cfg = siteconfig.normalize(request.tenant.site_config)
                # UC6-5: новый блок — сразу с демо-данными (живой пример вместо пустоты).
                new_block = {
                    "key": btype,
                    "enabled": True,
                    "data": dict(siteconfig.CBLOCK_DEMO_DATA.get(btype, {})),
                }
                _insert_after_section(cfg["sections"], new_block, request.POST.get("add_after"))
                request.tenant.site_config = siteconfig.normalize(cfg)
                request.tenant.save(update_fields=["site_config", "updated_at"])
                messages.success(request, _("Block added."))
            return redirect("site-home")
        # SE-4a: блок-шаблоны (многоразовые C-блоки). action кодирует id через ":" —
        # save_block_template:<cb_id> (сохранить текущий C-блок как шаблон, данные из
        # POST → ловим несохранённые правки), use_block_template:<tpl_id> (вставить
        # копию в конец), delete_block_template:<tpl_id>.
        action = request.POST.get("action", "")
        if action.startswith(
            ("save_block_template:", "use_block_template:", "delete_block_template:")
        ):
            import copy
            import uuid

            verb, _sep, ident = action.partition(":")
            cfg = siteconfig.normalize(request.tenant.site_config)
            tpls = dict(cfg.get("block_templates") or {})
            if verb == "save_block_template":
                btype = request.POST.get(f"cb_type_{ident}", "")
                if btype in siteconfig.REPEATABLE_BLOCKS:
                    label = (request.POST.get(f"tpl_label_{ident}") or "").strip()
                    tpls[uuid.uuid4().hex[:12]] = {
                        "key": btype,
                        "label": label or btype,
                        "data": _read_cblock_data(request.POST, ident, btype),
                    }
                    messages.success(request, _("Block saved as template."))
            elif verb == "use_block_template" and ident in tpls:
                tpl = tpls[ident]
                # SE-4c: опц. insert_after (инсертер «+» на канвасе) → вставка в позицию;
                # иначе в конец (back-compat с кнопкой «Insert» в библиотеке).
                _insert_after_section(
                    cfg["sections"],
                    {"key": tpl["key"], "enabled": True, "data": copy.deepcopy(tpl["data"])},
                    request.POST.get("insert_after"),
                )
                messages.success(request, _("Template inserted."))
            elif verb == "delete_block_template" and ident in tpls:
                tpls.pop(ident)
                messages.success(request, _("Template removed."))
            cfg["block_templates"] = tpls
            request.tenant.site_config = siteconfig.normalize(cfg)
            request.tenant.save(update_fields=["site_config", "updated_at"])
            return redirect("site-home")
        # SE-4b: применить/удалить шаблон страницы. use_page_template:<id> ЗАМЕНЯЕТ весь
        # набор секций снимком (это шаблон СТРАНИЦЫ, не вставка); delete_page_template:<id>
        # убирает из библиотеки. Сохранение шаблона — в основном потоке (ниже), чтобы
        # снимок ловил несохранённые правки порядка/видимости из формы.
        if action.startswith(("use_page_template:", "delete_page_template:")):
            import copy

            verb, _sep, ident = action.partition(":")
            cfg = siteconfig.normalize(request.tenant.site_config)
            ptpls = dict(cfg.get("page_templates") or {})
            if verb == "use_page_template" and ident in ptpls:
                cfg["sections"] = copy.deepcopy(ptpls[ident]["sections"])
                messages.success(request, _("Page template applied."))
            elif verb == "delete_page_template" and ident in ptpls:
                ptpls.pop(ident)
                cfg["page_templates"] = ptpls
                messages.success(request, _("Page template removed."))
            request.tenant.site_config = siteconfig.normalize(cfg)
            request.tenant.save(update_fields=["site_config", "updated_at"])
            return redirect("site-home")
        # A3: сохранить ИМЕНОВАННУЮ версию текущего конфига (снимок в начало истории;
        # публикация не меняется — безопасная точка отката перед экспериментами).
        if action == "save_version":
            cfg = siteconfig.normalize(request.tenant.site_config)
            label = (request.POST.get("version_label") or "").strip()[:60]
            snap = {k: v for k, v in cfg.items() if k not in siteconfig._SNAPSHOT_EXCLUDE}
            entry = {"ts": timezone.now().isoformat(), "config": snap}
            if label:
                entry["label"] = label
            cfg["history"] = siteconfig.normalize_history([entry] + list(cfg.get("history") or []))
            request.tenant.site_config = siteconfig.normalize(cfg)
            request.tenant.save(update_fields=["site_config", "updated_at"])
            messages.success(request, _("Version saved."))
            return redirect("site-home")
        # A3: переименовать снимок истории (label_version:<idx> + version_label).
        if action.startswith("label_version:"):
            _verb, _sep, ident = action.partition(":")
            cfg = siteconfig.normalize(request.tenant.site_config)
            history = list(cfg.get("history") or [])
            try:
                idx = int(ident)
            except (TypeError, ValueError):
                idx = -1
            if 0 <= idx < len(history):
                label = (request.POST.get("version_label") or "").strip()[:60]
                if label:
                    history[idx]["label"] = label
                else:
                    history[idx].pop("label", None)
                cfg["history"] = siteconfig.normalize_history(history)
                request.tenant.site_config = siteconfig.normalize(cfg)
                request.tenant.save(update_fields=["site_config", "updated_at"])
                messages.success(request, _("Version renamed."))
            return redirect("site-home")
        # SE-5b: откат на версию из истории. restore_version:<idx> — заменить текущий
        # конфиг снимком, а ТЕКУЩИЙ положить в начало истории (сам откат undoable).
        if action.startswith("restore_version:"):
            _verb, _sep, ident = action.partition(":")
            cfg = siteconfig.normalize(request.tenant.site_config)
            history = cfg.get("history") or []
            try:
                idx = int(ident)
            except (TypeError, ValueError):
                idx = -1
            if 0 <= idx < len(history):
                target = dict(history[idx]["config"])
                current_snap = {k: v for k, v in cfg.items() if k != "history"}
                target["history"] = [
                    {"ts": timezone.now().isoformat(), "config": current_snap}
                ] + history
                request.tenant.site_config = siteconfig.normalize(target)
                request.tenant.save(update_fields=["site_config", "updated_at"])
                messages.success(request, _("Version restored."))
            return redirect("site-home")
        # SE-2c-1: быстрое создание категории прямо в редакторе (мини-форма «+ Kategorie»,
        # по образцу add_block). Создаёт живую Category через CategoryForm (валидация/slug/
        # parent переиспользуются); категория сразу видна чипом на канве каталога. Категории
        # живут в БД, не в site_config, поэтому редактор просто редиректит на site-home.
        if request.POST.get("action") == "add_category":
            if request.tenant.is_module_active("catalog"):
                from apps.catalog.forms import CategoryForm

                # Мини-форма шлёт только name_de (+ опц. parent); sort_order в
                # CategoryForm обязателен — подставляем дефолт, не трогая общую форму.
                post = request.POST.copy()
                post.setdefault("sort_order", "0")
                form = CategoryForm(post)
                if form.is_valid():
                    category = form.save(commit=False)
                    category.is_active = True  # быстрая категория сразу видима на витрине
                    category.save()
                    messages.success(request, _("Category added."))
                else:
                    first = next(iter(form.errors.values()))[0]
                    messages.error(request, first)
            return redirect("site-home")
        from apps.core import archetypes

        config = siteconfig.normalize(request.tenant.site_config)
        # H0: секции скрытых (нерелевантных архетипу) типов в форму не выводятся →
        # их полей в POST нет. Чтобы не затереть (enabled/layout/visual), сохраняем их
        # существующую запись как есть, на прежнем месте. Lookup по ключу фикс-секции.
        existing_fixed = {
            s["key"]: (idx, s)
            for idx, s in enumerate(config["sections"])
            if isinstance(s, dict)
            and s.get("key") in {k for k, _l, _d in siteconfig.SECTIONS}
            and "id" not in s
        }
        # Фикс-секции (порядок/видимость/раскладка) — как раньше, но как (order, entry)
        # пары, чтобы слить с C-блоками в один отсортированный список.
        items = []
        for key, _label, _default in siteconfig.SECTIONS:
            # H0: скрытая из редактора секция (чужой неактивный архетип) → carry-forward.
            if not archetypes.section_visible_for(request.tenant, key) and key in existing_fixed:
                _idx, _entry = existing_fixed[key]
                items.append((_idx, _entry))
                continue
            try:
                order = int(request.POST.get(f"order_{key}", "999"))
            except (TypeError, ValueError):
                order = 999
            entry = {"key": key, "enabled": request.POST.get(f"enabled_{key}") == "on"}
            # SE-3c-mid: скрыть секцию на устройствах (mobile/tablet/desktop).
            entry["hidden_on"] = [
                d
                for d in ("mobile", "tablet", "desktop")
                if request.POST.get(f"hide_{d}_{key}") == "on"
            ]
            # SE-3e: ширина контейнера секции (contained/full). normalize валидирует.
            entry["width"] = request.POST.get(f"width_{key}", "contained")
            # H1.5: пер-секционный шрифт ("" = наследовать). normalize валидирует по FONTS.
            entry["font"] = request.POST.get(f"font_{key}", "")
            if key in siteconfig.GRID_SECTION_DEFAULTS:
                preset = request.POST.get(f"layout_preset_{key}", "")
                lay = {"preset": preset} if preset in siteconfig.LAYOUT_PRESETS else {}
                # SE-3c: пер-девайс число колонок (телефон/планшет/десктоп). Пустые →
                # normalize_layout возьмёт из пресета/авто (без регрессии).
                for fld in ("cols", "mobile", "tablet"):
                    v = request.POST.get(f"{fld}_{key}", "")
                    if v != "":
                        lay[fld] = v
                if lay:
                    entry["layout"] = lay
            if key in siteconfig.GRID_SECTION_LIMITS:
                entry["limit"] = request.POST.get(f"limit_{key}", "")
            if key == "products":
                entry["source"] = request.POST.get("source_products", "")
            if key in siteconfig.SECTION_VIEWALL_KEYS:
                entry["show_all"] = request.POST.get(f"show_all_{key}") == "on"
            # SE-3d: визуальные параметры блока. Источник истины радиуса —
            # slider `visual_radius_px_{key}` (Эксперт; JS держит его в синхроне с
            # basic-чекбоксом). Фолбэк: basic-тоггл `visual_radius_{key}` → 16px.
            raw_px = request.POST.get(f"visual_radius_px_{key}")
            if raw_px not in (None, ""):
                try:
                    radius = max(0, min(24, int(raw_px)))
                except (TypeError, ValueError):
                    radius = 0
            else:
                radius = 16 if request.POST.get(f"visual_radius_{key}") == "on" else 0
            entry["visual"] = {
                "radius": radius,
                "shadow": request.POST.get(f"visual_shadow_{key}") == "on",
                # SE-3d: фон/отступы карточек секции (normalize/_clean_visual санитайзит).
                # Фон применяется лишь при включённом тоггле (color-input всегда шлёт значение).
                "background": (
                    request.POST.get(f"visual_bg_{key}", "")
                    if request.POST.get(f"visual_bg_on_{key}") == "on"
                    else ""
                ),
                "padding": request.POST.get(f"visual_padding_{key}", ""),
            }
            items.append((order, entry))
        # D.2b: C-блоки — читаем посланные строки (id+тип+данные), удалённые пропускаем.
        for bid in request.POST.getlist("cb_id"):
            btype = request.POST.get(f"cb_type_{bid}", "")
            if btype not in siteconfig.REPEATABLE_BLOCKS:
                continue
            if request.POST.get(f"delete_cb_{bid}") == "on":
                continue  # удалён владельцем
            try:
                order = int(request.POST.get(f"order_cb_{bid}", "999"))
            except (TypeError, ValueError):
                order = 999
            items.append(
                (
                    order,
                    {
                        "key": btype,
                        "id": bid,
                        "enabled": request.POST.get(f"enabled_cb_{bid}") == "on",
                        "data": _read_cblock_data(request.POST, bid, btype),
                        # UC6-3: ширина/положение блока (normalize валидирует;
                        # раньше width C-блока терялся при Save — жил только в черновике).
                        "width": request.POST.get(f"width_cb_{bid}", "contained"),
                        "pos": request.POST.get(f"pos_cb_{bid}", ""),
                        # UC6-3a: принудительный перенос ряда узких блоков.
                        "newline": request.POST.get(f"newline_cb_{bid}") == "on",
                    },
                )
            )
        items.sort(key=lambda row: row[0])
        config["sections"] = [entry for _o, entry in items]
        # SE-4b: сохранить текущую компоновку как шаблон страницы. Снимок берём из только
        # что собранного config["sections"] → ловит несохранённые правки порядка/видимости
        # (как save_block_template ловит правки C-блока). normalize() ниже санитизирует.
        if request.POST.get("action") == "save_page_template":
            import copy
            import uuid

            ptpls = dict(config.get("page_templates") or {})
            label = (request.POST.get("page_tpl_label") or "").strip()
            ptpls[uuid.uuid4().hex[:12]] = {
                "label": label or _("Page template"),
                "sections": copy.deepcopy(config["sections"]),
            }
            config["page_templates"] = ptpls
            messages.success(request, _("Page saved as template."))
        # Пер-архетипные оверрайды тизеров (заголовок/описание/видимость).
        arch = dict(config.get("archetypes") or {})
        for spec in storefront.teaser_specs(request.tenant):
            key = spec["key"]
            arch[key] = {
                "label": request.POST.get(f"arch_label_{key}", "").strip(),
                "blurb": request.POST.get(f"arch_blurb_{key}", "").strip(),
                "hidden": request.POST.get(f"arch_visible_{key}") != "on",
            }
        config["archetypes"] = arch
        # M20U-7: кастомные заголовки секций главной (normalize чистит/обрезает).
        titles = {}
        for tkey in siteconfig.SECTION_TITLE_KEYS:
            tval = request.POST.get(f"title_{tkey}", "").strip()
            if tval:
                titles[tkey] = tval
        config["section_titles"] = titles
        # (per-page раскладки номеров/событий — на странице «Pages», pages_view;
        #  normalize сохраняет их при записи главной без изменений.)
        # SE-2a-2: раскладка каталога правится и на канве (per-page инспектор) —
        # сохраняем, если прислан валидный пресет (иначе не трогаем существующую).
        for fld, cfg_key in (
            ("catalog_preset", "catalog_layout"),
            ("events_preset", "events_index_layout"),
            ("stay_preset", "stay_index_layout"),
            ("service_preset", "service_index_layout"),
        ):
            preset = request.POST.get(fld, "")
            if preset in siteconfig.LAYOUT_PRESETS:
                config[cfg_key] = {"preset": preset}
            elif cfg_key == "service_index_layout" and fld in request.POST and not preset:
                # UB1-1: «Standard» (пустой выбор) удаляет ключ → легаси-грид услуг
                # (у соседей пустого выбора нет — их ключ всегда материализован).
                config.pop(cfg_key, None)
        # Категория: фильтры/сортировка/подкатегории — presence-guard (cf_present шлётся
        # панелью каталога; одним блоком, чтобы частичный POST не сбрасывал настройки).
        if request.tenant.is_module_active("catalog") and request.POST.get("cf_present"):
            config["catalog_show_filters"] = request.POST.get("catalog_show_filters") == "on"
            config["catalog_subcats_first"] = request.POST.get("catalog_subcats_first") == "on"
            _cs = request.POST.get("catalog_sort", "")
            if _cs in siteconfig.CATALOG_SORT_KEYS:
                config["catalog_sort"] = _cs
        # Корзина: показывать ли кросс-селл — presence-guard (cart_present шлётся панелью корзины).
        if request.tenant.is_module_active("catalog") and request.POST.get("cart_present"):
            config["cart_show_upsell"] = request.POST.get("cart_show_upsell") == "on"
        # SE-2b-2: порядок/видимость тематических секций детальной события правятся
        # и на канве (on-canvas инспектор) — раньше только на вкладке «Pages».
        # Presence-guard: пишем, только если инспектор реально прислан (есть ed_order_*),
        # иначе частичный POST без полей не должен скрыть все секции.
        if request.tenant.is_module_active("events") and any(
            k.startswith("ed_order_") for k in request.POST
        ):
            ed_rows = []
            for key in siteconfig.EVENT_DETAIL_SECTION_KEYS:
                try:
                    order = int(request.POST.get(f"ed_order_{key}", "999"))
                except (TypeError, ValueError):
                    order = 999
                ed_rows.append((order, key, request.POST.get(f"ed_visible_{key}") == "on"))
            ed_rows.sort(key=lambda r: r[0])
            config["event_detail"] = {
                "order": [k for _o, k, _v in ed_rows],
                "hidden": [k for _o, k, v in ed_rows if not v],
            }
        # Видимость опц. секций детальной товара (group=catalog_detail). Presence-guard:
        # пишем только если инспектор прислан (есть pd_present), иначе не трогаем.
        if request.tenant.is_module_active("catalog") and request.POST.get("pd_present"):
            config["product_detail"] = {
                "hidden": [
                    k
                    for k in siteconfig.PRODUCT_DETAIL_SECTION_KEYS
                    if request.POST.get(f"pd_visible_{k}") != "on"
                ]
            }
        # UA4-1 slice C: видимость секций детальной услуги/номера (hide-only, presence-guard).
        if request.tenant.is_module_active("booking") and request.POST.get("sd_present"):
            config["service_detail"] = {
                "hidden": [
                    k
                    for k in detail_sections.section_keys("booking")
                    if request.POST.get(f"sd_visible_{k}") != "on"
                ]
            }
        if request.tenant.is_module_active("stays") and request.POST.get("std_present"):
            config["stay_detail"] = {
                "hidden": [
                    k
                    for k in detail_sections.section_keys("stays")
                    if request.POST.get(f"std_visible_{k}") != "on"
                ]
            }
        # SE-3b: глобальная типографика (начертание заголовков + межстрочный интервал).
        # normalize_typography валидирует/клампит; пустые/0 = дефолт без регрессии.
        config["typography"] = {
            "weight_head": request.POST.get("typo_weight_head", ""),
            "line_height": request.POST.get("typo_line_height", ""),
        }
        # SE-2d: глобальный стиль карточек («весь сайт»). normalize_site_defaults
        # клампит radius (0..24) и приводит мусор к 0 → дефолт = текущее поведение.
        config["site_defaults"] = {
            "card_radius": request.POST.get("sd_card_radius", ""),
            "card_shadow": request.POST.get("sd_card_shadow") == "on",
            # SE-3d: глобальные фон/отступы карточек («весь сайт»). Фон применяется
            # лишь при включённом тоггле (color-input всегда шлёт значение).
            "card_bg": (
                request.POST.get("sd_card_bg", "")
                if request.POST.get("sd_card_bg_on") == "on"
                else ""
            ),
            "card_padding": request.POST.get("sd_card_padding", ""),
        }
        # S4: стартовая страница витрины (общая главная или один архетип).
        config["storefront_root"] = request.POST.get("storefront_root", "home").strip() or "home"
        # SE-7c: область «Меню» — стиль шапки + sticky. Presence-guard (правим лишь когда
        # инспектор Меню прислан, т.е. есть nav_style), иначе config["nav"] остаётся как был
        # (пункты меню — в полном билдере /dashboard/site/menu/, их не трогаем).
        if "nav_style" in request.POST:
            nav = dict(config.get("nav") or {})
            ns = request.POST.get("nav_style")
            nav["style"] = ns if ns in siteconfig.NAV_STYLES else nav.get("style", "classic")
            nav["sticky"] = request.POST.get("nav_sticky") == "on"
            config["nav"] = nav
        # SE-7d: область «Баннер» — заголовок/текст hero (presence-guard, чтобы прочие
        # сохранения не затирали; инпуты пред-заполнены из config → round-trip).
        if "hero_title" in request.POST:
            config["hero_title"] = request.POST.get("hero_title", "").strip()
            config["hero_text"] = request.POST.get("hero_text", "").strip()
        # M20f: дизайн — шрифт + стиль hero (site_config); акцент — поле Tenant.
        config["font"] = request.POST.get("font", config.get("font", "system"))
        config["hero_style"] = "accent" if request.POST.get("hero_accent") == "on" else "plain"
        # M20d: контент-секции (CTA/FAQ/Testimonials/Process/Team/Trust) — тот же парсер.
        config.update(siteconfig.parse_content_sections(request.POST.get))
        update_fields = ["site_config", "updated_at"]
        accent = (request.POST.get("accent") or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) and accent != request.tenant.primary_color:
            request.tenant.primary_color = accent
            update_fields.insert(1, "primary_color")
        # SE-5b: снимок текущей опубликованной версии в историю перед публикацией новой
        # (точки отката = явные «Сохранить»; инкрементальные действия историю не пишут).
        config["history"] = siteconfig.push_history(
            request.tenant.site_config, config.get("history"), timezone.now().isoformat()
        )
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=update_fields)
        messages.success(request, "Gespeichert.")
        return redirect("site-home")

    from apps.core import archetypes, modules

    # SE-5b-2: восстановить несохранённый черновик из БД (после закрытия браузера/смены
    # устройства — сессия пуста, но `_draft` пережил). Форма открывается на черновике,
    # превью синхронизируем через сессию. Если правок не было — обычный нормализованный
    # опубликованный конфиг (без регрессии).
    raw_cfg = request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
    db_draft = raw_cfg.get("_draft")
    if isinstance(db_draft, dict):
        config = siteconfig.normalize(db_draft)
        if hasattr(request, "session") and not request.session.get("site_preview_draft"):
            request.session["site_preview_draft"] = siteconfig.normalize(db_draft)
        messages.info(request, _("Restored your unpublished draft."))
    else:
        config = siteconfig.normalize(request.tenant.site_config)
    labels = {key: label for key, label, _default in siteconfig.SECTIONS}
    root_options = [{"key": "home", "label": _("Combined homepage")}] + [
        {"key": a.key, "label": a.label} for a in modules.storefront_archetypes(request.tenant)
    ]
    # SE-2a-1: страницы для переключателя превью в редакторе (главная + лендинги
    # активных архетипов). URL резолвим тут (tenant urlconf); недоступный — пропускаем.
    from django.urls import NoReverseMatch, reverse

    # Part D: каждый пункт несёт «группу вывода» (home / лендинг архетипа / деталь /
    # текстовая) — билдер по ней показывает в панели ТОЛЬКО блоки этой страницы.
    preview_pages = [{"label": _("Homepage"), "url": "/", "group": "home"}]
    for a in modules.storefront_archetypes(request.tenant):
        try:
            preview_pages.append({"label": a.label, "url": reverse(a.url_name), "group": a.key})
        except NoReverseMatch:
            continue
    # H0/H1: страницы-ДЕТАЛИ активных архетипов (товар/номер/событие — первый пример) —
    # чтобы деталь можно было открыть на канве и править инлайн (H1.2) / порядок секций.
    preview_pages.extend(archetypes.example_detail_pages(request.tenant))
    # Корзина (Click&Collect) — отдельная группа страницы: владелец открывает её на канве,
    # панель билдера показывает настройки корзины (а не блоки главной). Только при каталоге.
    if request.tenant.is_module_active("catalog"):
        try:
            preview_pages.append(
                {"label": _("Cart"), "url": reverse("storefront-cart"), "group": "cart"}
            )
        except NoReverseMatch:
            pass
    # H1 «простые страницы»: универсальные инфо/правовые страницы тоже доступны в
    # переключателе превью — владелец видит их вид и (для «О нас») правит about-тексты.
    for url_name, label in (
        ("storefront-about", _("About page")),
        ("storefront-impressum", _("Impressum")),
        ("storefront-privacy", _("Privacy")),
        ("storefront-withdrawal", _("Withdrawal")),
    ):
        try:
            preview_pages.append({"label": label, "url": reverse(url_name), "group": "text"})
        except NoReverseMatch:
            continue
    # Фикс-секции и C-блоки идут в одном `config["sections"]`; index = глобальный
    # порядок (его пишем в order_*-поля, чтобы при сохранении сохранить чередование).
    sections = []
    cblocks = []
    for index, s in enumerate(config["sections"], start=1):
        if s["key"] in siteconfig.REPEATABLE_BLOCKS:
            cblocks.append(
                {
                    "id": s["id"],
                    "type": s["key"],
                    "enabled": s["enabled"],
                    "data": s["data"],
                    "order": index,
                    # UC6-3: текущие ширина/положение — для селектов формы блока.
                    "width": s.get("width", "contained"),
                    "pos": s.get("pos", ""),
                    "newline": bool(s.get("newline")),  # UC6-3a
                }
            )
            continue
        if s["key"] not in labels:
            continue
        # H0 (архетипы как сущности): секции чужих (неактивных) архетипов скрываем из
        # списка редактора — пекарня не видит Stay/Events/Services/Handwerker. Их рендер
        # на витрине и так гейтится модулем; конфиг сохраняется POST-гардом (carry-forward).
        if not archetypes.section_visible_for(request.tenant, s["key"]):
            continue
        sections.append(
            {
                "key": s["key"],
                "label": labels[s["key"]],
                "enabled": s["enabled"],
                "order": index,
                "icon": siteconfig.SECTION_ICONS.get(s["key"], "🧩"),  # SE-9c: иконка рейла
                "is_grid": s["key"] in siteconfig.GRID_SECTION_DEFAULTS,
                "layout_preset": (s.get("layout") or {}).get("preset", ""),
                # SE-3c: пер-девайс число колонок (0 для tablet = «авто»).
                "layout_cols": (s.get("layout") or {}).get("cols", ""),
                "layout_mobile": (s.get("layout") or {}).get("mobile", ""),
                "layout_tablet": (s.get("layout") or {}).get("tablet", 0),
                "has_limit": s["key"] in siteconfig.GRID_SECTION_LIMITS,
                "limit": s.get("limit", ""),
                "has_title": s["key"] in siteconfig.SECTION_TITLE_KEYS,
                "title": (config.get("section_titles") or {}).get(s["key"], ""),
                "has_source": s["key"] == "products",
                "source": s.get("source", ""),
                "has_viewall": s["key"] in siteconfig.SECTION_VIEWALL_KEYS,
                "show_all": s.get("show_all", True),
                "visual_radius": bool(s.get("visual", {}).get("radius", 0) > 0),
                "visual_radius_px": int(s.get("visual", {}).get("radius", 0)),
                "visual_shadow": bool(s.get("visual", {}).get("shadow", False)),
                "visual_bg": s.get("visual", {}).get("background", ""),
                "visual_padding": int(s.get("visual", {}).get("padding", 0)),
                # SE-3c-mid: на каких устройствах секция скрыта.
                "hidden_on": s.get("hidden_on", []),
                # SE-3e: ширина контейнера секции (contained/full).
                "width": s.get("width", "contained"),
                # H1.5: пер-секционный шрифт (или "" = наследовать глобальный).
                "font": s.get("font", ""),
            }
        )
    preset_options = [
        ("list", _("List")),
        ("cols2", _("2 per row")),
        ("cols3", _("3 per row")),
        ("cols4", _("4 per row")),
        ("gallery", _("Gallery")),
    ]
    source_options = [
        ("featured_first", _("Featured first")),
        ("newest", _("Newest")),
        ("featured_only", _("Featured only")),
    ]
    archetypes_enabled = any(s["key"] == "archetypes" and s["enabled"] for s in config["sections"])
    # SE-2b-2 → UC1-3: секции детальных страниц для on-canvas инспектора — generic
    # `siteconfig.page_inspector` из единого реестра (event — orderable с order;
    # product/service/stay — hide-only), вместо четырёх ручных сборок.
    event_sections = siteconfig.page_inspector(config, "event_detail")
    product_sections = siteconfig.page_inspector(config, "product_detail")
    service_sections = siteconfig.page_inspector(config, "service_detail")
    stay_sections = siteconfig.page_inspector(config, "stay_detail")
    # SE-2c-1: живые категории каталога — для parent-select мини-формы «+ Kategorie».
    catalog_categories = []
    if request.tenant.is_module_active("catalog"):
        from apps.catalog.models import Category

        catalog_categories = list(Category.objects.filter(is_active=True))
    return render(
        request,
        "tenant/site_home.html",
        {
            "nav": "site",
            "sections": sections,
            "event_sections": event_sections,
            "product_sections": product_sections,
            "service_sections": service_sections,
            "stay_sections": stay_sections,
            "catalog_categories": catalog_categories,
            # SE-7c: область «Меню» — стиль шапки (classic/centered/minimal) + sticky
            # (пункты меню — в полном билдере /dashboard/site/menu/).
            "nav_style": config["nav"]["style"],
            "nav_sticky": config["nav"]["sticky"],
            "nav_styles": siteconfig.NAV_STYLES,
            # SE-7d: область «Баннер» — заголовок/текст hero (картинка — на канве/в галерее).
            "hero_title": config["hero_title"],
            "hero_text": config["hero_text"],
            # M3: обложки разделов (archetypes[key].hero_image) — загрузка из билдера.
            "cover_specs": storefront.cover_specs(request.tenant),
            # D.2b: C-блоки (кубики) + типы для кнопок «добавить».
            "cblocks": cblocks,
            # SE-4a: библиотека сохранённых блок-шаблонов (id/тип/имя) для вставки.
            "block_templates": [
                {"id": tid, "key": t["key"], "label": t["label"]}
                for tid, t in config["block_templates"].items()
            ],
            # SE-4b: библиотека шаблонов страниц (применить/удалить).
            "page_templates": [
                {"id": tid, "label": t["label"], "count": len(t["sections"])}
                for tid, t in config["page_templates"].items()
            ],
            # SE-5b: история версий (откат публикации).
            "history": [
                {"idx": i, "ts": h["ts"], "label": h.get("label", "")}
                for i, h in enumerate(config["history"])
            ],
            # UE1: селектор промо для промо-блока (активные+запланированные).
            "promos_for_blocks": _promos_for_blocks(request),
            # UC6-5: карточки библиотеки блоков — иконка + подсказка (вставка
            # даёт демо-данные из siteconfig.CBLOCK_DEMO_DATA).
            "block_types": [
                {
                    "value": "text",
                    "label": _("Text"),
                    "icon": "📝",
                    "hint": _("Heading + paragraph"),
                },
                {
                    "value": "image",
                    "label": _("Image"),
                    "icon": "🖼️",
                    "hint": _("Photo with caption"),
                },
                {
                    "value": "image_text",
                    "label": _("Image + text"),
                    "icon": "🏞️",
                    "hint": _("Photo beside text"),
                },
                {"value": "button", "label": _("Button"), "icon": "🔘", "hint": _("Link button")},
                {
                    "value": "spacer",
                    "label": _("Spacer"),
                    "icon": "↕️",
                    "hint": _("Vertical spacing"),
                },
                {
                    "value": "promo",
                    "label": _("Promotion"),
                    "icon": "🏷️",
                    "hint": _("Live promotion"),
                },  # UE1
            ],
            "preset_options": preset_options,
            "source_options": source_options,
            "archetype_specs": storefront.teaser_specs(request.tenant),
            "archetypes_enabled": archetypes_enabled,
            "root_options": root_options,
            "preview_pages": preview_pages,
            # UC6-1b: карта «путь → группа» для авто-скоупа панели по фактической
            # странице кадра (селектор страниц из тулбара убран). JSON, не escapejs —
            # тот кодирует дефисы (-) и ломает literal-сравнение путей.
            "preview_page_groups_json": _json.dumps(
                {p["url"]: p.get("group") or "home" for p in preview_pages}
            ),
            # T-6.1: deep-link — канва стартует со страницы, где нажали «Edit design».
            "preview_start_path": _safe_preview_page(request.GET.get("page")),
            # SE-2a-2/SE-2b-1: per-page инспектор раскладки лендингов (по активным модулям).
            "has_catalog": request.tenant.is_module_active("catalog"),
            "catalog_preset": (config.get("catalog_layout") or {}).get("preset", ""),
            "catalog_show_filters": config.get("catalog_show_filters", True),
            "catalog_sort": config.get("catalog_sort", "newest"),
            "catalog_subcats_first": config.get("catalog_subcats_first", True),
            "cart_show_upsell": config.get("cart_show_upsell", True),
            "has_events": request.tenant.is_module_active("events"),
            "events_preset": (config.get("events_index_layout") or {}).get("preset", ""),
            "has_stays": request.tenant.is_module_active("stays"),
            "stay_preset": (config.get("stay_index_layout") or {}).get("preset", ""),
            "has_booking": request.tenant.is_module_active("booking"),  # UA4-1 slice C
            # UB1-1: пресет листинга услуг; "" = ключ не задан (легаси-грид «Standard»).
            "service_preset": (config.get("service_index_layout") or {}).get("preset", ""),
            "storefront_root": config.get("storefront_root", "home"),
            # M20f: дизайн вживую — текущие значения + варианты шрифта.
            "font": config.get("font", "system"),
            "font_options": [
                ("system", _("System")),
                ("serif", _("Serif")),
                ("rounded", _("Rounded")),
            ],
            "hero_accent": config.get("hero_style") == "accent",
            "accent": request.tenant.primary_color or "#4f46e5",
            # SE-3b: типографика — текущие значения + варианты для селекторов.
            "typo_weight_head": config["typography"]["weight_head"],
            "typo_line_height": config["typography"]["line_height"],
            "typo_weight_options": [
                (300, _("Light")),
                (400, _("Normal")),
                (500, _("Medium")),
                (600, _("Semibold")),
                (700, _("Bold")),
                (800, _("Extra bold")),
            ],
            "typo_line_height_options": [1.4, 1.5, 1.6, 1.8, 2.0],
            # SE-3a: микрошаблоны «Quick styles» для секций-сеток (распаковка на фронте).
            "micro_templates": siteconfig.micro_templates(),
            # SE-2d/SE-3d: текущий глобальный стиль карточек («весь сайт») для контролов.
            "card_radius": config["site_defaults"]["card_radius"],
            "card_shadow": config["site_defaults"]["card_shadow"],
            "card_bg": config["site_defaults"]["card_bg"],
            "card_padding": config["site_defaults"]["card_padding"],
            # M20d: контент-секции — те же поля/партиал, что на «Site».
            "config": config,
            "faq_text": siteconfig.pairs_to_text(config["faq"], "q", "a"),
            "testimonials_text": siteconfig.pairs_to_text(config["testimonials"], "name", "text"),
            "process_text": siteconfig.pairs_to_text(config["process"], "title", "text"),
            "team_text": "\n".join(
                f"{m['name']} | {m['role']}".rstrip(" |") for m in config["team"]
            ),
            "trust_marks_text": "\n".join(config["trust"]["marks"]),
            "usp_text": siteconfig.usp_to_text(config["usp_bar"]),
        },
    )


def _cover_archetype_keys(tenant) -> set:
    from apps.tenants import storefront

    return {s["key"] for s in storefront.cover_specs(tenant)}


def _upload_cover_gallery(request, key: str) -> None:
    """S3b: загрузить фото в галерею раздела key (site_config['archetypes'][key])."""
    from django.core.exceptions import ValidationError

    from apps.catalog.images import save_product_image
    from apps.tenants import siteconfig

    if key not in _cover_archetype_keys(request.tenant):
        return
    files = request.FILES.getlist("images")
    if not files:
        return
    cfg = siteconfig.normalize(request.tenant.site_config)
    arch = dict(cfg.get("archetypes") or {})
    cur = dict(arch.get(key) or {})
    gallery = list(cur.get("gallery") or [])
    for f in files:
        if len(gallery) >= siteconfig._MAX_COVER_GALLERY:
            messages.info(request, "Galerie-Limit erreicht.")
            break
        try:
            gallery.append(save_product_image(f, sort_order=len(gallery), folder="cover"))
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
    cur["gallery"] = gallery
    arch[key] = cur
    cfg["archetypes"] = arch
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, "Bilder hochgeladen.")


def _upload_cover_hero(request, key: str) -> None:
    """Загрузить ОДНО фото как баннер раздела (archetypes[key]['hero_image']) —
    альтернатива вводу URL вручную. Реюз save_product_image (валидация + storage)."""
    from django.core.exceptions import ValidationError

    from apps.catalog.images import save_product_image
    from apps.tenants import siteconfig

    if key not in _cover_archetype_keys(request.tenant):
        return
    upload = request.FILES.get("image")
    if not upload:
        return
    try:
        ref = save_product_image(upload, folder="cover")
    except ValidationError as exc:
        messages.error(request, f"{upload.name}: {'; '.join(exc.messages)}")
        return
    cfg = siteconfig.normalize(request.tenant.site_config)
    arch = dict(cfg.get("archetypes") or {})
    cur = dict(arch.get(key) or {})
    cur["hero_image"] = ref["url"]
    arch[key] = cur
    cfg["archetypes"] = arch
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, "Banner hochgeladen.")


def _delete_cover_image(request, key: str, image_id: str) -> None:
    from apps.catalog.images import delete_stored_image
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    arch = dict(cfg.get("archetypes") or {})
    cur = dict(arch.get(key) or {})
    gallery, removed = [], None
    for ref in cur.get("gallery") or []:
        if ref.get("id") == image_id:
            removed = ref
        else:
            gallery.append(ref)
    if removed is not None:
        delete_stored_image(removed)
        cur["gallery"] = gallery
        arch[key] = cur
        cfg["archetypes"] = arch
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Bild gelöscht.")


@login_required
def site_preview(request):
    """Live-предпросмотр витрины (Z): актуальный сайт в iframe + переключатель
    ширины (Desktop/Tablet/Mobile)."""
    return render(request, "tenant/site_preview.html", {"nav": "site"})


@login_required
@require_POST
def site_preview_draft(request):
    """V1 live-preview: принять черновик композиции главной (sections +
    оверрайды тизеров) из конструктора, смёржить в текущий site_config и
    положить в сессию. Витрина `/?preview=1` рендерит этот черновик — без записи
    в БД. Возврат 204."""
    import json

    from django.http import HttpResponse

    from apps.tenants import siteconfig

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        data = {}
    cfg = siteconfig.normalize(request.tenant.site_config)
    if isinstance(data.get("sections"), list):
        known = {k for k, _l, _d in siteconfig.SECTIONS}
        seen, rows = set(), []
        for item in data["sections"]:
            key = item.get("key") if isinstance(item, dict) else None
            if key in known and key not in seen:
                row = {"key": key, "enabled": bool(item.get("enabled"))}
                # M20U-7: пресет раскладки секции-сетки — отражаем в превью.
                lay = item.get("layout") if isinstance(item, dict) else None
                if key in siteconfig.GRID_SECTION_DEFAULTS and isinstance(lay, dict):
                    sub = {}
                    if lay.get("preset") in siteconfig.LAYOUT_PRESETS:
                        sub["preset"] = lay["preset"]
                    # SE-3c: пер-девайс число колонок → в превью (normalize клампит).
                    for fld in ("cols", "mobile", "tablet"):
                        if isinstance(lay.get(fld), (int, str)):
                            sub[fld] = lay[fld]
                    if sub:
                        row["layout"] = sub
                # M20U-7: лимит секции-превью → в черновик (normalize клампит).
                if key in siteconfig.GRID_SECTION_LIMITS and isinstance(
                    item.get("limit"), (int, str)
                ):
                    row["limit"] = item["limit"]
                # M20U-7: источник товаров → в черновик.
                if key == "products" and item.get("source") in siteconfig.PRODUCT_SOURCES:
                    row["source"] = item["source"]
                # M20U-7: видимость «View all» → в черновик.
                if key in siteconfig.SECTION_VIEWALL_KEYS and "show_all" in item:
                    row["show_all"] = bool(item["show_all"])
                # SE-3d: визуальные параметры секции (radius/shadow/bg/padding) →
                # в черновик для live-preview (normalize/_clean_visual санитайзит).
                if isinstance(item.get("visual"), dict):
                    row["visual"] = item["visual"]
                # SE-3c-mid: скрыть секцию на устройстве → в превью.
                if isinstance(item.get("hidden_on"), list):
                    row["hidden_on"] = item["hidden_on"]
                # SE-3e: ширина контейнера секции (contained/full) → в превью.
                if item.get("width") in ("contained", "full"):
                    row["width"] = item["width"]
                # H1.5: пер-секционный шрифт → в превью (normalize валидирует по FONTS).
                if "font" in item:
                    row["font"] = item["font"]
                rows.append(row)
                seen.add(key)
            elif key in siteconfig.REPEATABLE_BLOCKS:
                # D.2b: C-блок (text/image/…) — ключ-ТИП повторяется, различаем по id
                # (не дедупим по ключу!). Без этой ветки cblocks выпадали из черновика
                # → только что добавленный блок «не появлялся» в live-preview редактора.
                cbid = item.get("id") if isinstance(item, dict) else None
                if isinstance(cbid, str) and cbid and cbid not in seen:
                    cb = {"key": key, "id": cbid, "enabled": bool(item.get("enabled"))}
                    if isinstance(item.get("data"), dict):
                        cb["data"] = item["data"]
                    # UC6-3: + w23/w12 и положение (normalize валидирует по CBLOCK_WIDTHS).
                    if item.get("width") in siteconfig.CBLOCK_WIDTHS:
                        cb["width"] = item["width"]
                    if item.get("pos") in ("left", "right"):
                        cb["pos"] = item["pos"]
                    if item.get("newline"):
                        cb["newline"] = True  # UC6-3a
                    if "font" in item:
                        cb["font"] = item["font"]
                    if isinstance(item.get("hidden_on"), list):
                        cb["hidden_on"] = item["hidden_on"]
                    rows.append(cb)
                    seen.add(cbid)
        if rows:
            cfg["sections"] = rows
    if isinstance(data.get("archetypes"), dict):
        arch = dict(cfg.get("archetypes") or {})
        for key, ov in data["archetypes"].items():
            if isinstance(ov, dict):
                cur = dict(arch.get(key) or {})
                cur["label"] = str(ov.get("label", "")).strip()
                cur["blurb"] = str(ov.get("blurb", "")).strip()
                cur["hidden"] = bool(ov.get("hidden"))
                arch[key] = cur
        cfg["archetypes"] = arch
    # M20U-7: кастомные заголовки секций — в превью (normalize чистит ключи/длину).
    if isinstance(data.get("section_titles"), dict):
        cfg["section_titles"] = data["section_titles"]
    # H1: описания секций — в превью (normalize чистит ключи/длину).
    if isinstance(data.get("section_intros"), dict):
        cfg["section_intros"] = data["section_intros"]
    # UC2-1 (слайс B): все page-scoped ключи драфта (детальные секции, раскладки
    # лендингов, catalog-флаги/сорт, корзина) — одним generic-наложением по
    # реестру siteconfig.PAGE_CONFIG_KEYS; семантика веток 1:1 (см. план-док).
    siteconfig.apply_page_payload(cfg, data)
    # SE-2d: глобальный стиль карточек («весь сайт») — в превью (normalize_site_defaults
    # клампит). Применяется через context-процессор на любой странице под ?preview=1.
    if isinstance(data.get("site_defaults"), dict):
        cfg["site_defaults"] = data["site_defaults"]
    # SE-3b: глобальная типографика → в превью (normalize_typography клампит).
    if isinstance(data.get("typography"), dict):
        cfg["typography"] = data["typography"]
    # M20f: дизайн вживую — шрифт + стиль hero (поля site_config).
    if data.get("font") in siteconfig.FONTS:
        cfg["font"] = data["font"]
    if data.get("hero_style") in siteconfig.HERO_STYLES:
        cfg["hero_style"] = data["hero_style"]
    # SE-8b: стиль шапки (Меню) + заголовок/текст баннера → в превью (видно вживую).
    if data.get("nav_style") in siteconfig.NAV_STYLES:
        nav = dict(cfg.get("nav") or {})
        nav["style"] = data["nav_style"]
        nav["sticky"] = bool(data.get("nav_sticky"))
        cfg["nav"] = nav
    if isinstance(data.get("hero_title"), str):
        cfg["hero_title"] = data["hero_title"].strip()
    if isinstance(data.get("hero_text"), str):
        cfg["hero_text"] = data["hero_text"].strip()
    # M20d: контент-секции — отражаем в превью, только если присланы (иначе не трём).
    if any(k in data for k in siteconfig.CONTENT_FIELDS):
        cfg.update(siteconfig.parse_content_sections(data.get))
    draft = siteconfig.normalize(cfg)
    # Акцент — отдельное поле Tenant; кладём override в черновик как `_accent`
    # (валидный hex), читается context-процессором под ?preview=1.
    accent = data.get("accent")
    if isinstance(accent, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", accent.strip()):
        draft["_accent"] = accent.strip()
    request.session["site_preview_draft"] = draft
    # SE-5b-2: автосейв черновика в БД — переживает закрытие браузера/смену устройства
    # (сессия теряется, черновик — нет). Пишем через .update(): (1) не триггерит сигнал
    # сброса кэша витрины (опубликованный контент не менялся), (2) дешевле полного save().
    # `_draft`/`_draft_ts` — служебные: normalize() дропает их из выдачи, push_history —
    # из истории, так что опубликованная витрина и история остаются чистыми.
    from apps.tenants.models import Tenant

    published = request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
    new_cfg = {**published, "_draft": draft, "_draft_ts": timezone.now().isoformat()}
    Tenant.objects.filter(pk=request.tenant.pk).update(site_config=new_cfg)
    return HttpResponse(status=204)


SHARE_PREVIEW_TTL = 7 * 24 * 3600  # A4: срок жизни share-ссылки на черновик


@login_required
@require_POST
def share_preview_issue(request):
    """A4: выпуск share-ссылки на превью черновика (read-only, без логина).

    Снапшот фиксируется В МОМЕНТ выпуска (cache, TTL 7 дней) — дальнейшие
    правки владельца ссылку не меняют. Источник: черновик сессии → БД-`_draft`
    (автосейв) → нормализованный опубликованный конфиг. Просмотр —
    `shared_preview` (promotions.public_views): снапшот в сессию посетителя
    → `/?preview=1` (штатный draft-путь витрины).
    """
    import secrets

    from django.core.cache import cache
    from django.http import JsonResponse

    from apps.tenants import siteconfig

    draft = request.session.get("site_preview_draft")
    if not isinstance(draft, dict):
        raw = request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
        db_draft = raw.get("_draft")
        draft = db_draft if isinstance(db_draft, dict) else siteconfig.normalize(raw)
    token = secrets.token_urlsafe(32)
    cache.set(f"share_preview:{token}", draft, SHARE_PREVIEW_TTL)
    from django.urls import reverse

    return JsonResponse(
        {"url": request.build_absolute_uri(reverse("shared-preview", args=[token]))}
    )


@login_required
@require_POST
def site_cblock_photo_edit(request):
    """UC6-4: замена фото C-блока (image/image_text) прямо на канве превью.

    Файл — реюз save_product_image (валидация+storage); новый url пишем в data
    блока ПУБЛИКУЕМОГО конфига и зеркалим в сессионный черновик + БД-`_draft`
    (иначе следующий push() черновика откатит фото на старое из формы — форму
    синхронизирует JS по ответу {url})."""
    from django.core.exceptions import ValidationError
    from django.http import JsonResponse

    from apps.catalog.images import save_product_image
    from apps.tenants import siteconfig

    bid = (request.POST.get("pk") or "").strip()
    upload = request.FILES.get("image")
    if not bid or not upload:
        return JsonResponse({"error": "missing pk/image"}, status=400)
    try:
        ref = save_product_image(upload, folder="cblock")
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)

    def _patch(cfg_dict) -> bool:
        hit = False
        for s in cfg_dict.get("sections", []):
            if (
                isinstance(s, dict)
                and s.get("id") == bid
                and s.get("key") in ("image", "image_text")
            ):
                data = dict(s.get("data") or {})
                data["url"] = ref["url"]
                s["data"] = data
                hit = True
        return hit

    published = request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
    cfg = siteconfig.normalize(published)
    if not _patch(cfg):
        return JsonResponse({"error": "block not found"}, status=404)
    new_cfg = siteconfig.normalize(cfg)
    # SE-5b-2: `_draft` живёт вне normalize — патчим и его, чтобы восстановление
    # черновика не вернуло старое фото.
    db_draft = published.get("_draft")
    if isinstance(db_draft, dict):
        draft = siteconfig.normalize(db_draft)
        _patch(draft)
        new_cfg = {**new_cfg, "_draft": draft, "_draft_ts": published.get("_draft_ts", "")}
    request.tenant.site_config = new_cfg
    request.tenant.save(update_fields=["site_config", "updated_at"])
    sess = request.session.get("site_preview_draft")
    if isinstance(sess, dict) and _patch(sess):
        request.session["site_preview_draft"] = sess
    return JsonResponse({"url": ref["url"]})


@login_required
@require_POST
def site_inline_edit(request):
    """V3 inline-edit: сохранить одно текстовое поле, отредактированное прямо на
    превью (contenteditable). Белый список полей — тексты hero/about; запись в
    site_config. Возврат 204."""
    import json

    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.tenants import siteconfig

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    field = data.get("field")
    value = data.get("value", "")
    value = value.strip() if isinstance(value, str) else ""
    cfg = siteconfig.normalize(request.tenant.site_config)
    if field in siteconfig.TEXT_FIELDS:
        cfg[field] = value
    elif field in siteconfig.NESTED_TEXT_FIELDS:
        # M20: вложенное поле секции ("cta.title") — пишем в дочерний словарь.
        parent, child = field.split(".", 1)
        section = dict(cfg.get(parent) or {})
        section[child] = value
        cfg[parent] = section
    elif field and field.startswith("section_titles."):
        # V3+: заголовки секций главной правятся прямо на превью (клик по «heading»).
        key = field.split(".", 1)[1]
        if key not in siteconfig.SECTION_TITLE_KEYS:
            return HttpResponseBadRequest()
        titles = dict(cfg.get("section_titles") or {})
        titles[key] = value  # пусто → normalize вернёт дефолтный i18n-заголовок
        cfg["section_titles"] = titles
    elif field and field.startswith("section_intros."):
        # H1: описания секций главной правятся инлайн на превью (как заголовки).
        key = field.split(".", 1)[1]
        if key not in siteconfig.SECTION_INTRO_KEYS:
            return HttpResponseBadRequest()
        intros = dict(cfg.get("section_intros") or {})
        intros[key] = value  # пусто → normalize уберёт ключ (на витрине описания нет)
        cfg["section_intros"] = intros
    else:
        return HttpResponseBadRequest()
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    return HttpResponse(status=204)


@login_required
def sections_view(request):
    """Обложки разделов (S3): интро-текст + hero-фото на каждый лендинг архетипа.
    Рендерятся поверх его публичной страницы (storefront/_archetype_cover.html).
    Сохранение мёржит в site_config, сохраняя оверрайды тизеров (label/blurb)."""
    from apps.tenants import siteconfig, storefront

    if request.method == "POST":
        # S3b: загрузка/удаление фото галереи раздела (multipart, отдельно).
        action = request.POST.get("action")
        if action == "upload_cover_gallery":
            _upload_cover_gallery(request, request.POST.get("archetype", ""))
            return redirect("site-sections")
        if action == "delete_cover_image":
            _delete_cover_image(
                request, request.POST.get("archetype", ""), request.POST.get("image_id", "")
            )
            return redirect("site-sections")
        # Загрузка баннера раздела файлом (альтернатива URL-полю).
        if action == "upload_cover_hero":
            _upload_cover_hero(request, request.POST.get("archetype", ""))
            return redirect("site-sections")
        config = siteconfig.normalize(request.tenant.site_config)
        arch = dict(config.get("archetypes") or {})
        for spec in storefront.cover_specs(request.tenant):
            key = spec["key"]
            cur = dict(arch.get(key) or {})
            cur["intro"] = request.POST.get(f"intro_{key}", "").strip()
            cur["hero_image"] = request.POST.get(f"hero_{key}", "").strip()
            arch[key] = cur
        config["archetypes"] = arch
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("site-sections")

    return render(
        request,
        "tenant/site_sections.html",
        {"nav": "site", "cover_specs": storefront.cover_specs(request.tenant)},
    )


# UA4-1: подписи секций детальной (event/product) переехали в единый реестр
# `apps.core.detail_sections` (KEYS+LABELS вместе); читаются через `section_labels`.


@login_required
def pages_view(request):
    """M20U-7 «Pages»: per-page настройки витрины — раскладки сеток страниц
    каталога /sortiment/, номеров /unterkunft/ и списка событий /veranstaltung/.
    Сохранение мёржит в site_config, прочие настройки не затрагивая."""
    from apps.tenants import siteconfig

    if request.method == "POST":
        config = siteconfig.normalize(request.tenant.site_config)
        config["catalog_layout"] = {"preset": request.POST.get("catalog_preset", "")}
        config["detail_related_layout"] = {"preset": request.POST.get("related_preset", "")}
        config["stay_index_layout"] = {
            "preset": request.POST.get("stay_index_preset", ""),
            "mobile": 1,
        }
        config["events_index_layout"] = {"preset": request.POST.get("events_index_preset", "")}
        # M20U-4: порядок/видимость тематических секций детальной события.
        ed_rows = []
        for key in siteconfig.EVENT_DETAIL_SECTION_KEYS:
            try:
                order = int(request.POST.get(f"ed_order_{key}", "999"))
            except (TypeError, ValueError):
                order = 999
            ed_rows.append((order, key, request.POST.get(f"ed_visible_{key}") == "on"))
        ed_rows.sort(key=lambda r: r[0])
        config["event_detail"] = {
            "order": [k for _o, k, _v in ed_rows],
            "hidden": [k for _o, k, v in ed_rows if not v],
        }
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("site-pages")

    config = siteconfig.normalize(request.tenant.site_config)
    preset_options = [
        ("list", _("List")),
        ("cols2", _("2 per row")),
        ("cols3", _("3 per row")),
        ("cols4", _("4 per row")),
        ("gallery", _("Gallery")),
    ]
    from apps.core import modules

    # M20U-4: секции детальной события в текущем порядке + видимость.
    ed = config["event_detail"]
    ed_hidden = set(ed["hidden"])
    ed_seen = set(ed["order"])
    ed_full = ed["order"] + [k for k in siteconfig.EVENT_DETAIL_SECTION_KEYS if k not in ed_seen]
    _event_labels = detail_sections.section_labels("events")
    event_sections = [
        {
            "key": k,
            "label": _event_labels.get(k, k),
            "order": i + 1,
            "visible": k not in ed_hidden,
        }
        for i, k in enumerate(ed_full)
    ]
    return render(
        request,
        "tenant/site_pages.html",
        {
            "nav": "site",
            "preset_options": preset_options,
            "catalog_preset": config["catalog_layout"]["preset"],
            "related_preset": config["detail_related_layout"]["preset"],
            "stay_index_preset": config["stay_index_layout"]["preset"],
            "events_index_preset": config["events_index_layout"]["preset"],
            "event_sections": event_sections,
            # Показываем настройку страницы, только если её модуль активен.
            "has_catalog": modules.is_module_active(request.tenant, "catalog"),
            "has_stays": modules.is_module_active(request.tenant, "stays"),
            "has_events": modules.is_module_active(request.tenant, "events"),
        },
    )


@login_required
def menu_builder_view(request):
    """Билдер меню витрины (S7b): дерево пунктов top + bottom, привязка к
    архетипам/категориям/страницам/URL/якорям, вложенность 2 уровня.

    Редактор — на клиенте (ванильный JS): модель сериализуется в скрытый JSON,
    сервер санитайзит через siteconfig.normalize (источник правды по схеме).
    Сохранение мёржит в текущий site_config, прочие настройки не затрагивая.
    """
    import json

    from apps.core import modules
    from apps.tenants import siteconfig

    if request.method == "POST":
        try:
            data = json.loads(request.POST.get("menus_json", "") or "{}")
        except (ValueError, TypeError):
            data = None
        config = siteconfig.normalize(request.tenant.site_config)
        # Битый/пустой payload не трогает меню (не затираем при сбое редактора);
        # валидное дерево (есть top/bottom) — пишем, normalize санитайзит.
        if isinstance(data, dict) and ("top" in data or "bottom" in data):
            config["menus"] = data
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("site-menu")

    tenant = request.tenant
    menus = siteconfig.normalize(tenant.site_config)["menus"]
    # Доступные цели для выпадашек редактора.
    archetype_targets = [
        {"value": s.key, "label": s.storefront_label or s.label_de}
        for s in modules.active_modules(tenant)
        if s.storefront_landing
    ]
    category_targets = []
    if modules.is_module_active(tenant, "catalog"):
        from apps.catalog.models import Category

        category_targets = [
            {"value": c.slug, "label": c.name}
            for c in Category.objects.filter(is_active=True).order_by("name")
        ]
    page_targets = [
        {"value": "home", "label": "Startseite"},
        {"value": "about", "label": "Über uns"},
    ]
    promo_group_targets = []
    if modules.is_module_active(tenant, "promotions"):
        from apps.promotions.models import Promotion

        groups = (
            Promotion.objects.filter(status="active")
            .exclude(group="")
            .values_list("group", flat=True)
            .distinct()
        )
        promo_group_targets = [{"value": g, "label": g} for g in sorted(set(groups))]
    builder = {
        "menus": menus,
        "types": list(siteconfig.MENU_NODE_TYPES),
        "archetypes": archetype_targets,
        "categories": category_targets,
        "pages": page_targets,
        "promo_groups": promo_group_targets,
        "styles": list(siteconfig.NAV_STYLES),
    }
    return render(request, "tenant/site_menu.html", {"nav": "site", "builder": builder})


@login_required
def modules_view(request):
    """Страница «Module» (Track D / D0b): тумблеры опциональных блоков кабинета.

    Core-модули показаны задизейбленными; запись — в Tenant.disabled_modules
    (храним выключенное). Read-only при gated-подписке обеспечивает
    SubscriptionGatingMiddleware (путь под /dashboard/).
    """
    from apps.core import modules as registry

    tenant = request.tenant
    optional = registry.optional_modules()
    if request.method == "POST":
        enabled_keys = set(request.POST.getlist("modules"))
        previously_disabled = set(tenant.disabled_modules or [])
        tenant.disabled_modules = [spec.key for spec in optional if spec.key not in enabled_keys]
        tenant.save(update_fields=["disabled_modules", "updated_at"])
        # Гибрид: включение неподходящего вертикали блока — с предупреждением
        # (осознанный выбор, не запрет).
        odd = [
            spec.label_de
            for spec in optional
            if spec.key in enabled_keys
            and spec.key in previously_disabled
            and not registry.is_suited_for(spec, tenant.business_type)
        ]
        if odd:
            messages.warning(
                request,
                _("Note: %(modules)s is untypical for your business type — enabled anyway.")
                % {"modules": ", ".join(odd)},
            )
        messages.success(request, "Gespeichert.")
        return redirect("modules")

    dep_labels = {spec.key: spec.label_de for spec in registry.REGISTRY}

    def _row(spec):
        return {
            "spec": spec,
            "active": registry.is_module_active(tenant, spec.key),
            "enabled": spec.core or spec.key not in (tenant.disabled_modules or []),
            "depends_on": [dep_labels[dep] for dep in spec.depends_on],
            "recommended": tenant.business_type in spec.recommended_for,
            "suited_label": registry.suited_label(spec),
        }

    # AB2 (анти-Битрикс): 3 секции в языке задач —
    #  «Für Ihr Geschäft empfohlen» (core + подходящие вертикали, не premium),
    #  «Weitere Funktionen» (универсальные/прочие, не premium),
    #  «Premium» (premium=True, бейдж тарифа).
    recommended = [
        _row(spec)
        for spec in registry.REGISTRY
        if not spec.premium and (spec.core or registry.is_suited_for(spec, tenant.business_type))
    ]
    other = [
        _row(spec)
        for spec in registry.REGISTRY
        if not spec.premium
        and not spec.core
        and not registry.is_suited_for(spec, tenant.business_type)
    ]
    premium = [_row(spec) for spec in registry.REGISTRY if spec.premium]
    return render(
        request,
        "tenant/modules.html",
        {"nav": "modules", "rows": recommended, "other_rows": other, "premium_rows": premium},
    )


@login_required
def domains_view(request):
    """Список custom-доменов бизнеса + форма добавления и DNS-инструкция."""
    return render(
        request,
        "tenant/domains.html",
        {
            "nav": "domains",
            "domains": request.tenant.custom_domains.all(),
            "target_ip": getattr(settings, "CUSTOM_DOMAIN_TARGET_IP", ""),
        },
    )


@login_required
@require_POST
def domain_add(request):
    try:
        domain = domains.validate_new_domain(request.POST.get("domain", ""))
    except domains.DomainError as exc:
        messages.error(request, str(exc))
        return redirect("domains")
    CustomDomain.objects.create(domain=domain, tenant=request.tenant)
    messages.success(request, _("Domain added. Set the DNS A record, then verify."))
    return redirect("domains")


@login_required
@require_POST
def domain_verify(request, pk):
    custom = get_object_or_404(CustomDomain, pk=pk, tenant=request.tenant)
    if domains.verify(custom):
        messages.success(request, _("Domain verified and active."))
    else:
        messages.error(request, custom.last_check_error or _("Verification failed."))
    return redirect("domains")


@login_required
@require_POST
def domain_remove(request, pk):
    custom = get_object_or_404(CustomDomain, pk=pk, tenant=request.tenant)
    domains.remove(custom)
    messages.success(request, _("Domain removed."))
    return redirect("domains")


@login_required
def media_library(request):
    """CM-4: медиа-библиотека — все загруженные файлы тенанта (реестр MediaAsset).

    Пустой реестр при первом заходе — ленивый backfill из FileRef-копий.
    Alt-редактор пишет в реестр + write-back в копии (источник рендера —
    FileRef). Удаление — только незанятых (media_registry.delete_unused).
    """
    from apps.core import media_registry
    from apps.core.models import MediaAsset

    tenant = getattr(request, "tenant", None)
    if request.method == "POST":
        action = request.POST.get("action", "")
        asset = MediaAsset.objects.filter(pk=request.POST.get("pk", None) or None).first()
        if asset is not None:
            if action == "alt":
                alt = dict(asset.alt or {})
                alt["de"] = (request.POST.get("alt_de") or "").strip()[:200]
                asset.alt = alt
                asset.save(update_fields=["alt", "updated_at"])
                media_registry.write_back_alt(asset.path, alt, tenant)
                messages.success(request, _("Alt text saved."))
            elif action == "delete":
                if media_registry.delete_unused(asset, tenant):
                    messages.success(request, _("File deleted."))
                else:
                    messages.error(request, _("File is still in use."))
        return redirect("media-library")

    if not MediaAsset.objects.exists():
        media_registry.backfill(tenant)  # первый заход — засеять из существующего
    folder = request.GET.get("ordner", "")
    assets_qs = MediaAsset.objects.all()
    if folder:
        assets_qs = assets_qs.filter(folder=folder)
    used = media_registry.used_paths(tenant)
    assets = [{"asset": a, "used": a.path in used} for a in assets_qs[:200]]
    folders = list(
        MediaAsset.objects.exclude(folder="")
        .values_list("folder", flat=True)
        .distinct()
        .order_by("folder")
    )
    return render(
        request,
        "tenant/media_library.html",
        {"nav": "media", "assets": assets, "folders": folders, "folder": folder},
    )
