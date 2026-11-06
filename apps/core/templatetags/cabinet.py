"""Шаблонные теги кабинета (AB1 язык задач + анти-Битрикс v2 хаб-табы)."""

import logging

from django import template
from django.utils.translation import gettext_lazy as _

from apps.core import nav_registry, packages

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def stats_text(rows):
    """GK-4: rows полосы цифр → textarea «wert | label» (обратный парс — normalize)."""
    from apps.tenants import siteconfig

    return siteconfig.stats_to_text(rows)


@register.simple_tag(takes_context=True)
def status_label(context, obj, kind="order"):
    """FB-4a: имя статуса в кабинете — своё имя владельца (site_config["status_labels"])
    или дефолт. FB-3 Вариант B Phase 6: для КАСТОМ-статуса дефолт = его label (иначе
    get_status_display вернул бы код). FSM/письма/витрину не трогает."""
    return _status_label(getattr(context.get("request"), "tenant", None), obj, kind)


# KA-12 E9.1: тон бейджа = РОЛЬ статуса (решение владельца по макету «Kabinett-Bausteine»):
# «Bestätigt» одного цвета у записи, номера и заказа; кастом-статус — тон своей роли.
# Тон `run` (ui-tone-run) ролям не назначается — его ставят экраны напрямую (info-плашки).
ROLE_TONES = {"intake": "new", "active": "ok", "done": "done", "cancelled": "bad"}


def tone_for(kind, status, tenant=None) -> str:
    """Тон бейджа (kind, status); неизвестный kind/код — нейтральный `off`, без исключения."""
    from apps.core import status_registry

    try:
        d = status_registry.resolve(kind, status, tenant)
    except (AttributeError, TypeError):
        # Кривой status_defs (не-dict запись) или нехэшируемый код — бейдж нейтральный,
        # страница не падает; след в логе, чтобы не прятать настоящий баг.
        logger.debug("status tone fallback for %r/%r", kind, status, exc_info=True)
        d = None
    return ROLE_TONES.get(getattr(d, "role", None), "off")


@register.simple_tag(takes_context=True)
def status_tone(context, kind, status):
    """`{% status_tone "booking" b.status %}` → «ui-tone-ok» (класс для своей разметки)."""
    tenant_obj = getattr(context.get("request"), "tenant", None)
    return f"ui-tone-{tone_for(kind, status, tenant_obj)}"


@register.simple_tag(takes_context=True)
def status_badge(context, obj, kind="order"):
    """`{% status_badge b "booking" %}` → готовый бейдж: тон по роли + подпись владельца."""
    from django.utils.html import format_html

    tenant_obj = getattr(context.get("request"), "tenant", None)
    return format_html(
        '<span class="ui-badge ui-tone-{}">{}</span>',
        tone_for(kind, obj.status, tenant_obj),
        _status_label(tenant_obj, obj, kind),
    )


def _status_label(tenant_obj, obj, kind):
    from apps.core import status_registry

    d = status_registry.resolve(kind, obj.status, tenant_obj)
    if d is not None and not d.builtin and d.label:
        default = d.label
    elif hasattr(obj, "get_status_display"):
        default = obj.get_status_display()
    else:
        # SM-3: у Reservation choices нет — словарь builtin-подписей, не сырой код.
        from apps.core import transactions

        default = transactions.builtin_status_labels(kind).get(obj.status, str(obj.status))
    cfg = getattr(tenant_obj, "site_config", None)
    if not isinstance(cfg, dict):
        return default
    labels = cfg.get("status_labels")
    if not isinstance(labels, dict):
        return default
    node = labels.get(kind)
    if not isinstance(node, dict):
        return default
    return node.get(obj.status) or default


# S1/S2/S3 → W8: реестр навигации живёт в apps/core/nav_registry.py (ЕДИНЫЙ
# источник: якоря, подменю сайдбара, подсветка, палитра). HUB_TABS — производная
# в прежней форме кортежей (url_name, label, nav_key, module_key, advanced);
# R7-1: сам ТЕГ hub_tabs снесён — таб-бары на страницах дублировали подменю
# сайдбара (фидбэк владельца 2026-08-24), меню осталось одно.
HUB_TABS = nav_registry.legacy_hub_tabs()


