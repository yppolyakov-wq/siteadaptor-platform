"""Общие tenant-facing вьюхи (живут в схеме арендатора)."""

import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.option_styles import VARIANT_STYLES
from apps.core import detail_sections, presence
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
    # мастер (нетронутое состояние: первый шаг, ничего не выполнено и не
    # пропущено, не завершён), попадает сразу в Onboarding-Wizard, а не в пустой
    # кабинет. Любое действие в мастере (Weiter/Überspringen/Zurück) уводит из
    # нетронутого состояния и снимает редирект — остальной кабинет не гейтится.
    untouched = (
        not state["completed"]
        and state["step"] == onboarding.STEP_KEYS[0]
        and not state["skipped"]
        and not state["done"]
    )
    if untouched:
        return redirect("setup")

    from apps.core import archetypes, sales_page
    from apps.core import dashboard as dash

    tenant = request.tenant
    # X3 (вариант B плана cabinet-cleanup): первый экран = РАБОЧАЯ ПЕТЛЯ архетипа
    # (отель → Belegungsplan, салон → Tagesplan, магазин/гастро → заказы, заявки →
    # доска), а не набор плиток. Контекст и тело — те же, что у страницы Verkäufe
    # (`body_context` + `core/_sales_body.html`), поэтому петля не форкается.
    loop_kind = (sales_page.visible_kinds(tenant) or [""])[0]
    loop_view = sales_page.resolve_view(tenant, loop_kind) if loop_kind else ""
    loop_ctx = {}
    if loop_kind:
        sub = sales_page.body_context(request, loop_kind, loop_view)
        if isinstance(sub, dict):
            loop_ctx = sub
    heute = sales_page.heute_columns(tenant)
    ctx = {
        "nav": "dashboard",
        # X2a: ОДИН механизм прогресса — единый чек-лист (реестр шагов мастера +
        # перенесённый пункт часов).
        "checklist": onboarding.setup_checklist(tenant),
        # ST-4a: виджеты «что сегодня» — сжаты в полосу над петлёй (X3).
        "widgets": dash.home_widgets(tenant),
        # X3: сама петля — через общий партиал тела продаж.
        "active_kind": loop_kind,
        "active_view": loop_view,
        "sales_primary_is_stays": archetypes.primary_module(tenant) == "stays",
        # LS-2: карточка присутствия «Jetzt erreichbar» (режим + живой статус).
        "presence_mode": presence.mode(tenant),
        "presence_now": presence.available_now(tenant),
        "presence_number": getattr(tenant, "whatsapp_number", ""),
        # Полоса «сегодня» над петлёй: заезды/выдачи/записи (SM-2 колонки).
        "heute_columns": heute,
        "heute_has_items": any(col["items"] for col in heute),
    }
    return render(request, "tenant/dashboard.html", {**loop_ctx, **ctx})


@login_required
def setup_view(request):
    """Onboarding-Wizard: тонкий диспетчер шагов (AB6.1).

    Слайды (сохранение полей + контекст) — реестр apps.core.setup_steps.HANDLERS;
    порядок/статусы — apps.tenants.onboarding.SETUP_STEPS (state v2 в
    site_config["onboarding"], легаси-int-шаги мапятся). Рельса прогресса
    позволяет прыгнуть к любому шагу (?step=<key>) и дозаполнить пропущенное;
    здесь остаются только глобальные action'ы мастера.
    """
    from apps.core import setup_steps
    from apps.tenants import demo, onboarding

    tenant = request.tenant

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "skip":
            onboarding.advance(tenant, skip=True)
            return redirect("setup")
        if action == "back":
            onboarding.back(tenant)
            return redirect("setup")
        # AB6.9 «Später fertigstellen»: выйти в кабинет (мастер помечается тронутым,
        # AB5-редирект не зациклит; владелец может вернуться позже).
        if action == "exit":
            onboarding.leave(tenant)
            return redirect("dashboard")
        # B.1 (анти-Битрикс): наполнить сайт демо-контентом прямо из мастера, чтобы
        # после онбординга витрина была НЕ пустой (обратимо). Остаёмся на шаге.
        if action == "load_demo":
            if demo.load_demo(tenant):
                messages.success(request, _("Example content added — your site isn't empty."))
            return redirect("setup")
        if action == "clear_demo":
            if demo.clear_demo(tenant):
                messages.info(request, _("Example content removed."))
            return redirect("setup")
        # AB6.2c: мини-форма слайда «Angebot» — создать первую сущность (товар/услуга/
        # номер/событие по архетипу) и остаться на слайде (можно добавить ещё).
        if action == "create_offer":
            setup_steps.create_offer(request)
            return redirect("setup")
        # AB3/AB6.9 «Mit Beispielen starten» (слайд start): залить БОГАТОЕ демо — товары/
        # услуги/номера с ФОТО + hero-баннер + галерея (load_demo обогащён), затем шагнуть
        # дальше. Вид витрины (шаблон/раскладку) владелец выбирает на слайде «Stil» — здесь
        # авто-шаблон НЕ применяем (не перехватывать выбор). На escape-hatch business ещё
        # сохраняет тип (apply_business_type — no-op на слайде start).
        if action == "demo_start":
            setup_steps.apply_business_type(tenant, request.POST.get("business_type", ""))
            if demo.load_demo(tenant):
                messages.success(
                    request, _("Example content added — just edit it, no blank pages.")
                )
            onboarding.advance(tenant)
            return redirect("setup")
        handler = setup_steps.HANDLERS[onboarding.get_state(tenant)["step"]]
        if handler.post:
            handler.post(request)
        # AB3-v2 «живое превью»: action=live сохраняет поля текущего шага БЕЗ перехода
        # дальше (debounced fetch при вводе) — iframe-превью сразу перечитывает витрину.
        if action == "live":
            from django.http import HttpResponse

            return HttpResponse(status=204)
        onboarding.advance(tenant)
        return redirect("setup")

    # GET: рельса открывает любой шаг — ?step=<key> персистится (escape-hatch к
    # скрытому business тоже), невалидный ключ игнорируется. Без ?step= позиция на
    # скрытом шаге (свежий тенант стоит на business) → снап к первому видимому.
    wanted = request.GET.get("step")
    if wanted:
        state = onboarding.goto(tenant, wanted)
    else:
        state = onboarding.get_state(tenant)
        visible = onboarding.visible_keys(tenant)
        if state["step"] not in visible and visible:
            state = onboarding.goto(tenant, visible[0])
    step = state["step"]
    handler = setup_steps.HANDLERS[step]
    # «Step N of M» — по ВИДИМЫМ шагам тенанта; escape-hatch (скрытый шаг, напр.
    # business) не в рельсе → показываем его как «доп. шаг» без искажения счётчика.
    visible = onboarding.visible_keys(tenant)
    step_num = visible.index(step) + 1 if step in visible else len(visible)
    context = {
        "nav": "dashboard",
        "step": step,
        "step_num": step_num,
        "total": len(visible),
        "state": state,
        "steps": onboarding.steps_with_status(tenant),
        "step_template": handler.template,
        "show_preview": handler.preview,
        "live_save": handler.live,
    }
    if handler.context:
        context.update(handler.context(request))
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
            "style_hint": f("style_hint"),  # UC6-6f (normalize валидирует)
        }
    if btype == "newsletter":
        # GK-8: оверрайды заголовка/текста/кнопки (normalize держит непустые).
        return {"title": f("title"), "body": f("body"), "button_label": f("button_label")}
    if btype == "stats":
        # GK-4: textarea «wert | label» построчно — канонизацию в rows-список
        # делает строковая ветка _clean_cblock_data (normalize).
        return {"rows": post.get(f"cb_{bid}_rows", "")}
    return {}


def _cblock_entry_from_post(post, bid: str, btype: str) -> dict:
    """UC6-7b: полный entry C-блока из POST-строки формы (data + width/pos/newline/
    visual) — общий для блоков главной (cb_id) и блоков страниц (pb_id); normalize
    валидирует. enabled/order читает вызывающий цикл (маркеры у списков разные)."""
    return {
        "key": btype,
        "id": bid,
        "enabled": post.get(f"enabled_cb_{bid}") == "on",
        "data": _read_cblock_data(post, bid, btype),
        # UC6-3: ширина/положение блока (normalize валидирует;
        # раньше width C-блока терялся при Save — жил только в черновике).
        "width": post.get(f"width_cb_{bid}", "contained"),
        "pos": post.get(f"pos_cb_{bid}", ""),
        # UC6-3a: принудительный перенос ряда узких блоков.
        "newline": post.get(f"newline_cb_{bid}") == "on",
        # UC6-6b: visual блока (normalize._clean_visual клампит;
        # фон — только при включённом тоггле, color-input шлёт всегда).
        "visual": {
            "radius": post.get(f"visual_radius_px_cb_{bid}"),
            "shadow": post.get(f"visual_shadow_cb_{bid}") == "on",
            "background": (
                post.get(f"visual_bg_cb_{bid}", "")
                if post.get(f"visual_bg_on_cb_{bid}") == "on"
                else ""
            ),
            "padding": post.get(f"visual_padding_cb_{bid}"),
        },
    }


def _promo_style_options():
    """UC6-6f: [(key, DE-label)] стилей скидки для селекта промо-блока (без "").
    Fail-safe: без promotions — пустой список (селект скрыт)."""
    try:
        from apps.promotions.models import Promotion

        return [(k, label) for k, label in Promotion.DISCOUNT_STYLES if k]
    except Exception:  # noqa: BLE001
        return []


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
        # W7a: пишем ТОЛЬКО поля формы + часы — голый save() затирал параллельные
        # записи других колонок (site_config черновика билдера, owner_chat_id из
        # Telegram-вебхука, Stripe-callback) снимком на момент загрузки страницы.
        tenant.save(
            update_fields=[
                *BusinessSettingsForm.Meta.fields,
                "opening_hours_structured",
                "updated_at",
            ]
        )
        messages.success(request, _("Gespeichert."))
        return redirect("settings")
    from apps.core import modules as _mod

    return render(
        request,
        "tenant/settings.html",
        {
            "form": form,
            "nav": "settings",
            "opening_hours_rows": _opening_hours_rows(request.tenant),
            # W4-2: гейт нерелевантных полей по модулю (скрытие ТОЛЬКО CSS — поля
            # остаются в DOM, иначе Save затрёт, урок W0). Лояльность → voucher/
            # auto-redeem; зона обслуживания → Handwerker(jobs)/доставка(orders).
            "settings_show_loyalty": _mod.is_module_active(request.tenant, "loyalty"),
            "settings_show_service_area": _mod.is_module_active(request.tenant, "jobs")
            or _mod.is_module_active(request.tenant, "orders"),
            # X5-4: перекрёстная ссылка «часы бизнеса ↔ расписание слотов записи»
            # (владелец правил часы и не понимал, почему на витрине нет слотов —
            # это разные вещи; фидбэк 2026-07-30).
            "settings_show_booking_hint": _mod.is_module_active(request.tenant, "booking"),
        },
    )


def save_payment_settings(request) -> None:
    """W4-3: POST-диспетчер оплаты/доставки — секция сохраняется ТОЛЬКО при своём
    скрытом сентинеле `sec_*` (рендерится лишь когда секция показана → скрытая секция
    не затирает свои поля, guard потери). ОБЩИЙ для экрана `payment_settings` и слайда
    мастера «Zahlung» (AB6.2 payment); та же логика записи, что у старых экранов."""
    from apps.billing.views import save_stripe_methods
    from apps.orders.views import save_delivery, save_prepay, save_vorkasse

    tenant = request.tenant
    if request.POST.get("sec_stripe"):
        save_stripe_methods(tenant, request)
    if request.POST.get("sec_prepay"):
        save_prepay(tenant, request)
    if request.POST.get("sec_vorkasse"):
        save_vorkasse(tenant, request)
    if request.POST.get("sec_delivery"):
        save_delivery(tenant, request)