@register.simple_tag(takes_context=True)
def query_with(context, key, value=""):
    """KA-12 E2.9: текущий GET с заменённым `key` (пусто — убрать); номер
    страницы сбрасывается — чип/фильтр начинает список сначала."""
    request = context.get("request")
    q = request.GET.copy() if request is not None else None
    if q is None:
        return f"?{key}={value}" if value else "?"
    for drop in (*_PAGER_DROP, "seite", key):
        q.pop(drop, None)
    if value:
        q[key] = str(value)
    encoded = q.urlencode()
    return f"?{encoded}" if encoded else "?"


#: Параметры, которые ссылки пейджера не переносят: фрагменты, курсоры, возвраты.
_PAGER_DROP = ("box", "cursor", "next", "drawer")  # FLT-4a: шторка не липнет


@register.inclusion_tag("core/_list_pager.html", takes_context=True)
def list_pager(context, page, base=""):
    """KA-P4a: пейджер списка кабинета. Ссылки — текущий GET (все фильтры) с другим
    номером страницы; `base` — путь, если список встроен в чужую страницу (главная)."""
    request = context.get("request")
    params = request.GET.copy() if request is not None else None
    path = base or (request.path if request is not None else "")

    def url(n):
        if params is None:
            return f"{path}?{page.param}={n}"
        q = params.copy()
        for key in (*_PAGER_DROP, page.param):
            q.pop(key, None)
        for key, value in (context.get("pager_params") or {}).items():
            if value:
                q[key] = value
        if n > 1:
            q[page.param] = str(n)
        qs = q.urlencode()
        return f"{path}?{qs}" if qs else path

    return {
        "page": page,
        "prev_url": url(page.page - 1) if page.has_prev else "",
        "next_url": url(page.page + 1) if page.has_next else "",
    }


@register.filter
def can_open(url_name, request):
    """E6.7e: `{% if 'modules'|can_open:request %}` — экран открывается этому
    пользователю (``view_perms``; тот же источник, что скрывает меню)."""
    from apps.core import permissions, view_perms

    user = getattr(request, "user", None)
    if user is None or not permissions.is_member(user):
        return True  # не член команды — кабинет его не пускает, прятать нечего
    return view_perms.allowed_quiet(user, url_name, "GET")


@register.filter
def pkg_allowed(url_name, tenant):
    """T-8.32b: `{% if 'payment-settings'|pkg_allowed:request.tenant %}` — экран открыт пакету."""
    return tenant is None or packages.view_allowed(tenant, str(url_name))


@register.filter
def lite_allowed(url_name, request):
    """KA-12 E8.10: `{% if 'x'|lite_allowed:request %}` — экран открыт пакету И, в Telegram
    Mini App, входит в её белый список (иначе ссылка ведёт в «nicht verfügbar»)."""
    from apps.core import tg_login

    name = str(url_name)
    tenant = getattr(request, "tenant", None)
    if tenant is not None and not packages.view_allowed(tenant, name):
        return False
    return not tg_login.is_tg_session(request) or name in tg_login.TG_LITE_VIEWS


@register.inclusion_tag("tenant/_nav_palette.html", takes_context=True)
def nav_palette(context):
    """W8-4: палитра Ctrl+K — гейтнутый индекс реестра (модуль активен).
    haystack = label+search в нижнем регистре (клиентский фильтр)."""
    return {"entries": nav_registry.palette_entries_for(context.get("request"))}


# E9: стадия → тон детали `.ui-badge` (та же палитра, что `status_tone` по роли:
# новое — жёлтое, в работе — зелёное, завершено — серое, отмена — красное).
_STAGE_BADGES = {
    "intake": "ui-tone-new",
    "in_progress": "ui-tone-ok",
    "done": "ui-tone-done",
    "terminal": "ui-tone-bad",
}


@register.filter
def cblock_label(block_type):
    """STU-12b: переводимое имя типа C-блока (реестр siteconfig.CBLOCK_LABELS);
    незнакомый тип — как есть (мусор в конфиге не роняет форму)."""
    from apps.tenants import siteconfig

    return siteconfig.CBLOCK_LABELS.get(block_type, block_type)


@register.simple_tag(takes_context=True)
def list_block_hint(context, data):
    """LB-1: подписи и пункты строки редактора блока «Liste» (`list_blocks.view_hint`).

    Тег, а не переменная вьюхи: строку рендерят и форма билдера, и вставка без
    перезагрузки (`_add_block_fetch_response`) — так подпись не может разойтись.
    Конфиг — из контекста билдера (`config`), иначе сохранённый конфиг тенанта.
    """
    from apps.core import list_blocks
    from apps.tenants import siteconfig

    cfg = context.get("config")
    if not isinstance(cfg, dict) or "sections" not in cfg:
        tenant = getattr(context.get("request"), "tenant", None)
        cfg = siteconfig.normalize(getattr(tenant, "site_config", None) or {})
    data = data if isinstance(data, dict) else {}
    hint = list_blocks.view_hint(cfg, data)
    # LB-1b: значение блока, которого нет в живых списках, остаётся выбранным (W0).
    hint.update(
        list_blocks.editor_options(
            data,
            context.get("promo_types_for_blocks"),
            context.get("list_categories_for_blocks"),
            sources=context.get("list_sources_for_blocks"),
            collections=context.get("list_collections_for_blocks"),
            themes=context.get("event_categories_for_blocks"),
            countries=context.get("tour_countries_for_blocks"),
            review_kinds=context.get("review_kinds_for_blocks"),
            targets=context.get("promo_targets_for_blocks"),
        )
    )
    return hint


@register.filter
def stage_badge(stage):
    """SH-11: стадия пайплайна → классы пилюли статуса в строке списка.

    Цвет берём по СТАДИИ (реестр pipeline), а не по литеральному коду статуса —
    иначе кастом-статусы владельца (SM-3) остались бы серыми."""
    return _STAGE_BADGES.get(stage or "", "ui-tone-off")


@register.filter
def nav_anchor(nav_key):
    """W8: nav_key страницы → nav_key якоря сайдбара (карта из nav_registry) —
    подсветка «где я» работает на ВСЕХ экранах кабинета, а не на 7 якорных."""
    return nav_registry.anchor_for(nav_key or "")


@register.simple_tag(takes_context=True)
def sidebar_anchor(context):
    """Якорь подсветки сайдбара для текущей страницы (W8 + лёгкий кабинет T-8.29).

    В полном кабинете — карта nav_registry; в лёгком «Verbindungen» — свой пункт, а
    по карте W8 его экраны относились бы к «Einstellungen» (там это «Geschäft»)."""
    nav = context.get("nav_anchor_override") or context.get("nav") or ""
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if nav in LITE_CONNECTION_NAVS:
        from apps.core import lite_cabinet

        if request is not None and lite_cabinet.is_lite_request(request):
            return "integrations"
        if lite_cabinet.is_lite(tenant):
            return "integrations"
    # KA-12 E8.3: страницы скрытого «Finanzen» подсвечивают Einstellungen.
    return nav_registry.anchor_for_tenant(nav, tenant)


# T-8.29: страницы, которые в лёгком кабинете подсвечивают «Verbindungen».
LITE_CONNECTION_NAVS = frozenset({"integrations", "telegram"})


@register.simple_tag
def icon(name, css="w-6 h-6"):
    """ST-4a: SVG-иконка из спрайта tenant/_icons.html (<use href="#<name>">)."""
    from django.utils.html import format_html

    return format_html('<svg class="{}" aria-hidden="true"><use href="#{}"></use></svg>', css, name)


@register.inclusion_tag("tenant/_doc_langs.html", takes_context=True)
def doc_langs(context, url):
    """I18N-7b: языки печатного документа рядом с кнопкой скачивания.

    Владелец отдаёт клиенту счёт/смету/накладную на его языке (`?lang=`), не
    переключая язык всего кабинета. При одном доступном языке партиал пуст."""
    from apps.core.documents import allowed_languages

    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    return {
        "url": url,
        "doc_languages": [{"code": code} for code in allowed_languages(tenant)],
    }


@register.inclusion_tag("tenant/_i18n_switch.html", takes_context=True)
def lang_switch(context):
    """E9.10: ОДИН переключатель языка ввода для всех экранов с переводами.

    Выпадашка рядом с заголовком страницы показывает поля одного языка
    (`[data-i18n-loc]`). Формы с полным i18n-словарём (товар/категория/акция)
    уже кладут `i18n_groups` в контекст — берём их; прочим экранам (набор,
    услуга, номер, правовые тексты) группы строятся по языкам тенанта.
    Один язык — ничего не рендерим."""
    if context.get("i18n_groups") is not None:
        return {
            "i18n_groups": context["i18n_groups"],
            "i18n_multi": context.get("i18n_multi"),
            "request": context.get("request"),
        }
    from django.conf import settings

    from apps.core.i18n_input import form_locales

    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return {"i18n_groups": [], "i18n_multi": False}
    names = dict(settings.LANGUAGES)
    groups = [
        {
            "code": loc,
            "label": str(names.get(loc, loc.upper())),
            "is_base": loc == settings.LANGUAGE_CODE,
        }
        for loc in form_locales(tenant)
    ]
    return {"i18n_groups": groups, "i18n_multi": len(groups) > 1, "request": request}