def payment_settings_context(request) -> dict:
    """W4-3: контекст формы оплаты/доставки (GET) — ОБЩИЙ для экрана `payment_settings`
    и слайда мастера «Zahlung» (партиал `_payment_fields.html`/`_payment_connect.html`)."""
    from apps.billing import connect
    from apps.billing.views import STRIPE_METHOD_CHOICES
    from apps.core import modules as _mod
    from apps.orders.views import _zone_rows

    tenant = request.tenant

    def _eur(cents):
        return f"{(cents or 0) / 100:.2f}"

    return {
        "orders_active": _mod.is_module_active(tenant, "orders"),
        # Stripe-Connect + Zahlarten (E7-3).
        "connect_configured": connect.is_connect_configured(),
        "connected": bool(tenant.stripe_connect_id),
        "payments_enabled": tenant.payments_enabled,
        "method_choices": STRIPE_METHOD_CHOICES,
        "selected_methods": set(getattr(tenant, "stripe_payment_methods", None) or []),
        # Vorkasse + Bank.
        "vorkasse_enabled": tenant.vorkasse_enabled,
        "bank_holder": tenant.bank_holder,
        "bank_iban": tenant.bank_iban,
        "bank_bic": tenant.bank_bic,
        # Abholung/Prepay.
        "orders_prepay": tenant.orders_prepay,
        # Lieferung/Versand (значения в €, как order_list).
        "delivery_enabled": tenant.delivery_enabled,
        "delivery_fee_eur": _eur(tenant.delivery_fee_cents),
        "delivery_free_eur": _eur(tenant.delivery_free_cents),
        "delivery_min_eur": _eur(tenant.delivery_min_cents),
        "delivery_area": tenant.delivery_area,
        "pickup_min_eur": _eur(tenant.pickup_min_cents),
        "delivery_restrict_to_zones": tenant.delivery_restrict_to_zones,
        "delivery_zone_rows": _zone_rows(tenant),
        "pickup_locations_text": "\n".join(
            f"{p['name']} | {p['address']}".rstrip(" |")
            for p in getattr(tenant, "pickup_points", [])
        ),
    }


@login_required
def payment_settings(request):
    """W4-3: единый экран «Zahlung & Versand» — свод оплаты/доставки, раньше размазанных
    по 3 экранам (Stripe-Zahlarten billing, Vorkasse/Lieferung/Abholung orders).

    Одна форма, один Save. POST диспатчит на извлечённые save-хелперы через
    `save_payment_settings`; контекст — `payment_settings_context`. Оба переиспользуются
    в слайде мастера «Zahlung». Старые экраны billing-payments/orders-settings живы.
    """
    if request.method == "POST":
        save_payment_settings(request)
        messages.success(request, _("Gespeichert."))
        return redirect("payment-settings")
    return render(
        request,
        "tenant/payment_settings.html",
        {"nav": "payments", **payment_settings_context(request)},
    )


@login_required
def finder_settings(request):
    """FD-3-lite: кабинет Finder — тумблер опции + предпросмотр дерева вопросов.

    Finder — ОПЦИЯ витрины (решение владельца 2026-07-18): страница /finder/
    отвечает 404, пока не включено. Targeted-write: пишем только `enabled` —
    кастом-вопросы (полный редактор FD-3) не трогаются. Превью показывает
    актуальное дерево (кастом → пресет архетипа)."""
    from apps.core import finder as finder_mod
    from apps.tenants import siteconfig

    tenant = request.tenant
    kind = finder_mod.primary_kind(tenant)
    # FD-3: тип slug-маппинга по primary-kind (events — только words/price:
    # у Event category — CharField, slug-скоринг не работает — селектор скрыт).
    slug_field = {"product": "category", "service": "collection", "stay": "collection"}.get(
        kind, ""
    )
    if request.method == "POST":
        cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
        fnd = dict(cfg.get("finder")) if isinstance(cfg.get("finder"), dict) else {}
        action = request.POST.get("action", "")
        if action == "save_questions":
            # FD-3: собрать сырой questions-dict — normalize_finder валидирует
            # (капы 6×8×10, дроп мусора, presence-minimal). enabled НЕ трогаем
            # (targeted-write — замок toggle_preserves_custom_questions).
            questions = _finder_questions_from_post(request.POST, slug_field)
            if questions:
                fnd["questions"] = questions
            else:
                fnd.pop("questions", None)  # пусто → возврат к пресету архетипа
            messages.success(request, _("Saved."))
        elif action == "load_preset":
            # «Branchen-Vorlage laden» — пресет как стартовая точка редактирования.
            fnd["questions"] = finder_mod.preset_tree(tenant)
            messages.success(request, _("Vorlage geladen."))
        else:  # FD-3-lite: тумблер опции
            if request.POST.get("enabled"):
                fnd["enabled"] = True
            else:
                fnd.pop("enabled", None)
            messages.success(request, _("Saved."))
        # W9-3: targeted-write узла finder (normalize_finder валидирует: капы,
        # дроп мусора, presence-minimal) — без пересборки полного конфига.
        node = siteconfig.normalize_finder(fnd)
        if node:
            cfg["finder"] = node
        else:
            cfg.pop("finder", None)
        tenant.site_config = cfg
        tenant.save(update_fields=["site_config", "updated_at"])
        return redirect("finder-settings")
    # FD-3: живые slug-опции для селектора маппинга (не свободный ввод —
    # мёртвый slug молча даёт 0 совпадений; принцип LS-3).
    slug_options = []
    if slug_field == "category":
        from apps.catalog.models import Category

        slug_options = list(Category.objects.values_list("slug", "name")[:100])
    elif slug_field == "collection":
        from apps.collections.models import Collection

        slug_options = list(Collection.objects.values_list("slug", "name")[:100])
    cfg_now = siteconfig.normalize(tenant.site_config)
    custom_questions = (cfg_now.get("finder") or {}).get("questions") or []
    return render(
        request,
        "tenant/finder_settings.html",
        {
            "nav": "finder",
            "finder_enabled": finder_mod.enabled(tenant),
            "tree": finder_mod.tree_for(tenant),
            "has_kind": bool(kind),
            # FD-3: редактор — существующие кастом-вопросы + пустые слоты.
            "finder_editor_rows": _finder_editor_rows(custom_questions),
            "finder_has_custom": bool(custom_questions),
            "finder_slug_field": slug_field,
            "finder_slug_options": slug_options,
        },
    )


def _finder_questions_from_post(post, slug_field):
    """FD-3: сырой questions-список из индексированных полей формы (q_<i>_… /
    q_<i>_chip_<j>_…). Пустые слоты пропускаются; key автогенерятся slugify с
    суффиксом при коллизии; капы/валидацию делает normalize_finder."""
    from django.utils.text import slugify

    from apps.tenants import siteconfig

    def uniq(base, used, fallback):
        key = slugify(base)[:40] or fallback
        candidate, n = key, 2
        while candidate in used:
            candidate, n = f"{key[:36]}-{n}", n + 1
        used.add(candidate)
        return candidate

    rows = []
    used_q = set()
    for i in range(siteconfig._MAX_FINDER_QUESTIONS):
        qlabel = (post.get(f"q_{i}_label") or "").strip()
        if not qlabel:
            continue
        try:
            pos = int(post.get(f"q_{i}_pos", "") or i)
        except (TypeError, ValueError):
            pos = i
        chips = []
        used_c = set()
        for j in range(siteconfig._MAX_FINDER_CHIPS):
            clabel = (post.get(f"q_{i}_chip_{j}_label") or "").strip()
            if not clabel:
                continue
            match = {}
            words = [
                w.strip() for w in (post.get(f"q_{i}_chip_{j}_words") or "").split(",") if w.strip()
            ]
            if words:
                match["words"] = words
            slug = (post.get(f"q_{i}_chip_{j}_slug") or "").strip()
            if slug and slug_field:
                match[slug_field] = slug
            for pf in ("price_min", "price_max"):
                raw = (post.get(f"q_{i}_chip_{j}_{pf}") or "").replace(",", ".").strip()
                if raw:
                    match[pf] = raw
            chips.append(
                {"key": uniq(clabel, used_c, f"chip-{j + 1}"), "label": clabel, "match": match}
            )
        if chips:
            rows.append(
                (
                    pos,
                    {
                        "key": uniq(qlabel, used_q, f"frage-{i + 1}"),
                        "label": qlabel,
                        "chips": chips,
                    },
                )
            )
    rows.sort(key=lambda r: r[0])
    return [q for _p, q in rows]


def _finder_editor_rows(custom_questions):
    """FD-3: слоты формы — существующие кастом-вопросы + 1 пустой (до капа);
    у вопроса — его чипы + 2 пустых слота (до капа). Без JS: «добавить ещё» =
    сохранить и открыть снова (слоты дорастают)."""
    from apps.tenants import siteconfig

    rows = []
    for i in range(siteconfig._MAX_FINDER_QUESTIONS):
        q = custom_questions[i] if i < len(custom_questions) else None
        if q is None and i > len(custom_questions):
            break  # ровно один пустой слот после существующих
        chips = list((q or {}).get("chips") or [])
        chip_rows = []
        for j in range(siteconfig._MAX_FINDER_CHIPS):
            c = chips[j] if j < len(chips) else None
            if c is None and j > len(chips) + 1:
                break  # два пустых чип-слота
            match = (c or {}).get("match") or {}
            chip_rows.append(
                {
                    "j": j,
                    "label": (c or {}).get("label", ""),
                    "words": ", ".join(match.get("words") or []),
                    "slug": match.get("collection") or match.get("category") or "",
                    "price_min": match.get("price_min", ""),
                    "price_max": match.get("price_max", ""),
                }
            )
        rows.append({"i": i, "label": (q or {}).get("label", ""), "chips": chip_rows})
    return rows


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
    tenant = request.tenant
    if request.method == "POST":
        if save_languages(request):
            messages.success(request, _("Saved."))
            return redirect("languages")
        messages.error(request, _("Please enable at least one language."))
    return render(
        request,
        "tenant/languages.html",
        {"languages": languages_context(tenant), "nav": "languages"},
    )


def save_languages(request) -> bool:
    """L2/AB6.2-lang: сохранить включённые языки витрины + дефолт из POST
    (`locales` чекбоксы + `default_locale`). ОБЩИЙ для кабинета «Sprachen» и слайда
    мастера. Инварианты: минимум один язык; дефолт ∈ включённые. False = ничего
    не выбрано (настройки не тронуты)."""
    registry = [code for code, _label in settings.LANGUAGES]
    # Порядок — как в реестре (стабильно), дубли/не-реестр отфильтрованы.
    chosen = set(request.POST.getlist("locales"))
    enabled = [code for code in registry if code in chosen]
    if not enabled:
        return False
    default = request.POST.get("default_locale", "")
    if default not in enabled:
        default = enabled[0]  # инвариант: дефолт ∈ включённые
    tenant = request.tenant
    tenant.enabled_locales = enabled
    tenant.default_locale = default
    tenant.save(update_fields=["enabled_locales", "default_locale"])
    return True


def languages_context(tenant) -> list[dict]:
    """L2/AB6.2-lang: языки реестра как [{code,label,enabled,is_default}] — общий
    контекст кабинета «Sprachen» и слайда мастера."""
    registry = [code for code, _label in settings.LANGUAGES]
    lang_names = dict(settings.LANGUAGES)
    current = set(tenant.active_locales)
    return [
        {
            "code": code,
            "label": lang_names.get(code, code.upper()),
            "enabled": code in current,
            "is_default": code == tenant.default_locale,
        }
        for code in registry
    ]


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
        # W9-5: реквизиты (USt-IdNr./Steuernummer/§19/Register/Verantwortlicher)
        # переехали сюда из «Mein Geschäft» — свой сентинел + update_fields
        # (единственный писатель; форма настроек их больше не содержит).
        if request.POST.get("sec_steuer"):
            tenant.vat_id = request.POST.get("vat_id", "").strip()[:32]
            tenant.tax_number = request.POST.get("tax_number", "").strip()[:32]
            tenant.small_business = bool(request.POST.get("small_business"))
            tenant.register_entry = request.POST.get("register_entry", "").strip()[:200]
            tenant.legal_responsible = request.POST.get("legal_responsible", "").strip()[:200]
            tenant.save(
                update_fields=[
                    "vat_id",
                    "tax_number",
                    "small_business",
                    "register_entry",
                    "legal_responsible",
                    "updated_at",
                ]
            )
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
    return render(
        request,
        "tenant/legal_docs.html",
        {"kinds": kinds, "nav": "legal-docs", "steuer": tenant},
    )


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
            messages.info(request, _("Galerie-Limit erreicht."))
            break
        try:
            gallery.append(save_product_image(f, sort_order=len(gallery), folder="gallery"))
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
    cfg["gallery"] = gallery
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, _("Bilder hochgeladen."))


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
        messages.success(request, _("Bild gelöscht."))


@login_required
def site_view(request):
    """W11-5 (Website-свод): страница «Site» умерла — Studio единственный вход.

    Её функции переехали в билдер: quick-start (шаблоны + демо) — область
    «Schnellstart» рейки, фон баннера/быстрый заказ — форма билдера, видео
    галереи — область «Медиа», контент-секции и галерея были общими и раньше.
    Остаётся 302 с переносом GET (прецедент W10-6): старые ссылки/закладки живы.
    """
    from django.http import HttpResponseRedirect
    from django.urls import reverse

    qs = request.GET.urlencode()
    return HttpResponseRedirect(reverse("site-home") + (f"?{qs}" if qs else ""))


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


def _redirect_builder(request):
    """UC6-7b: возврат в билдер ПОСЛЕ действия инсертера — канва открывается на той
    же странице, где вставляли (page_path из POST → ?page= deep-link, см. T-6.1)."""
    from urllib.parse import quote

    from django.urls import reverse

    page_path = _safe_preview_page(request.POST.get("page_path"))
    if page_path != "/":
        return redirect(f"{reverse('site-home')}?page={quote(page_path)}")
    return redirect("site-home")


def _page_preset_ui(tenant, config):
    """ST-2: данные пикеров пресетов страниц для scoped-строк панели билдера
    («Über uns» всегда — страница есть у всех; корзина — при активном каталоге).
    config — уже нормализованный site_config."""
    from apps.core import page_presets

    hosts = (("info", True), ("cart", tenant.is_module_active("catalog")))
    return [
        {
            "host": host,
            "page_key": host,
            "presets": page_presets.presets_for(host, tenant.business_type),
            "current": page_presets.current_preset(config, host),
        }
        for host, enabled in hosts
        if enabled
    ]


def _add_block_fetch_response(request, new_id, host):
    """UC6-7c-2: JSON-ответ инсертера-без-перезагрузки — HTML строки нового C-блока
    (тот же партиал `_cb_row.html`, что и в форме) для вставки в редактор без
    навигации. Только для хостов страниц (host); главная/ошибка → {ok:false} (клиент
    откатывается на форм-POST с перезагрузкой). Блок уже сохранён в add_block."""
    from django.http import JsonResponse
    from django.template.loader import render_to_string

    from apps.tenants import siteconfig

    if not new_id or not host:
        return JsonResponse({"ok": False})
    cfg = siteconfig.normalize(request.tenant.site_config)
    container = (cfg.get("page_blocks") or {}).get(host, [])
    row, order = None, 1
    for i, s in enumerate(container, start=1):
        if s.get("id") == new_id:
            row, order = s, i
            break
    if row is None:
        return JsonResponse({"ok": False})
    b = {
        "id": row["id"],
        "type": row["key"],
        "enabled": row["enabled"],
        "data": row["data"],
        "order": order,
        "width": row.get("width", "contained"),
        "pos": row.get("pos", ""),
        "newline": bool(row.get("newline")),
        "visual": row.get("visual") or {},
    }
    row_html = render_to_string(
        "tenant/_cb_row.html",
        {
            "b": b,
            "pb_page": host,
            "promos_for_blocks": _promos_for_blocks(request),
            "promo_style_options": _promo_style_options(),
        },
        request=request,
    )
    return JsonResponse({"ok": True, "id": new_id, "host": host, "row_html": row_html})