#: AIS-5: экраны, где машинный перевод не предлагаем (правовые тексты — юридический риск).
NO_TRANSLATE_SCREENS = frozenset({"legal-docs"})


@register.simple_tag(takes_context=True)
def i18n_translate_ctx(context):
    """AIS-5: данные кнопки «🌐 Übersetzen» или None (ИИ выключен, нет права записи экрана,
    правовой экран, вне кабинета). Экран подписывается — эндпоинт верит только подписи."""
    from django.db import connection

    from apps.ai.api import is_enabled
    from apps.core import i18n_translate, view_perms

    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    view_name = getattr(match, "view_name", "") or ""
    user = getattr(request, "user", None)
    if not view_name or view_name in NO_TRANSLATE_SCREENS or user is None:
        return None
    try:
        if not is_enabled(i18n_translate.TASK):
            return None
        if view_perms.rule_for(view_name) is None:
            return None
        if not view_perms.allowed(user, view_name, "POST"):
            return None
    except Exception:  # noqa: BLE001 — кнопка не должна ронять форму
        logger.warning("i18n translate button skipped", exc_info=True)
        return None
    from django.conf import settings
    from django.urls import reverse

    return {
        "url": reverse("i18n-translate"),
        "result": reverse("i18n-translate-result", args=["0" * 32]).rsplit("0" * 32, 1)[0],
        "screen": i18n_translate.sign_screen(connection.schema_name, view_name),
        "base": settings.LANGUAGE_CODE,
    }


#: AIS-7: вид текста → поле ответа → name инпута формы (база описания товара — `<поле>_<база>`).
_DRAFT_TARGETS = {
    "product": lambda base: {"description": f"description_{base}"},
    "service": lambda base: {"description": "description"},
    "about": lambda base: {"about_title": "about_title", "about_text": "about_text"},
    "hero": lambda base: {"hero_title": "hero_title", "hero_text": "hero_text"},
}


@register.inclusion_tag("tenant/_ai_draft_button.html", takes_context=True)
def text_draft_button(context, kind, obj=None, locale=""):
    """AIS-7: «✨ Text vorschlagen» рядом с полем. Без кнопки: ИИ выключен, нет права записи
    экрана, вид не для этого экрана, объект не сохранён (факты читаются из базы)."""
    import json

    from django.conf import settings
    from django.db import connection
    from django.urls import reverse

    from apps.ai.api import is_enabled
    from apps.core import i18n_translate, text_draft, view_perms
    from apps.core.translate_views import DRAFT_HINT_SCREENS, DRAFT_SCREENS

    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    view_name = getattr(match, "view_name", "") or ""
    user = getattr(request, "user", None)
    off = {"draft": None, "unsaved": False}
    if user is None:
        return off
    if kind in DRAFT_HINT_SCREENS.get(view_name, ()):
        try:
            if is_enabled(text_draft.TASK) and view_perms.allowed(user, view_name, "POST"):
                return {"draft": None, "unsaved": True}
        except Exception:  # noqa: BLE001
            logger.warning("text draft hint skipped", exc_info=True)
        return off
    if kind not in DRAFT_SCREENS.get(view_name, ()):
        return off
    try:
        if not is_enabled(text_draft.TASK) or not view_perms.allowed(user, view_name, "POST"):
            return off
    except Exception:  # noqa: BLE001 — кнопка не должна ронять форму
        logger.warning("text draft button skipped", exc_info=True)
        return off
    state = getattr(obj, "_state", None)
    if kind in ("product", "service") and (
        not getattr(obj, "pk", None) or state is None or state.adding
    ):  # UUID-pk есть и у несохранённого объекта — смотрим на _state
        return {"draft": None, "unsaved": True}
    base = settings.LANGUAGE_CODE
    return {
        "unsaved": False,
        "draft": {
            "url": reverse("text-draft"),
            "result": reverse("text-draft-result", args=["0" * 32]).rsplit("0" * 32, 1)[0],
            "screen": i18n_translate.sign_screen(connection.schema_name, view_name),
            "kind": kind,
            "pk": str(getattr(obj, "pk", "") or ""),
            "locale": locale or base,
            "targets": json.dumps(_DRAFT_TARGETS[kind](base)),
        },
    }