@login_required
def home_builder_view(request):
    """Конструктор главной (S2b): порядок/видимость блоков главной + тизеры
    архетипов. Отдельная страница — «подключать/выключать выведение блоков».

    Контент блоков (тексты hero/about, FAQ, галерея, цвета, шрифты, навигация)
    правится на «Site»; здесь — только композиция главной. Сохранение мёржит в
    текущий site_config (остальные настройки не затрагиваются).
    """
    from apps.core.seo import _dumps as _safe_json  # LOW: инлайн-<script>-safe JSON
    from apps.tenants import demo, siteconfig, sitetemplates, storefront

    if request.method == "POST":
        # M20e: медиа галереи — отдельные multipart-формы (upload/delete), общие
        # с «Site» хелперы; обрабатываем до основной формы композиции.
        if request.POST.get("action") == "upload_gallery":
            _upload_gallery_images(request)
            return redirect("site-home")
        if request.POST.get("action") == "delete_gallery_image":
            _delete_gallery_image(request, request.POST.get("image_id", ""))
            return redirect("site-home")
        # W11-5: видео галереи (перенос со страницы «Site») — targeted-write одним
        # ключом; early-return, чтобы форма области не проваливалась в main-save.
        if request.POST.get("action") == "save_gallery_video":
            cfg = siteconfig.normalize(request.tenant.site_config)
            cfg["gallery_video"] = request.POST.get("gallery_video", "").strip()
            request.tenant.site_config = siteconfig.normalize(cfg)
            request.tenant.save(update_fields=["site_config", "updated_at"])
            messages.success(request, _("Gespeichert."))
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
        # W11-5 (Website-свод): quick-start со страницы «Site» — шаблоны витрины
        # и демо-контент теперь в Studio (область «Schnellstart»). Те же библиотеки,
        # что у мастера; early-return ДО main-save (fall-through стёр бы секции).
        if request.POST.get("action") == "apply_template":
            if sitetemplates.apply_template(request.tenant, request.POST.get("template", "")):
                messages.success(request, _("Vorlage übernommen."))
            else:
                messages.error(request, _("Unbekannte Vorlage."))
            return redirect("site-home")
        if request.POST.get("action") == "load_demo":
            if demo.load_demo(request.tenant):
                messages.success(request, _("Demo-Inhalte geladen."))
            else:
                messages.info(request, _("Demo-Inhalte sind bereits vorhanden."))
            return redirect("site-home")
        if request.POST.get("action") == "clear_demo":
            if demo.clear_demo(request.tenant):
                messages.success(request, _("Demo-Inhalte gelöscht."))
            else:
                messages.info(request, _("Keine Demo-Inhalte vorhanden."))
            return redirect("site-home")
        # D.2b: добавить пустой C-блок (text/image/…) — появится в списке для правки.
        # E.3: необязательный `add_after` (ключ фикс-секции или id C-блока) — вставить
        # новый блок сразу ПОСЛЕ него (инсертер «+» на канвасе); иначе — в конец.
        if request.POST.get("action") == "add_block":
            import uuid

            btype = request.POST.get("block_type", "")
            # UC6-7c-2: инсертер на СТРАНИЦЕ шлёт fetch → отвечаем HTML новой строки
            # (вставка без перезагрузки билдера); обычный форм-POST — прежний редирект.
            is_fetch = request.headers.get("X-Requested-With") == "fetch"
            new_id = None
            page_key = request.POST.get("page_key", "")
            host = page_key if page_key in siteconfig.PAGE_BLOCK_HOSTS else ""
            # UC6-7c (ревью-фикс): fetch-вставка с невалидным page_key НЕ должна молча
            # уйти на главную — вернём ok:false без сохранения (клиент перезагрузит; на
            # практике page_key всегда валиден — из data-pb-host витрины).
            if is_fetch and page_key and not host:
                return _add_block_fetch_response(request, None, "")
            # UC2-3(b): ссылочные секции-справочники валидны ТОЛЬКО на странице
            # (host); на главной живут настоящие секции — там тип отклоняется.
            _allowed = siteconfig.REPEATABLE_BLOCKS + (siteconfig.PAGE_REF_BLOCKS if host else ())
            if btype in _allowed:
                cfg = siteconfig.normalize(request.tenant.site_config)
                new_id = uuid.uuid4().hex[:12]
                # UC6-5/6c: новый блок — демо-данные + опц. пресет отображения
                # (variant из двухшагового инсертера; normalize валидирует). id задаём
                # ЯВНО (после спреда) — чтобы найти блок для fetch-ответа/рендера строки.
                new_block = {
                    "key": btype,
                    "enabled": True,
                    **siteconfig.cblock_insert_preset(btype, request.POST.get("variant", "")),
                    "id": new_id,
                }
                # UC6-7b: инсертер на НЕ-главной шлёт page_key (хост из data-pb-host
                # канвы) → блок кладём в page_blocks[хост]; add_after="pbhost:<key>"
                # (якорь пустой страницы) не матчится по id → append в конец.
                if host:
                    pb = dict(cfg.get("page_blocks") or {})
                    rows = list(pb.get(host) or [])
                    _insert_after_section(rows, new_block, request.POST.get("add_after"))
                    pb[host] = rows
                    cfg["page_blocks"] = pb
                else:
                    _insert_after_section(cfg["sections"], new_block, request.POST.get("add_after"))
                request.tenant.site_config = siteconfig.normalize(cfg)
                request.tenant.save(update_fields=["site_config", "updated_at"])
                if not is_fetch:
                    messages.success(request, _("Block added."))
            if is_fetch:
                return _add_block_fetch_response(request, new_id, host)
            return _redirect_builder(request)
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
                new_block = {"key": tpl["key"], "enabled": True, "data": copy.deepcopy(tpl["data"])}
                # SE-4c: опц. insert_after (инсертер «+» на канвасе) → вставка в позицию;
                # иначе в конец (back-compat с кнопкой «Insert» в библиотеке).
                # UC6-7b: на НЕ-главной (page_key) шаблон вставляется в page_blocks[хост].
                page_key = request.POST.get("page_key", "")
                if page_key in siteconfig.PAGE_BLOCK_HOSTS:
                    pb = dict(cfg.get("page_blocks") or {})
                    rows = list(pb.get(page_key) or [])
                    _insert_after_section(rows, new_block, request.POST.get("insert_after"))
                    pb[page_key] = rows
                    cfg["page_blocks"] = pb
                else:
                    _insert_after_section(
                        cfg["sections"], new_block, request.POST.get("insert_after")
                    )
                messages.success(request, _("Template inserted."))
            elif verb == "delete_block_template" and ident in tpls:
                tpls.pop(ident)
                messages.success(request, _("Template removed."))
            cfg["block_templates"] = tpls
            request.tenant.site_config = siteconfig.normalize(cfg)
            request.tenant.save(update_fields=["site_config", "updated_at"])
            return _redirect_builder(request)
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
        # ST-2: пресет НЕ-home страницы (реестр page_presets; сейчас info/cart).
        # use_page_preset:<host>:<id> — идемпотентная замена посеянных блоков
        # page_blocks[host] + плоские ключи; блоки владельца целы. Редирект
        # через _redirect_builder — канва остаётся на настраиваемой странице.
        # DS-3c: сборка (Startpaket) — Look + виды вывода одним кликом (серверное
        # применение: виды вывода живут вне draft-канала Look-кнопок).
        if action.startswith("use_bundle:"):
            from apps.tenants import sitetemplates

            _verb, _sep, bkey = action.partition(":")
            if sitetemplates.apply_bundle(request.tenant, bkey):
                messages.success(request, _("Startpaket angewendet."))
            return _redirect_builder(request)
        if action.startswith("use_page_preset:"):
            from apps.core import page_presets

            _verb, _sep, rest = action.partition(":")
            host, _sep2, preset_id = rest.partition(":")
            cfg = siteconfig.normalize(request.tenant.site_config)
            if page_presets.apply_page_preset(cfg, host, preset_id):
                request.tenant.site_config = siteconfig.normalize(cfg)
                request.tenant.save(update_fields=["site_config", "updated_at"])
                messages.success(request, _("Page template applied."))
            return _redirect_builder(request)
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
            # UC6-6d: вариант отображения секции (normalize валидирует по SECTION_STYLES).
            entry["style"] = request.POST.get(f"style_{key}", "")
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
                # DS-5: симметрия/лента (чекбокс не прислан = выкл — presence).
                if request.POST.get(f"balance_{key}") == "on":
                    lay["balance"] = True
                if request.POST.get(f"scroll_{key}") == "on":
                    lay["scroll"] = True
                # DS-5: плитка категорий — высота фото + инфо-строка.
                if key == "categories":
                    if request.POST.get("img_h_categories", ""):
                        entry["img_h"] = request.POST.get("img_h_categories")
                    ti = []
                    if request.POST.get("tile_price_categories") == "on":
                        ti.append("price")
                    if request.POST.get("tile_count_categories") == "on":
                        ti.append("count")
                    if ti:
                        entry["tile_info"] = ti
                if lay:
                    entry["layout"] = lay
            if key in siteconfig.GRID_SECTION_LIMITS:
                entry["limit"] = request.POST.get(f"limit_{key}", "")
            if key == "products":
                entry["source"] = request.POST.get("source_products", "")
                # MEN-24c: кап строк прайс-вида (пусто → normalize ключ не пишет)
                entry["rows"] = request.POST.get("rows_products", "")
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
            items.append((order, _cblock_entry_from_post(request.POST, bid, btype)))
        items.sort(key=lambda row: row[0])
        config["sections"] = [entry for _o, entry in items]
        # UC6-7b: C-блоки СТРАНИЦ (page_blocks) — пересборка целиком из pb_id-строк
        # под presence-guard (POST без формы страниц не должен стереть конфиг).
        # В форме рендерится строка КАЖДОГО непустого хоста (page_cblocks; пустых
        # хостов в конфиге и не бывает — normalize_page_blocks дропает `if blocks`),
        # поэтому пересборка из всех pb_id-строк не теряет блоки других страниц.
        if request.POST.get("pb_present") == "1":
            pb_items: dict[str, list] = {}
            for bid in request.POST.getlist("pb_id"):
                host = request.POST.get(f"pb_page_{bid}", "")
                btype = request.POST.get(f"cb_type_{bid}", "")
                if host not in siteconfig.PAGE_BLOCK_HOSTS:
                    continue
                # UC2-3(b): на страницах валидны и ссылочные секции-справочники.
                if (
                    btype not in siteconfig.REPEATABLE_BLOCKS
                    and btype not in siteconfig.PAGE_REF_BLOCKS
                ):
                    continue
                if request.POST.get(f"delete_cb_{bid}") == "on":
                    continue  # удалён владельцем
                try:
                    order = int(request.POST.get(f"order_cb_{bid}", "999"))
                except (TypeError, ValueError):
                    order = 999
                pb_items.setdefault(host, []).append(
                    (order, _cblock_entry_from_post(request.POST, bid, btype))
                )
            config["page_blocks"] = {
                host: [entry for _o, entry in sorted(rows, key=lambda r: r[0])]
                for host, rows in pb_items.items()
            }
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
            # DS-3a: страничные extra-виды (напр. «preisliste» каталога) валидны
            # только для СВОЕЙ страницы (PAGE_EXTRA_PRESETS).
            if preset in siteconfig.LAYOUT_PRESETS or preset in siteconfig.PAGE_EXTRA_PRESETS.get(
                cfg_key, ()
            ):
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
            # ST-7c: форма карточки ("" = прежняя; normalize отбрасывает мусор).
            "card_style": request.POST.get("sd_card_style", ""),
            # O-2: дефолтный вид выбора вариантов для всего магазина ("" = список).
            "variant_style": request.POST.get("sd_variant_style", ""),
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
            # ФИКС (2026-07-16): шапка витрины рендерит menus.top (top_meta) — зеркалим
            # style/sticky и туда, иначе на конфиге с материализованным `menus`
            # (после первого Save) пикер стиля/пресеты UC6-6h были no-op. Без `menus`
            # в конфиге normalize сам выведет top из nav — зеркалить нечего.
            menus = config.get("menus")
            if isinstance(menus, dict) and isinstance(menus.get("top"), dict):
                menus["top"]["style"] = nav["style"]
                menus["top"]["sticky"] = nav["sticky"]
        # SE-7d: область «Баннер» — заголовок/текст hero (presence-guard, чтобы прочие
        # сохранения не затирали; инпуты пред-заполнены из config → round-trip).
        if "hero_title" in request.POST:
            config["hero_title"] = request.POST.get("hero_title", "").strip()
            config["hero_text"] = request.POST.get("hero_text", "").strip()
        # W11-5: фон баннера по URL (перенос со страницы «Site») — presence-guard.
        if "hero_image" in request.POST:
            config["hero_image"] = request.POST.get("hero_image", "").strip()
        # W11-5: быстрый заказ на карточках — чекбокс, поэтому сентинел присутствия
        # (unchecked не шлётся; без сентинела любое иное сохранение гасило бы тумблер).
        if request.POST.get("quick_add_present") == "1":
            config["quick_add"] = request.POST.get("quick_add") == "on"
        # M20f: дизайн — шрифт + стиль hero (site_config); акцент — поле Tenant.
        config["font"] = request.POST.get("font", config.get("font", "system"))
        config["hero_style"] = "accent" if request.POST.get("hero_accent") == "on" else "plain"
        # ST-1b: тёмный Look — hidden-input `theme` ВСЕГДА в форме (W0-инвариант,
        # пред-заполнен текущим значением); "dark" → ключ, иначе снимаем (билдер —
        # единый источник темы, W6). Presence-guard: без поля в POST не трогаем.
        if "theme" in request.POST:
            if request.POST.get("theme") == "dark":
                config["theme"] = "dark"
            else:
                config.pop("theme", None)
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
        messages.success(request, _("Gespeichert."))
        # UC6-7b: Save с канвы на подстранице возвращает канву на ТУ ЖЕ страницу
        # (page_path — скрытое поле формы, синкается JS при навигации кадра).
        return _redirect_builder(request)

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
    # UC6-7b: C-блоки страниц (page_blocks) — строки формы для набора «Landing pages»
    # (общий партиал _cb_row; порядок хостов стабильный — по PAGE_BLOCK_HOSTS).
    page_cblocks = []
    for host in siteconfig.PAGE_BLOCK_HOSTS:
        host_rows = [
            {
                "id": s["id"],
                "type": s["key"],
                "enabled": s["enabled"],
                "data": s["data"],
                "order": index,
                "width": s.get("width", "contained"),
                "pos": s.get("pos", ""),
                "newline": bool(s.get("newline")),
                "visual": s.get("visual") or {},
            }
            for index, s in enumerate((config.get("page_blocks") or {}).get(host) or [], start=1)
        ]
        if host_rows:
            page_cblocks.append({"page_key": host, "blocks": host_rows})
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
                    "visual": s.get("visual") or {},  # UC6-6b
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
                # DS-5: симметрия/лента + плитка категорий (высота фото, инфо).
                "layout_balance": bool((s.get("layout") or {}).get("balance")),
                "layout_scroll": bool((s.get("layout") or {}).get("scroll")),
                "img_h": s.get("img_h", 0),
                "tile_info": s.get("tile_info", []),
                "has_limit": s["key"] in siteconfig.GRID_SECTION_LIMITS,
                "limit": s.get("limit", ""),
                "has_title": s["key"] in siteconfig.SECTION_TITLE_KEYS,
                "title": (config.get("section_titles") or {}).get(s["key"], ""),
                "has_source": s["key"] == "products",
                "source": s.get("source", ""),
                "rows": s.get("rows", ""),  # MEN-24c: кап строк прайс-вида
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
                # UC6-6d: вариант отображения секции (FAQ и др. из SECTION_STYLES).
                "style": s.get("style", ""),
                "style_options": [
                    (sk, siteconfig.SECTION_STYLE_LABELS.get(sk, sk))
                    for sk in siteconfig.SECTION_STYLES.get(s["key"], ())
                ],
            }
        )
    preset_options = [
        ("list", _("List")),
        ("cols2", _("2 per row")),
        ("cols3", _("3 per row")),
        ("cols4", _("4 per row")),
        ("cols5", _("5 per row")),  # DS-6
        ("cols6", _("6 per row")),  # DS-6
        ("gallery", _("Gallery")),
    ]
    # DS-5c (HIGH-находка ревью): селект каталога канвы обязан знать прайс-виды —
    # иначе сохранённый preisliste* не матчится ни одной опцией, браузер шлёт
    # первую ("list") и Save молча откатывает вид (класс W0).
    catalog_preset_options = preset_options + [
        (k, siteconfig.SECTION_STYLE_LABELS.get(k, k))
        for k in siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"]
    ]
    # MEN-18: у листинга услуг — свои прайс-виды (тот же класс W0: опция обязана
    # существовать, иначе Save молча откатывает сохранённый вид).
    service_preset_options = preset_options + [
        (k, siteconfig.SECTION_STYLE_LABELS.get(k, k))
        for k in siteconfig.PAGE_EXTRA_PRESETS["service_index_layout"]
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
            "page_cblocks": page_cblocks,  # UC6-7b
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
            # UC6-6f: стили вывода скидки для селекта промо-блока (fail-safe).
            "promo_style_options": _promo_style_options(),
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
                {
                    "value": "stats",
                    "label": _("Numbers"),
                    "icon": "🔢",
                    "hint": _("2–4 key figures with captions"),
                },  # GK-4
                {
                    "value": "newsletter",
                    "label": _("Newsletter"),
                    "icon": "📧",
                    "hint": _("Signup form with double opt-in"),
                },  # GK-8
                # UC2-3(b): ссылочные секции-справочники — ТОЛЬКО на страницах
                # (page_only → JS прячет на главной; контент общий с главной).
                {
                    "value": "faq_ref",
                    "label": "FAQ anzeigen",
                    "icon": "❓",
                    "hint": "Der FAQ-Block der Startseite — auch auf dieser Seite",
                    "page_only": True,
                },
                {
                    "value": "team_ref",
                    "label": "Team anzeigen",
                    "icon": "👥",
                    "hint": "Der Team-Block der Startseite — auch auf dieser Seite",
                    "page_only": True,
                },
                {
                    "value": "gallery_ref",
                    "label": "Galerie anzeigen",
                    "icon": "🖼️",
                    "hint": "Die Galerie der Startseite — auch auf dieser Seite",
                    "page_only": True,
                },
                {
                    "value": "testimonials_ref",
                    "label": "Stimmen anzeigen",
                    "icon": "💬",
                    "hint": "Kundenstimmen der Startseite — auch auf dieser Seite",
                    "page_only": True,
                },
                # AF-2b: встраиваемые формы (заявка/контакт) — на страницах;
                # рендер гейтится модулем (jobs/inbox выключен → блок пуст).
                {
                    "value": "anfrage_ref",
                    "label": "Anfrage-Formular",
                    "icon": "📝",
                    "hint": "Angebot-Anfrage direkt auf dieser Seite (Modul Aufträge)",
                    "page_only": True,
                },
                {
                    "value": "message_ref",
                    "label": "Kontaktformular",
                    "icon": "✉️",
                    "hint": "Frage-stellen-Formular direkt auf dieser Seite (Modul Nachrichten)",
                    "page_only": True,
                },
            ],
            "preset_options": preset_options,
            "catalog_preset_options": catalog_preset_options,  # DS-5c: канва-селект каталога
            "service_preset_options": service_preset_options,  # MEN-18: прайс-виды услуг
            "source_options": source_options,
            "archetype_specs": storefront.teaser_specs(request.tenant),
            "archetypes_enabled": archetypes_enabled,
            "root_options": root_options,
            "preview_pages": preview_pages,
            # UC6-1b: карта «путь → группа» для авто-скоупа панели по фактической
            # странице кадра (селектор страниц из тулбара убран). JSON, не escapejs —
            # тот кодирует дефисы (-) и ломает literal-сравнение путей.
            "preview_page_groups_json": _safe_json(
                {p["url"]: p.get("group") or "home" for p in preview_pages}
            ),
            # UC6-6c: пресеты типов блоков для двухшагового инсертера «+».
            # UC6-6e: + props пресета — JS рисует миниатюру-картинку варианта.
            "cblock_variants_json": _safe_json(
                {
                    t: [
                        {
                            "key": v["key"],
                            "label": v["label"],
                            "w": v.get("width", ""),
                            "pos": v.get("pos", ""),
                            "align": (v.get("data") or {}).get("align", ""),
                            "color": (v.get("data") or {}).get("color", ""),
                            "side": (v.get("data") or {}).get("side", ""),
                            "rounded": (v.get("data") or {}).get("rounded", ""),
                            "shadow": bool((v.get("visual") or {}).get("shadow")),
                            "bg": (v.get("visual") or {}).get("background", ""),
                            "hint": (v.get("data") or {}).get("style_hint", ""),
                            # ST-7a: высота spacer-варианта для миниатюры.
                            "height": (v.get("data") or {}).get("height", ""),
                            # GK-4: число пар полосы цифр (0 = демо-набор из 3).
                            "count": len((v.get("data") or {}).get("rows", []) or []),
                        }
                        for v in vs
                    ]
                    for t, vs in siteconfig.CBLOCK_VARIANTS.items()
                }
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
            # ST-2: пикеры пресетов НЕ-home страниц (реестр page_presets) —
            # карточки в scoped-строках панели; рекомендованные типу бизнеса
            # первыми, актив подсвечен current_preset.
            "page_preset_ui": _page_preset_ui(request.tenant, config),
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
            # ST-1b: Look-карточки архетипа (клик выставляет контролы формы) +
            # текущая тема (hidden-input `theme` — round-trip при Save).
            "looks": sitetemplates.looks_for(request.tenant.business_type),
            "bundles": sitetemplates.bundles_for(request.tenant.business_type),  # DS-3c
            "theme": config.get("theme", ""),
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
            "card_style": config["site_defaults"].get("card_style", ""),  # ST-7c
            # O-2: дефолтный вид выбора вариантов + реестр видов для селекта.
            "variant_style": config["site_defaults"].get("variant_style", ""),
            "variant_styles": VARIANT_STYLES,
            # M20d: контент-секции — те же поля/партиал, что на «Site».
            "config": config,
            "faq_text": siteconfig.pairs_to_text(config["faq"], "q", "a"),
            "testimonials_text": siteconfig.testimonials_to_text(config["testimonials"]),
            "process_text": siteconfig.pairs_to_text(config["process"], "title", "text"),
            "team_text": "\n".join(
                f"{m['name']} | {m['role']}".rstrip(" |") for m in config["team"]
            ),
            "trust_marks_text": "\n".join(config["trust"]["marks"]),
            "usp_text": siteconfig.usp_to_text(config["usp_bar"]),
            # W11-5: quick-start (шаблоны витрины + демо) — перенос со страницы «Site».
            "site_templates": sitetemplates.template_cards(request.tenant.business_type),
            "has_demo": demo.has_demo(request.tenant),
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
            messages.info(request, _("Galerie-Limit erreicht."))
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
    messages.success(request, _("Bilder hochgeladen."))


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
    messages.success(request, _("Banner hochgeladen."))


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
        messages.success(request, _("Bild gelöscht."))


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
                    # DS-5: симметрия/лента → в превью (только truthy).
                    for fld in ("balance", "scroll"):
                        if lay.get(fld):
                            sub[fld] = True
                    if sub:
                        row["layout"] = sub
                # DS-5: плитка категорий → в превью (normalize клампит/whitelist).
                if key == "categories":
                    if isinstance(item.get("img_h"), (int, str)):
                        row["img_h"] = item["img_h"]
                    if isinstance(item.get("tile_info"), list):
                        row["tile_info"] = item["tile_info"]
                # M20U-7: лимит секции-превью → в черновик (normalize клампит).
                if key in siteconfig.GRID_SECTION_LIMITS and isinstance(
                    item.get("limit"), (int, str)
                ):
                    row["limit"] = item["limit"]
                # M20U-7: источник товаров → в черновик.
                if key == "products" and item.get("source") in siteconfig.PRODUCT_SOURCES:
                    row["source"] = item["source"]
                # MEN-24c: кап строк прайс-вида → в черновик (normalize клампит).
                if key == "products" and isinstance(item.get("rows"), (int, str)):
                    row["rows"] = item["rows"]
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
                if item.get("style"):
                    row["style"] = item["style"]  # UC6-6d
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
                    if isinstance(item.get("visual"), dict):
                        cb["visual"] = item["visual"]  # UC6-6b
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
    # UC6-7b: C-блоки страниц — passthrough целиком (collect шлёт ВСЕ хосты из
    # формы, включая опустевшие после удаления); normalize_page_blocks чистит
    # (whitelist хостов, _clean_cblock, кап) на normalize ниже.
    if isinstance(data.get("page_blocks"), dict):
        cfg["page_blocks"] = data["page_blocks"]
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
    # ST-1b: тёмный Look → в превью (пустое значение снимает тёмную тему).
    if "theme" in data:
        if data.get("theme") == "dark":
            cfg["theme"] = "dark"
        else:
            cfg.pop("theme", None)
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
    # W11-5: фон баннера (URL) и быстрый заказ на карточках — перенесены со страницы
    # «Site» в билдер; в превью, иначе правка видна только после Save.
    if isinstance(data.get("hero_image"), str):
        cfg["hero_image"] = data["hero_image"].strip()
    if isinstance(data.get("quick_add"), bool):
        cfg["quick_add"] = data["quick_add"]
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
            # Фидбэк 2026-07-28: кнопка на слайдере обложки (пусто = дефолт «Discover»).
            cur["button_label"] = request.POST.get(f"btn_label_{key}", "").strip()
            cur["button_url"] = request.POST.get(f"btn_url_{key}", "").strip()
            arch[key] = cur
        config["archetypes"] = arch
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, _("Gespeichert."))
        return redirect("site-sections")

    return render(
        request,
        "tenant/site_sections.html",
        {"nav": "site", "cover_specs": storefront.cover_specs(request.tenant)},
    )


# UA4-1: подписи секций детальной (event/product) переехали в единый реестр
# `apps.core.detail_sections` (KEYS+LABELS вместе); читаются через `section_labels`.


def _pages_is_food_type(request) -> bool:
    """MEN-24a: гейт чекбокса маркировки — только гастро-типам (fail-closed)."""
    try:
        from apps.catalog.views import FOOD_BUSINESS_TYPES

        return getattr(request.tenant, "business_type", "") in FOOD_BUSINESS_TYPES
    except Exception:  # noqa: BLE001
        return False


@login_required
def pages_view(request):
    """M20U-7 «Pages»: per-page настройки витрины — раскладки сеток страниц
    каталога /sortiment/, номеров /unterkunft/ и списка событий /veranstaltung/.
    Сохранение мёржит в site_config, прочие настройки не затрагивая."""
    from apps.tenants import siteconfig

    if request.method == "POST":
        config = siteconfig.normalize(request.tenant.site_config)
        config["catalog_layout"] = {"preset": request.POST.get("catalog_preset", "")}
        # DS-7: тумблеры каталожного блока (сентинел cl_present — чужой POST не
        # роняет ключи, класс W0). Скрытие цен — только browse-only (PAngV);
        # при активном orders чекбокс не рендерится и ключ не трогаем.
        if request.POST.get("cl_present"):
            # KAT-1: тумблер category_landings умер (категория всегда страница).
            # MEN-24a: маркировка (диеты/аллергены) в прайс-листе — чекбокс
            # рендерится только FOOD-типам, но ключ пишем под общим сентинелом:
            # не-FOOD тип его и не включит (гейт витрины двойной).
            config["menu_labels"] = request.POST.get("menu_labels") == "on"
            from apps.core import modules as _modules

            if not _modules.is_module_active(request.tenant, "orders"):
                config["menu_show_prices"] = request.POST.get("menu_show_prices") == "on"
        config["detail_related_layout"] = {"preset": request.POST.get("related_preset", "")}
        # MEN-18 (фидбэк «не нашёл, где изменить вид услуг»): листинг услуг
        # настраивается и отсюда, не только с канвы. Семантика — как у канвы
        # (home_builder): пустой выбор «Standard» УДАЛЯЕТ ключ (легаси-грид),
        # сентинел присутствия — чужой POST ключ не трогает (класс W0).
        if "service_index_preset" in request.POST:
            svc_preset = request.POST.get("service_index_preset", "")
            if svc_preset:
                config["service_index_layout"] = {"preset": svc_preset}
            else:
                config.pop("service_index_layout", None)
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
        messages.success(request, _("Gespeichert."))
        return redirect("site-pages")

    config = siteconfig.normalize(request.tenant.site_config)
    preset_options = [
        ("list", _("List")),
        ("cols2", _("2 per row")),
        ("cols3", _("3 per row")),
        ("cols4", _("4 per row")),
        ("cols5", _("5 per row")),  # DS-6
        ("cols6", _("6 per row")),  # DS-6
        ("gallery", _("Gallery")),
    ]
    # MEN-18: прайс-виды листинга услуг (список / с фото / 2 колонки).
    service_preset_options = preset_options + [
        (key, siteconfig.SECTION_STYLE_LABELS.get(key, key))
        for key in siteconfig.PAGE_EXTRA_PRESETS["service_index_layout"]
    ]
    # DS-3a: страничные extra-виды каталога (прайс-листы) — только его пикер.
    # Ревью MEN-14/16: список был ЗАХАРДКОЖЕН и отстал на три новых вида —
    # сохранённый preisliste_buch не совпадал ни с одной опцией, браузер слал
    # первую («list») и Save молча откатывал вид (тот же класс, что DS-5c на
    # канве). Источник опций — реестр: новый вид появляется здесь сам.
    catalog_preset_options = preset_options + [
        (key, siteconfig.SECTION_STYLE_LABELS.get(key, key))
        for key in siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"]
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
            "catalog_preset_options": catalog_preset_options,  # DS-3a
            "catalog_preset": config["catalog_layout"]["preset"],
            # DS-7: текущие значения тумблеров каталожного блока.
            "menu_prices_on": config.get("menu_show_prices") is not False,
            "menu_labels_on": bool(config.get("menu_labels")),  # MEN-24a
            "is_food_type": _pages_is_food_type(request),  # MEN-24a: гейт чекбокса
            "orders_active_for_prices": modules.is_module_active(request.tenant, "orders"),
            "related_preset": config["detail_related_layout"]["preset"],
            "stay_index_preset": config["stay_index_layout"]["preset"],
            "events_index_preset": config["events_index_layout"]["preset"],
            # MEN-18: раскладка услуг (ключ presence-minimal: нет = «Standard»).
            "service_index_preset": config.get("service_index_layout", {}).get("preset", ""),
            "service_preset_options": service_preset_options,
            "event_sections": event_sections,
            # Показываем настройку страницы, только если её модуль активен.
            "has_catalog": modules.is_module_active(request.tenant, "catalog"),
            "has_stays": modules.is_module_active(request.tenant, "stays"),
            "has_events": modules.is_module_active(request.tenant, "events"),
            "has_booking": modules.is_module_active(request.tenant, "booking"),
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
        messages.success(request, _("Gespeichert."))
        return redirect("site-menu")

    from apps.tenants import menu as menu_mod

    tenant = request.tenant
    menus = siteconfig.normalize(tenant.site_config)["menus"]
    # Доступные цели для выпадашек редактора.
    archetype_targets = [
        {"value": s.key, "label": s.storefront_label or s.label_de}
        for s in modules.active_modules(tenant)
        if s.storefront_landing
    ]
    category_targets = []
    parent_targets = []
    if modules.is_module_active(tenant, "catalog"):
        from apps.catalog.models import Category

        # MEN-15: подпись — локализованное имя. Раньше в селект уезжал сырой
        # JSONField ({'de': 'Buffets'}), поэтому владелец выбирал цель вслепую.
        # Порядок — как в каталоге (sort_order), а не по строке словаря.
        cats = list(Category.objects.filter(is_active=True).order_by("sort_order", "slug"))
        roots = [c for c in cats if c.parent_id is None]
        kids = {}
        for c in cats:
            if c.parent_id is not None:
                kids.setdefault(c.parent_id, []).append(c)
        # Порядок селекта — как в каталоге: корневая, под ней её ветка с
        # отступами по уровню (плоский список вперемешку читался как случайный).
        # Ревью MEN-15: обход обязан покрыть ВСЕ живые категории. Первая версия
        # выводила только корни и их прямых детей — категория 3-го уровня и
        # активный ребёнок ВЫКЛЮЧЕННОГО родителя пропадали из селекта, и Save
        # молча переставлял такой пункт меню на первую опцию (класс W0).
        category_targets = []
        seen = set()

        def _walk(node, depth):
            if node.pk in seen:
                return
            seen.add(node.pk)
            prefix = "— " * depth
            category_targets.append(
                {"value": node.slug, "label": f"{prefix}{node.get_i18n('name')}"}
            )
            for child in kids.get(node.pk, []):
                _walk(child, depth + 1)

        for root in roots:
            _walk(root, 0)
        for cat in cats:  # осиротевшие ветки (родитель выключен/удалён) — в конце
            _walk(cat, 0)
        # Цели для узла «Kategorien»: пусто = корневые, иначе подкатегории этой.
        parent_targets = [
            {"value": "", "label": str(_("Alle Hauptkategorien"))},
        ] + [{"value": c.slug, "label": c.get_i18n("name")} for c in roots]
    # Аудит 2026-08-07: список был захардкожен как {home, about}, поэтому узел с
    # любой другой целью (Galerie/Bewertungen/Team/Treue/…) не находил себя в
    # селекте, браузер выбирал первый пункт, и после Save пункт вёл на главную.
    # Источник — реестр страниц меню: новая страница появляется здесь сама.
    page_targets = menu_mod.page_target_choices()
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
        "category_parents": parent_targets,
        "pages": page_targets,
        "promo_groups": promo_group_targets,
        "styles": list(siteconfig.NAV_STYLES),
    }
    return render(request, "tenant/site_menu.html", {"nav": "site", "builder": builder})