#: E9.10: подписи и вид полей переводов в списках кабинета (один словарь на все
#: экраны — подпись поля перевода = подпись базового поля + код языка).
_I18N_FIELD_LABELS = {
    "name": _("Name"),
    "label": _("Name"),
    "title": _("Title"),
    "bio": _("Description"),
    "description": _("Description"),
    "reward_label": _("Reward"),
    "house_rules": _("House rules"),
}
_I18N_MULTILINE = {"bio", "description", "house_rules"}


@register.simple_tag(takes_context=True)
def i18n_inputs(context, obj, fields):
    """E9.10: поля переводов объекта для форм-строк (`tenant/_i18n_inline.html`).

    `fields` — «label,reward_label». Для новой записи (`obj` = None) поля пустые.
    Один язык у тенанта — пустой список, партиал ничего не рисует."""
    from apps.core.i18n_input import i18n_inputs_for

    request = context.get("request")
    names = tuple(f.strip() for f in str(fields).split(",") if f.strip())
    out = i18n_inputs_for(obj, getattr(request, "tenant", None), fields=names)
    for inp in out:
        inp["label"] = _I18N_FIELD_LABELS.get(inp["field"], inp["field"])
        inp["multiline"] = inp["field"] in _I18N_MULTILINE
    return out


@register.simple_tag
def i18n_base_locale():
    """E9.10: код базового языка контента (плоское поле модели) — для
    `data-i18n-loc` у базовых полей на экранах с overlay-переводами."""
    from django.conf import settings

    return settings.LANGUAGE_CODE


@register.inclusion_tag("tenant/_overlay_i18n_inputs.html", takes_context=True)
def overlay_i18n_inputs(context, obj, fields, compact=False):
    """I18N-10: per-locale инпуты overlay-переводов объекта (`<field>_<loc>`).

    Механика Ф1: поля неосновных локалей ЕСТЬ в DOM, но скрыты — свитчер языка
    показывает нужную (инвариант W0: скрытие только CSS). `fields` — строка
    «label,size,color». Один язык у тенанта → тег ничего не рендерит.
    """
    from apps.core.i18n_input import i18n_inputs_for

    request = context.get("request")
    names = tuple(f.strip() for f in fields.split(",") if f.strip())
    return {
        "inputs": i18n_inputs_for(obj, getattr(request, "tenant", None), fields=names),
        "compact": compact,
    }


@register.inclusion_tag("core/_vat_select.html")
def vat_select(current=None, hint="", inherit_label=""):
    """DC-8: поле «MwSt.-Satz» — общее для форм номера/услуги/события.

    Ставка живёт на позиции (проживание 7 %, допы 19 % — Aufteilungsgebot),
    поэтому её выбирают у КАЖДОЙ продаваемой сущности. Свободного ввода нет:
    только три законные ставки DACH (прецедент формы товара, SH-4).

    VAT-3: `inherit_label` добавляет первым пунктом «как у сделки» (пустое
    значение). Он нужен там, где НЕзаданная ставка — законное состояние: у
    доп-услуги пусто означает «облагается как сама сделка», и терять эту
    семантику нельзя."""
    from decimal import Decimal

    from apps.core import vat

    try:
        current_rate = Decimal(str(current)) if current not in (None, "") else None
    except Exception:  # noqa: BLE001 — чужое значение в шаблоне не должно ронять страницу
        current_rate = None
    return {
        "vat_choices": [(f"{r:.2f}", f"{r.normalize():f} %") for r in vat.RATE_CHOICES],
        "vat_current": f"{current_rate:.2f}" if current_rate is not None else "",
        "vat_hint": hint,
        "vat_inherit_label": inherit_label,
    }


@register.filter
def cab_can(user, key):
    """KA-12 E6.7: ``{% if request.user|cab_can:"kunden.export" %}`` — кнопка по праву.
    Неизвестный ключ — ошибка в тестах (PERMS_STRICT), в проде кнопка скрыта."""
    from apps.core.permissions import has_perm

    try:
        return has_perm(user, key)
    except (TypeError, ValueError):
        return False