@login_required
def seo_settings_view(request):
    """SEO-2: кабинет мета-заготовок (title/description per-тип страницы).

    GET — редактор с текущими шаблонами, плейсхолдер-подсказки и live-превью
    Google-сниппета (JS). POST — сохранить в site_config["seo"]["templates"]
    (normalize сохраняет ключ через normalize_seo; движок seo_meta резолвит на
    витрине). Пустые поля → тип не пишется → архетип-дефолт (прогрессивность)."""
    import json

    from apps.core import seo_meta
    from apps.tenants import siteconfig

    if request.method == "POST":
        # W9-3: targeted-write ТОЛЬКО узла seo (normalize_seo валидирует его) —
        # пересборка полного конфига через normalize() из save-пути настроек
        # запрещена (класс W0/W6: терялись ключи соседних экранов).
        cfg = (
            dict(request.tenant.site_config) if isinstance(request.tenant.site_config, dict) else {}
        )
        templates = {}
        for pt in seo_meta.PAGE_TYPES:
            entry = {}
            title = (request.POST.get(f"title_{pt}") or "").strip()
            desc = (request.POST.get(f"desc_{pt}") or "").strip()
            if title:
                entry["title"] = title
            if desc:
                entry["description"] = desc
            if entry:
                templates[pt] = entry
        seo = {"templates": templates}
        # SEO-3b: чекбокс «ИИ-индексацию разрешить» снят → allow_ai=False (robots блокирует
        # AI-краулеров). Отмечен/дефолт → разрешено (ключ не пишем, golden-паритет).
        if request.POST.get("allow_ai") != "on":
            seo["allow_ai"] = False
        node = siteconfig.normalize_seo(seo)
        if node:
            cfg["seo"] = node
        else:
            cfg.pop("seo", None)  # presence-minimal: пусто → ключа нет
        request.tenant.site_config = cfg
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, _("Gespeichert."))
        return redirect("site-seo")

    tenant = request.tenant
    seo_cfg = siteconfig.normalize(tenant.site_config).get("seo") or {}
    saved = seo_cfg.get("templates") or {}
    allow_ai = seo_cfg.get("allow_ai") is not False  # дефолт True
    page_labels = {
        "home": _("Homepage"),
        "listing": _("Listings (catalog, rooms, events)"),
        "detail": _("Detail pages (product, service, room)"),
        "category": _("Category pages"),
    }
    # Пример-значения для превью per-тип (что подставляется на реальной странице).
    samples = {
        "home": {},
        "listing": {"heading": str(_("Sortiment"))},
        "detail": {"name": str(_("Bio-Honig 500 g"))},
        "category": {"category": str(_("Brot & Backwaren"))},
    }
    name = (tenant.name or "").strip()
    city = (getattr(tenant, "city", "") or "").strip()
    rows = []
    for pt in seo_meta.PAGE_TYPES:
        entry = saved.get(pt) or {}
        preview = seo_meta.resolve(tenant, pt, samples.get(pt))
        # sample для клиентского live-превью (те же значения, что даёт resolve).
        sample = {"tenant": name, "city": city, **samples.get(pt, {})}
        sample["tenant_sfx"] = f" · {name}" if name else ""
        sample["city_sfx"] = f" · {city}" if city else ""
        rows.append(
            {
                "key": pt,
                "label": page_labels.get(pt, pt),
                "title": entry.get("title", ""),
                "description": entry.get("description", ""),
                "default_title": seo_meta.DEFAULTS[pt]["title"],
                "default_desc": seo_meta.DEFAULTS[pt]["description"],
                "preview_title": preview["title"],
                "preview_desc": preview["description"],
                "sample_json": json.dumps(sample),
            }
        )
    return render(
        request,
        "tenant/site_seo.html",
        {
            # SM-4: свой nav-ключ — подсветка подпункта «SEO» раздела Website
            # (якорь мапится через site-хаб; раньше был общий "site").
            "nav": "seo",
            "rows": rows,
            "placeholders": ["{tenant}", "{city}", "{heading}", "{name}", "{category}"],
            "title_max": seo_meta.TITLE_MAX,
            "desc_max": seo_meta.DESC_MAX,
            "allow_ai": allow_ai,
        },
    )


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
            str(spec.label_de)
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
        messages.success(request, _("Gespeichert."))
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
        {
            "nav": "modules",
            "rows": recommended,
            "other_rows": other,
            "premium_rows": premium,
        },
    )


@login_required
def set_presence_view(request):
    """LS-2: режим присутствия «Jetzt erreichbar» (auto/on/off).

    Targeted-write: правит ТОЛЬКО ключ presence —
    остальной site_config цел. auto = отсутствие ключа (presence-minimal)."""
    tenant = request.tenant
    cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
    new_mode = request.POST.get("mode", "")
    if new_mode in ("on", "off"):
        cfg["presence"] = {"mode": new_mode}
    else:  # auto — дефолт, ключ убираем
        cfg.pop("presence", None)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    return redirect(_safe_dashboard_referer(request))


@login_required
@require_POST
def set_cabinet_lang_view(request):
    """T1 (FB-12): переключатель ЯЗЫКА КАБИНЕТА из шапки — пишет выбор в сессию
    (валидируется по CABINET_LANGUAGES), возвращает назад. Отдельно от языка витрины."""
    from apps.core.i18n_cabinet import set_cabinet_locale

    set_cabinet_locale(request, request.POST.get("lang", ""))
    return redirect(_safe_dashboard_referer(request))


def _safe_dashboard_referer(request):
    """Безопасный редирект назад: Referer, только если он свой (same-host) и под
    /dashboard/ — иначе на дашборд. Защита от open-redirect."""
    from urllib.parse import urlparse

    ref = request.META.get("HTTP_REFERER") or ""
    parsed = urlparse(ref)
    same_host = not parsed.netloc or parsed.netloc == request.get_host()
    if ref and same_host and parsed.path.startswith("/dashboard/"):
        return ref
    return "dashboard"


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


# --- U-D2: единая Kanban-доска транзакций ------------------------------------


@login_required
def verkaeufe(request):
    """Единая страница продаж (2026-08-03): вкладки по kind (primary всегда,
    прочие — при наличии продаж), в каждой — переключатель видов
    Kalender/Board/Liste. Переключение вкладки = обычная навигация `?tab=`
    (неактивные вкладки не запрашиваются вовсе)."""
    from django.urls import reverse

    from apps.core import sales_page

    tenant = request.tenant
    kinds = sales_page.visible_kinds(tenant) or ["order"]
    active = request.GET.get("tab", "")
    if active not in kinds:
        active = kinds[0]
    view = sales_page.resolve_view(tenant, active, request.GET.get("view", ""))
    # W10-4: kind-агностичный вид «Heute» (?view=heute) — не персистится и не
    # входит в KIND_VIEWS (переключатель видов остаётся per-kind).
    if request.GET.get("view") == "heute":
        view = "heute"
    # W10-3: «＋» из любого вида — цель создания по kind (есть только у
    # календарных движков: walk-in формы живут в их телах/на stay-new).
    create_target = ""
    if active == "stay":
        create_target = reverse("stays:stay-new")
    elif active == "booking":
        create_target = reverse("verkaeufe") + "?tab=booking&view=kalender#neu"
    elif active == "job":
        create_target = reverse("jobs:new")  # X2c: ручная заявка (звонок/визит)
    ctx = {
        "nav": "board",
        "sales_tabs": sales_page.tab_descriptors(tenant, active),
        "sales_views": sales_page.view_descriptors(tenant, active, view),
        "active_kind": active,
        "active_view": view,
        "create_target": create_target,
    }
    # X3: тело поверхности строит ОБЩАЯ функция — её же зовёт главная кабинета
    # (одна петля архетипа, один источник контекста).
    sub = sales_page.body_context(request, active, view)
    if not isinstance(sub, dict):  # ?box=1 — fetch-фрагмент карточки брони
        return sub
    ctx = {**sub, **ctx}
    return render(request, "core/verkaeufe.html", ctx)


@login_required
def verkaeufe_view_set(request):
    """Persist выбранного вида вкладки (targeted-write `sales_views[kind]`)."""
    from django.http import HttpResponseNotAllowed

    from apps.core.sales_page import KIND_VIEWS

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    kind = request.POST.get("kind", "")
    view = request.POST.get("view", "")
    if view in KIND_VIEWS.get(kind, ()):
        tenant = request.tenant
        cfg = dict(tenant.site_config or {})
        sv = dict(cfg.get("sales_views") or {})
        sv[kind] = view
        cfg["sales_views"] = sv
        tenant.site_config = cfg
        tenant.save(update_fields=["site_config"])
    from django.urls import reverse

    # W10-1: возврат на ПОЛНЫЙ исходный путь (next=, только внутренний) — иначе
    # переключение вида сбрасывало ?von=/?tag=/?q=/?buchung= (аудит 2026-08-05).
    nxt = request.POST.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(reverse("verkaeufe") + f"?tab={kind}")


def _board_stage_rows(tenant):
    """W5: строки панели «Spalten anpassen» (переименование/порядок/скрытие) —
    общие для доски и экрана «Abläufe» (W9-8)."""
    from apps.core import pipeline
    from apps.tenants import siteconfig

    board_cfg = siteconfig.normalize_board((tenant.site_config or {}).get("board"))
    labels = board_cfg.get("labels", {})
    hidden = set(board_cfg.get("hidden", []))
    order = board_cfg.get("order") or list(pipeline.STAGES)
    order = order + [s for s in pipeline.STAGES if s not in order]
    return [
        {
            "stage": s,
            "default_label": str(pipeline.STAGE_LABELS[s]),
            "label": labels.get(s, ""),
            "hidden": s in hidden,
            "pos": i + 1,
        }
        for i, s in enumerate(order)
    ]


def _status_kinds_for(tenant):
    """Активные kind'ы с настраиваемыми статусами: [(kind, label)].

    SM-2 (2026-08-10): паритет всем шести направлениям — имена статусов и
    правила переходов настраиваются у каждого модуля продаж, не только у
    order/booking/stay."""
    from apps.core import transactions

    _kind_modules = (
        ("order", "orders"),
        ("booking", "booking"),
        ("stay", "stays"),
        ("job", "jobs"),
        ("ticket", "events"),
        ("reservation", "promotions"),
    )
    return [
        (k, transactions.KIND_LABEL.get(k, k))
        for k, m in _kind_modules
        if tenant.is_module_active(m)
    ]


@login_required
def board(request):
    """X2b: легаси-доска снесена → 302 на единую страницу продаж (W10-6, GET-carry).

    Ссылок из шаблонов на неё не было уже с X0 («Full view» ведёт в Verkäufe);
    доска оставалась третьей поверхностью продаж с собственными вкладками и
    панелью колонок. Паритет достигнут: канбан — вид вкладки Verkäufe, панель
    «⚙️ Spalten» и настройки статусов живут на «Abläufe» (W9-8).
    Семантика параметра: доска знала `?kind=`, единая страница — `?tab=`.
    """
    from apps.core import sales_page

    params = {"kind": None}  # старый ключ не тащим в новый адрес
    kind = request.GET.get("kind", "")
    if kind:
        params["tab"] = kind
    return sales_page.legacy_redirect(request, **params)


@login_required
@require_POST
def board_settings(request):
    """W5: сохранить настройки Kanban-доски (переименование/порядок/скрытие колонок)
    в site_config['board']. Правила переходов (FSM) НЕ трогаем (V4). Targeted-write
    — прочие ключи site_config целы."""
    from apps.core import pipeline
    from apps.tenants import siteconfig

    tenant = request.tenant
    labels, hidden, order_pairs = {}, [], []
    for stage in pipeline.STAGES:
        lbl = (request.POST.get(f"label_{stage}") or "").strip()
        if lbl:
            labels[stage] = lbl
        if request.POST.get(f"hidden_{stage}"):
            hidden.append(stage)
        try:
            pos = int(request.POST.get(f"order_{stage}", ""))
        except (TypeError, ValueError):
            pos = 999
        order_pairs.append((pos, stage))
    order = [s for _, s in sorted(order_pairs, key=lambda p: p[0])]
    board_in = {"labels": labels, "hidden": hidden}
    if order != list(pipeline.STAGES):  # дефолтный порядок не материализуем
        board_in["order"] = order
    board = siteconfig.normalize_board(board_in)
    cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
    if board:
        cfg["board"] = board
    else:
        cfg.pop("board", None)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, _("Gespeichert."))
    # W9-8: панель колонок теперь и на «Abläufe» — next= возвращает туда (только
    # внутренний путь; паттерн status_labels_save).
    nxt = request.POST.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    # X2b: доска снесена — панель колонок живёт на «Abläufe» (W9-8).
    return redirect("ablaeufe")


@login_required
@require_POST
def kanban_action(request, kind, pk):
    """UD2-2: применить FSM-переход к транзакции с доски (drag-drop / кнопка).

    Единая точка: резолвит модель+FSM по kind и зовёт SM().apply(target) — тот
    же путь, что per-app экраны (revenue/письма/склад на on_transition, без
    дублей; src==dst — no-op). IllegalTransition → 409 (fetch: клиент откатывает
    карточку) либо сообщение+redirect (обычный POST). Успех fetch → перерисованная
    карточка (свежие бейдж/кнопки, остаётся в новой колонке)."""
    from django.http import HttpResponse, HttpResponseBadRequest
    from django.urls import reverse

    from apps.core import transactions
    from apps.core.fsm import IllegalTransition

    if kind not in transactions.TRANSACTION_KINDS:
        return HttpResponseBadRequest("unknown kind")
    obj = get_object_or_404(transactions.model_for(kind), pk=pk)
    target = request.POST.get("action", "")
    is_fetch = request.headers.get("X-Requested-With") == "fetch"
    # W7c: тот же канбан встроен на главную и Verkäufe — non-fetch POST (без JS/
    # сбой fetch) возвращаемся на исходную поверхность (только внутренний путь),
    # а не выбрасываем владельца на легаси /dashboard/board/.
    back = request.POST.get("next", "")
    if not (back.startswith("/") and not back.startswith("//")):
        # X2b: доска снесена — возвращаемся во вкладку единой страницы продаж.
        back = reverse("verkaeufe") + f"?tab={kind}"
    try:
        # W10-5: единая точка — спец-поля поверхности (tracking_code при
        # «Versendet» заказа-доставки) едут в extra и пишутся ДО apply.
        transactions.apply_action(kind, obj, target, actor=request.user, extra=request.POST)
    except IllegalTransition:
        if is_fetch:
            return HttpResponse(status=409)
        messages.error(request, _("Dieser Schritt ist im aktuellen Status nicht möglich."))
        return redirect(back)
    obj.refresh_from_db()
    # FB-4a/b имена + FB-3 правила переходов — на перерисованной карточке (доска кабинета).
    from apps.core import status_labels, transition_rules

    tenant = getattr(request, "tenant", None)
    tx = transactions.transaction_for(
        kind,
        obj,
        status_labels.custom_labels(tenant, kind),
        transition_rules.subset_for(tenant, kind),
    )
    if is_fetch:
        # kanban_next: сохранить исходный next в перерисованной карточке (иначе
        # hidden-поле указывало бы на URL самого action-эндпоинта).
        return render(
            request,
            "core/_kanban_card.html",
            {"tx": tx, "kind": kind, "kanban_next": request.POST.get("next", "")},
        )
    return redirect(back)


@login_required
@require_POST
def status_labels_save(request, kind):
    """FB-4a/FB-4b: сохранить свои имена статусов (order/booking/stay) — кабинет-
    отображение. Targeted-write в site_config['status_labels'][kind]; FSM/переходы/
    письма/витрину не трогаем. `next` (локальный путь) — куда вернуться."""
    from django.http import Http404
    from django.urls import reverse

    from apps.core import status_labels
    from apps.tenants import siteconfig

    statuses = siteconfig.status_label_statuses(kind)
    if statuses is None:
        raise Http404("unknown status kind")
    status_labels.save_labels(request.tenant, kind, statuses, request)
    messages.success(request, _("Gespeichert."))
    nxt = request.POST.get("next", "")
    if not nxt.startswith("/"):
        nxt = reverse("ablaeufe")  # X2b: доска снесена — настройки статусов там
    return redirect(nxt)


@login_required
@require_POST
def transitions_save(request, kind):
    """FB-3: сохранить правила переходов статусов (order/booking/stay) — какие уже-легальные
    не-danger переходы показывать. FSM/apply()/побочки/письма НЕ трогаем (жёсткий пол);
    danger/отмена не прячется. `next` (локальный путь) — куда вернуться."""
    from django.http import Http404
    from django.urls import reverse

    from apps.core import transition_rules
    from apps.tenants import siteconfig

    if siteconfig.status_label_statuses(kind) is None:
        raise Http404("unknown status kind")
    transition_rules.save(request.tenant, kind, request)
    messages.success(request, _("Gespeichert."))
    nxt = request.POST.get("next", "")
    if not nxt.startswith("/"):
        nxt = reverse("ablaeufe")  # X2b: доска снесена — правила переходов там
    return redirect(nxt)


@login_required
def ablaeufe_view(request):
    """W9-8: «Abläufe» — настройки процессов продаж в ОДНОМ месте: имена статусов
    (FB-4a/b), правила переходов (FB-3), свои статусы (status-manager) и колонки
    доски (W5). Раньше панели были разбросаны (список заказов/ресурсы booking, у
    stays — мёртвый контекст) — аудит 2026-08-05. Сохранение — прежние эндпоинты
    (status-labels-save/transitions-save/board-settings) через next= сюда."""
    from apps.core import status_labels, transition_rules
    from apps.tenants import siteconfig

    tenant = request.tenant
    kinds = _status_kinds_for(tenant)
    active = request.GET.get("kind", "")
    if active not in [k for k, _label in kinds]:
        active = kinds[0][0] if kinds else ""
    label_rows, transition_rows = [], []
    if active:
        label_rows = status_labels.label_rows(tenant, active, _status_choices(active))
        transition_rows = transition_rules.editor_rows(tenant, active)
    # X5-3 (план x5-settings §2): «Abläufe» — ОДНА страница с двумя входами.
    # Заход из подпункта «Verkäufe» раньше телепортировал: подсвечивался якорь
    # «Einstellungen» и рисовался таб-бар настроек. С ?from=board страница
    # остаётся в контексте продаж (хлебная крошка вместо табов).
    from_board = request.GET.get("from") == "board"
    ctx = {
        "nav": "ablaeufe",
        "kinds": kinds,
        "active_kind": active,
        "status_label_rows": label_rows,
        "transition_rows": transition_rows,
        "board_stage_rows": _board_stage_rows(tenant),
        "from_board": from_board,
        # X2c: настройки публичной формы заявки жили на легаси-странице заявок
        # (которая схлопывается) — их место в «Abläufe» (процессы продаж).
        "anfrage_enabled": tenant.is_module_active("jobs"),
        "anfrage_cfg": (siteconfig.normalize(tenant.site_config).get("anfrage") or {}),
    }
    if from_board:
        ctx["nav_anchor_override"] = "board"
    return render(request, "tenant/ablaeufe.html", ctx)


def _status_choices(kind):
    """Дефолт-choices статусов kind для панели имён (ленивые импорты моделей)."""
    if kind == "order":
        from apps.orders.models import Order

        return Order.STATUSES
    if kind == "booking":
        from apps.booking.models import Booking

        return Booking.STATUSES
    if kind == "job":
        from apps.jobs.models import Job

        return Job.STATUSES
    if kind == "ticket":
        from apps.events.models import Ticket

        return Ticket.STATUSES
    if kind == "reservation":
        # У Reservation модельных choices нет (UD1) — подписи из реестра ролей.
        return [
            ("pending", _("Offen")),
            ("confirmed", _("Bestätigt")),
            ("fulfilled", _("Eingelöst")),
            ("cancelled", _("Storniert")),
            ("expired", _("Abgelaufen")),
        ]
    from apps.stays.models import StayBooking

    return StayBooking.STATUSES


def _set_status_config(cfg, top_key, kind, value):
    """Targeted-write cfg[top_key][kind]=value, presence-minimal (пустое снимает ключ)."""
    node = dict(cfg.get(top_key) or {})
    if value:
        node[kind] = value
    else:
        node.pop(kind, None)
    if node:
        cfg[top_key] = node
    else:
        cfg.pop(top_key, None)


@login_required
def status_manager(request, kind):
    """FB-3 Вариант B Phase 5 (+SM-3: все шесть направлений): редактор своих
    статусов + переходов. Владелец выбирает роль — стадия/поведение следуют;
    переходы — чекбоксами."""
    from django.http import Http404

    from apps.core import status_registry, transactions
    from apps.tenants import siteconfig

    if siteconfig.status_label_statuses(kind) is None:
        raise Http404("unknown status kind")
    tenant = request.tenant
    builtin = status_registry.descriptors(kind)
    custom = status_registry.custom_descriptors(tenant, kind)
    edges = status_registry.custom_edges(tenant, kind)
    blabels = transactions.builtin_status_labels(kind)

    def label_of(code):
        d = custom.get(code)
        return d.label if d else blabels.get(code, code)

    def role_of(code):
        d = builtin.get(code) or custom.get(code)
        return d.role if d else ""

    all_codes = list(builtin) + list(custom)
    trans_rows = []
    for c, d in custom.items():
        # SM-3: рёбер ИЗ cancelled-роли не бывает (терминальный статус терминален,
        # как в builtin-графе; слой чтения custom_edges их отбросит) → источником
        # не предлагаем отменённые, а у cancel-роли кастома нет блока «Führt zu».
        # Молчаливо-мёртвая галочка хуже отсутствующей.
        sources = [
            {"code": o, "label": label_of(o), "checked": (o, c) in edges}
            for o in all_codes
            if o != c and role_of(o) != "cancelled"
        ]
        targets = (
            [
                {"code": o, "label": label_of(o), "checked": (c, o) in edges}
                for o in all_codes
                if o != c
            ]
            if d.role != "cancelled"
            else []
        )
        trans_rows.append({"code": c, "label": d.label, "sources": sources, "targets": targets})
    return render(
        request,
        "tenant/status_manager.html",
        {
            "nav": "board",
            "kind": kind,
            "kind_label": transactions.KIND_LABEL.get(kind, kind),
            "roles": [(r, status_registry.ROLE_LABELS[r]) for r in status_registry.ROLES],
            "custom_rows": [
                {"code": c, "label": d.label, "role": d.role} for c, d in custom.items()
            ],
            "trans_rows": trans_rows,
            "next": request.GET.get("next", ""),
        },
    )


@login_required
@require_POST
def status_manager_save(request, kind):
    """FB-3 Вариант B Phase 5 (+SM-3): сохранить свои статусы (def_from_role) + переходы.
    Targeted-write status_defs/status_edges; normalize + presence-minimal. FSM built-in
    не трогаем. Существующий код с НЕИЗМЕНЁННОЙ ролью сохраняет свой деф (продвинутые
    флаги вроде counts_in_reports, выставленные через site_config, не слетают)."""
    from django.http import Http404
    from django.urls import reverse

    from apps.core import status_registry
    from apps.tenants import siteconfig

    if siteconfig.status_label_statuses(kind) is None:
        raise Http404("unknown status kind")
    tenant = request.tenant
    builtin_codes = set(status_registry.descriptors(kind))
    cfg_now = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    stored = {
        d["code"]: d
        for d in siteconfig.normalize_status_defs(cfg_now.get("status_defs")).get(kind, [])
    }

    def _slug(v):
        # SM-3: кламп 20 = max_length поля status (согласован с normalize)
        return re.sub(r"[^a-z0-9_]+", "_", (v or "").strip().lower()).strip("_")[:20]

    defs, seen = [], set()
    for code in request.POST.getlist("custom_code"):
        if request.POST.get(f"del_{code}"):
            continue
        label = (request.POST.get(f"label_{code}") or "").strip()[:40]
        role = request.POST.get(f"role_{code}") or "active"
        if code and label and code not in seen:
            seen.add(code)
            old = stored.get(code)
            if old is not None and old.get("role") == role:
                defs.append({**old, "label": label})  # роль та же → флаги целы
            else:
                defs.append(status_registry.def_from_role(code, label, role, kind=kind))
    new_label = (request.POST.get("new_label") or "").strip()[:40]
    if new_label:
        new_code = _slug(new_label)
        if new_code and new_code not in builtin_codes and new_code not in seen:
            defs.append(
                status_registry.def_from_role(
                    new_code, new_label, request.POST.get("new_role") or "active", kind=kind
                )
            )
            seen.add(new_code)

    valid_defs = siteconfig.normalize_status_defs({kind: defs}).get(kind, [])
    valid_codes = {d["code"] for d in valid_defs}
    known = builtin_codes | valid_codes
    edges = []
    for val in request.POST.getlist("edge"):
        if "|" not in val:
            continue
        src, dst = val.split("|", 1)
        # SM-3: рёбра ИЗ cancelled-роли не сохраняем (слой чтения их отбросил бы —
        # мёртвый конфиг); роль src: builtin-дескриптор или только что валидированный деф.
        src_desc = status_registry.descriptors(kind).get(src)
        src_role = (
            src_desc.role
            if src_desc
            else next((d["role"] for d in valid_defs if d["code"] == src), "")
        )
        if (
            src in known
            and dst in known
            and src != dst
            and (src in valid_codes or dst in valid_codes)
            and src_role != "cancelled"
        ):
            edges.append({"src": src, "dst": dst})
    valid_edges = siteconfig.normalize_status_edges({kind: edges}).get(kind, [])

    cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
    _set_status_config(cfg, "status_defs", kind, valid_defs)
    _set_status_config(cfg, "status_edges", kind, valid_edges)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, _("Gespeichert."))
    nxt = request.POST.get("next", "")
    if not nxt.startswith("/"):
        nxt = reverse("status-manager", args=[kind])
    return redirect(nxt)


# --- FB-8: единый обзор продаваемых сущностей --------------------------------