@register.filter
def cab_is_owner(user):
    """KA-H11: кнопки выгрузок с персональными данными — только владельцу."""
    from apps.core.roles import is_owner

    try:
        return is_owner(user)
    except (TypeError, ValueError):  # не настоящий пользователь — кнопку не показываем
        return False


@register.filter
def money_input(value) -> str:
    """KA-M2: значение денежного поля для рукописного `<input>` («12,50» в de, ввод — как есть)."""
    from apps.core.form_fields import format_money

    return format_money(value)


@register.simple_tag(takes_context=True)
def nav_title(context, fallback=""):
    """KA-12 E8.5: `{% nav_title <перевод fallback> %}` — заголовок страницы = подпись пункта
    меню из реестра (одна строка на экран, правило глоссария). Порядок: запись с
    совпавшим query → запись без query → якорь → fallback (уже переведён `_()`)."""
    from django.http import QueryDict

    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    name = getattr(match, "view_name", "") or ""
    if name:
        get = getattr(request, "GET", {}) or {}
        plain = None
        for e in nav_registry.ENTRIES:
            if e.url_name != name:
                continue
            if not e.query:
                plain = plain or e
                continue
            want = QueryDict(e.query.lstrip("?"))
            if all(get.get(k) == want.get(k) for k in want):
                return str(e.label)
        if plain is not None:
            return str(plain.label)
        for a in nav_registry.ANCHORS:
            if a.url_name == name:
                return str(a.label)
    return str(fallback)


@register.filter
def mask_email(value):
    """E6.7g: «•••@domain.de» — сотрудник без права на контакты узнаёт клиента по домену."""
    from apps.core.contact_access import mask_email as _mask

    return _mask(value or "")


@register.filter
def mask_phone(value):
    """E6.7g: «•••12» — последние цифры телефона."""
    from apps.core.contact_access import mask_phone as _mask

    return _mask(value or "")


@register.filter
def tc_grouped(findings):
    """SP-11: подсказки «Text-Check» без повторов. Правило срабатывает по каждому полю и
    языку отдельно, и одно и то же замечание с той же цитатой выходило до 12 раз
    подряд. Склеиваем по (код, цитата, текст): первое — со своей кнопкой правки,
    остальные места — подписью «auch in: …» (повторная проверка покажет оставшиеся)."""
    groups: dict = {}
    order = []
    for f in findings or []:
        # Поле входит в ключ (ревью): одна цитата в заголовке и в описании — два замечания.
        key = (
            getattr(f, "code", ""),
            getattr(f, "field", ""),
            getattr(f, "quote", ""),
            str(getattr(f, "message", "")),
        )
        if key not in groups:
            groups[key] = (f, [])
            order.append(key)
        else:
            place = (getattr(f, "locale", "") or "").upper()
            if place and place not in groups[key][1]:
                groups[key][1].append(place)
    return [groups[k] for k in order]


@register.inclusion_tag("core/_assistant_fab.html", takes_context=True)
def assistant_fab(context):
    """AIS A-3c: плавающая кнопка «✨ Assistent» — единственный вход в помощника.

    Точка — поддержка ответила, а владелец не прочёл; бейдж клиентов — общий опрос
    `data-inbox-badge` (только если экран бесед открывается). Сбой — кнопка без меток."""
    from apps.core import assistant_panel

    request = context.get("request")
    seite = ""
    support_dot = kunden = False
    if request is None or not getattr(getattr(request, "user", None), "is_authenticated", False):
        return {"request": request, "seite": "", "support_dot": False, "kunden": False}
    memo = getattr(request, "_assistant_fab", None)
    if memo is not None:  # тег мог сработать дважды на одном запросе
        return memo
    try:
        match = getattr(request, "resolver_match", None)
        seite = getattr(match, "view_name", "") or ""
        support_dot = assistant_panel._available(request, "support") and bool(
            assistant_panel.support_unread(request)
        )
        kunden = assistant_panel._available(request, "kunden")
    except Exception:  # noqa: BLE001 — кнопка помощника не роняет кабинет
        logging.getLogger(__name__).warning("assistant fab: badges failed", exc_info=True)
    memo = {"request": request, "seite": seite, "support_dot": support_dot, "kunden": kunden}
    request._assistant_fab = memo
    return memo