@login_required
def sellable_manage(request):
    """FB-8: «Angebote» — один экран со всеми продаваемыми сущностями (товар/услуга/
    номер/событие/комбо): обзор + видимость + переход к РОДНОЙ форме. Единый CRUD НЕ
    делаем — родные формы остаются авторитетными."""
    from apps.core import sellable_manage as sm

    tenant = request.tenant
    # X6-2: поиск по всем продаваемым сущностям сразу (владелец ищет по имени,
    # не зная kind). Пустой q = прежний обзор.
    q = (request.GET.get("q") or "").strip()
    return render(
        request,
        "tenant/sellable_manage.html",
        {
            "nav": "sellables",
            "q": q,
            "sections": sm.sellable_manage_sections_for(tenant, q=q),
            "add_options": sm.add_options(tenant),
            # W11-4: гейт кнопки «% Aktion» на карточках (цель PL из строки).
            "promotions_active": tenant.is_module_active("promotions"),
            # ST-5a: карточный грид.
            # Во вьюхе (не processor) — как dashboard: работает и на public-схеме.
        },
    )


@login_required
@require_POST
def sellable_visibility(request, kind, pk):
    """FB-8: тумблер видимости сущности (is_active) — product/service/stay/combo. Event
    публикуется через FSM (draft↔published) на своей форме → сюда не приходит."""
    from apps.core import sellable_manage as sm

    obj = sm.toggle_visibility(kind, pk)
    messages.success(
        request, _("Sichtbar.") if getattr(obj, "is_active", False) else _("Ausgeblendet.")
    )
    return redirect("sellable-manage")


# --- U-D4: настройки каналов уведомлений (email ∥ Telegram) -------------------


@login_required
def notifications_settings(request):
    """UD4-2: матрица каналов per-событие (клиент) + owner-каналы + привязка
    Telegram владельца. Хранение — Tenant.site_config['notify'] (без миграции);
    owner_chat_id/owner_link_token в том же узле НЕ затираем при сохранении."""
    from apps.notifications import prefs
    from apps.telegram.notify import (
        _notify_node,
        _save_notify_node,
        active_bot,
        owner_chat_id,
        owner_deep_link,
    )

    tenant = request.tenant
    if request.method == "POST":
        if request.POST.get("action") == "disconnect_owner":
            node = dict(_notify_node(tenant))
            node.pop("owner_chat_id", None)
            _save_notify_node(tenant, node)
            messages.success(request, _("Telegram getrennt."))
            return redirect("notifications-settings")
        cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
        node = dict(cfg.get("notify")) if isinstance(cfg.get("notify"), dict) else {}
        customer = {}
        for domain, events in prefs.CUSTOMER_EVENTS.items():
            if not tenant.is_module_active(prefs.DOMAIN_MODULE[domain]):
                continue
            for event, _label in events:
                customer[f"{domain}:{event}"] = {
                    "email": bool(request.POST.get(f"c-{domain}-{event}-email")),
                    "telegram": bool(request.POST.get(f"c-{domain}-{event}-telegram")),
                }
        # W7a: мержим, а не заменяем — строки временно выключенных модулей не были
        # в форме, и их выбор должен пережить Save (иначе включение модуля обратно
        # тихо вернёт письма, которые владелец отключал).
        merged = dict(node.get("customer")) if isinstance(node.get("customer"), dict) else {}
        merged.update(customer)
        node["customer"] = merged
        node["owner"] = {
            "email": bool(request.POST.get("o-email")),
            "telegram": bool(request.POST.get("o-telegram")),
        }
        cfg["notify"] = node
        tenant.site_config = cfg
        tenant.save(update_fields=["site_config"])
        messages.success(request, _("Benachrichtigungen gespeichert."))
        return redirect("notifications-settings")

    return render(
        request,
        "tenant/notifications.html",
        {
            "nav": "notifications",
            "matrix": prefs.customer_matrix(tenant),
            "owner": prefs.owner_channels(tenant),
            "owner_deep_link": owner_deep_link(tenant),
            "owner_linked": bool(owner_chat_id(tenant)),
            # FB-10: КУДА идут owner-письма (и предупреждение, если адрес пуст —
            # частая причина «уведомления не приходят»).
            "owner_email": tenant.owner_email,
            # W9-7: read-only статус бизнес-бота — Telegram-строки матрицы бессмысленны
            # без активного бота, владелец должен видеть это ЗДЕСЬ, не гадая.
            "bot": active_bot(),
        },
    )


@login_required
def marketing_home(request):
    """ST-6a: Marketing-центр — лендинг с карточками в ROI-порядке ТЗ, read-only
    обзором авто-напоминаний и панелью результатов (готовые источники, только
    чтение). Новая страница (ничего не заменяет)
    (прецедент integrations_home)."""
    from apps.core import marketing_home as mh

    tenant = request.tenant

    def _unread():
        # X0: непрочитанные треды — первой карточкой (бейдж якоря ведёт сюда).
        if not tenant.is_module_active("inbox"):
            return 0
        from apps.inbox.models import Conversation

        return Conversation.objects.filter(unread_for_staff=True).count()

    try:
        inbox_unread = _unread()
    except Exception:  # noqa: BLE001 — карточка сообщений не валит лендинг (_safe-паттерн)
        inbox_unread = 0
    return render(
        request,
        "tenant/marketing_home.html",
        {
            "nav": "promotions",
            "cards": mh.cards(tenant),
            "reminders": mh.reminder_overview(tenant),
            "metrics": mh.results_panel(tenant),
            "inbox_unread": inbox_unread,
        },
    )


def _google_rating_status(tenant):
    """GK-11: ok = кэш есть; warn = ID задан, но ещё не обновлялось; muted = выкл."""
    if not tenant.google_place_id:
        return (_("Nicht verbunden"), "muted")
    if tenant.google_rating is None:
        return (_("Wartet auf erste Aktualisierung"), "warn")
    return (f"★ {tenant.google_rating} · {tenant.google_rating_count}", "ok")


@login_required
def palette_search(request):
    """X8: JSON-поиск по ДАННЫМ для палитры Ctrl+K (сделки/клиенты/предложения).

    `@login_required` обязателен (класс дефектов X0: без него данные бизнеса
    читал бы аноним — Membership-гейт мидлвари анонима не трогает). Источники
    и их модульные гейты — `apps.core.palette_search`."""
    from django.http import JsonResponse

    from apps.core import palette_search as ps

    sections = ps.search(request.tenant, request.GET.get("q", ""))
    return JsonResponse(
        {
            "sections": [
                {"key": sec["key"], "label": str(sec["label"]), "items": sec["items"]}
                for sec in sections
            ]
        }
    )


@login_required
def integrations_home(request):
    """ST-4a → W9-9 (Р-3): «Integrationen» — вкладка Einstellungen-хаба с
    read-only статусами подключений на карточках (fail-safe: сломанный блок
    не валит экран — паттерн _safe ST-4a). Сами подключения настраиваются
    на целевых экранах; здесь только вход + честное состояние."""
    from django.conf import settings as dj_settings

    from apps.telegram.notify import active_bot, owner_chat_id

    def _safe(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 — статус одного блока не валит лендинг
            return ("", "muted")

    tenant = request.tenant

    def _stripe_status():
        if getattr(tenant, "payments_enabled", False):
            return (_("Stripe verbunden"), "ok")
        if getattr(tenant, "vorkasse_enabled", False):
            return (_("Vorkasse aktiv — Stripe nicht verbunden"), "warn")
        return (_("Nicht verbunden"), "muted")

    def _telegram_status():
        # console-бэкенд = письма НЕ уходят наружу (Stage 0 честно на виду).
        if "console" in (getattr(dj_settings, "EMAIL_BACKEND", "") or "").lower():
            return (_("E-Mail: Test-Modus (Konsole) — Mails gehen nicht raus"), "warn")
        bot = active_bot()
        if bot is None:
            return (_("Kein Telegram-Bot"), "muted")
        # I18N-7b: gettext НЕ в f-строке (xgettext их не извлекает).
        label = _("Bot aktiv")
        if bot.bot_username:
            label = f"{label} · @{bot.bot_username}"
        if owner_chat_id(tenant):
            linked = _("Inhaber verbunden")
            label = f"{label} · {linked}"
        return (label, "ok")

    def _domain_status():
        doms = list(tenant.custom_domains.all()[:5])
        active = next((d for d in doms if d.is_active), None)
        if active is not None:
            return (active.domain, "ok")
        if any(d.status == d.PENDING for d in doms):
            return (_("Prüfung ausstehend"), "warn")
        return (_("Keine eigene Domain"), "muted")

    def _publishing_status():
        from apps.publishing.models import Channel as PubChannel

        n = PubChannel.objects.filter(is_enabled=True).exclude(type=PubChannel.LOG).count()
        if n:
            lbl = _("Verbunden:")
            return (f"{lbl} {n}", "ok")
        return (_("Keine Kanäle verbunden"), "muted")

    def _ota_status():
        from apps.stays.models import Channel as OtaChannel

        n = OtaChannel.objects.count()
        if n:
            lbl = _("Verbunden:")
            return (f"{lbl} {n}", "ok")
        return (_("Keine Kanäle verbunden"), "muted")

    cards = [
        {
            "icon": "💳",
            "label": _("Zahlung & Stripe"),
            "hint": _("Online-Zahlung, Vorkasse, Zahlarten"),
            "url_name": "payment-settings",
            "show": True,
            "status": _safe(_stripe_status),
        },
        {
            "icon": "📨",
            "label": _("Benachrichtigungen & Telegram"),
            "hint": _("E-Mail/Telegram-Kanäle, Telegram verbinden"),
            "url_name": "notifications-settings",
            "show": True,
            "status": _safe(_telegram_status),
        },
        {
            "icon": "🌐",
            "label": _("Eigene Domain"),
            "hint": _("Custom-Domain verbinden"),
            "url_name": "domains",
            "show": True,
            "status": _safe(_domain_status),
        },
        {
            "icon": "📣",
            "label": _("Publishing (Google/Facebook/Instagram)"),
            "hint": _("Kanäle verbinden und Beiträge planen"),
            "url_name": "channels",
            "show": tenant.is_module_active("publishing"),
            "status": _safe(_publishing_status),
        },
        {
            # GK-11: Google-рейтинг (Places API) — плашка «★ X,X · N Google-
            # Bewertungen» на витрине; ключ платформенный (env/секрет-стор).
            "icon": "⭐",
            "label": _("Google Bewertungen"),
            "hint": _("Bewertung und Anzahl von Google auf der Website anzeigen"),
            "url_name": "google-reviews-settings",
            "show": True,
            "status": _safe(lambda: _google_rating_status(tenant)),
        },
        {
            "icon": "🏨",
            "label": _("Channel Manager (OTA)"),
            "hint": _("Buchungen aus Portalen importieren"),
            "url_name": "stays:channels",
            "show": tenant.is_module_active("stays"),
            "status": _safe(_ota_status),
        },
    ]
    return render(
        request,
        "tenant/integrations_home.html",
        # nav-ключ прежний — подсветку на якорь «Einstellungen» ведёт реестр W8.
        {"nav": "integrations", "cards": [c for c in cards if c["show"]]},
    )


@login_required
def google_reviews_settings(request):
    """GK-11: Place ID + кэш Google-рейтинга. Targeted-save (W7a: голый save()
    затирал бы конкурентные записи site_config/Stripe); «Jetzt aktualisieren» —
    синхронный fetch с честной ошибкой (без ключа/битый ID)."""
    from apps.tenants import google_places
    from apps.tenants.forms import GoogleRatingForm

    tenant = request.tenant
    form = GoogleRatingForm(request.POST or None, instance=tenant)
    if request.method == "POST":
        if request.POST.get("action") == "refresh" and tenant.google_place_id:
            try:
                rating, count = google_places.fetch_rating(tenant.google_place_id)
            except Exception:
                messages.error(
                    request,
                    _(
                        "Aktualisierung fehlgeschlagen — Place ID prüfen; "
                        "der Plattform-API-Schlüssel muss konfiguriert sein."
                    ),
                )
            else:
                tenant.google_rating = rating
                tenant.google_rating_count = count
                tenant.google_rating_updated_at = timezone.now()
                tenant.save(
                    update_fields=[
                        "google_rating",
                        "google_rating_count",
                        "google_rating_updated_at",
                        "updated_at",
                    ]
                )
                messages.success(request, _("Aktualisiert."))
            return redirect("google-reviews-settings")
        if form.is_valid():
            form.save(commit=False)
            tenant.save(update_fields=[*GoogleRatingForm.Meta.fields, "updated_at"])
            messages.success(request, _("Gespeichert."))
            return redirect("google-reviews-settings")
    return render(
        request, "tenant/google_reviews_settings.html", {"nav": "integrations", "form": form}
    )
