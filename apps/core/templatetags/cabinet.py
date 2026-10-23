"""Шаблонные теги кабинета (AB1 язык задач + анти-Битрикс v2 хаб-табы)."""

from django import template

from apps.core import modules, nav_registry, packages

register = template.Library()


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
    from apps.core import status_registry

    tenant_obj = getattr(context.get("request"), "tenant", None)
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


def _hide_owner_only(context) -> bool:
    """X0: True — пользователь ОПРЕДЕЛЁННО сотрудник (не owner) текущего тенанта →
    owner-only записи (Recht/Abo/Team) прячем: мидлварь W9-10 всё равно отдаст им
    403, мёртвый таб только путает. Fail-open: аноним/тест-стаб/ошибка → показываем
    (доступ держит middleware, скрытие — чистый UX-слой)."""
    request = context.get("request")
    if request is None:
        return False
    try:
        from apps.core import roles
        from apps.core.models import Membership

        role = roles.role_of(getattr(request, "user", None))
        return bool(role) and role != Membership.ROLE_OWNER
    except Exception:  # noqa: BLE001 — рендер хрома не должен падать из-за ролей
        return False


#: Параметры, которые ссылки пейджера не переносят: фрагменты, курсоры, возвраты.
_PAGER_DROP = ("box", "cursor", "next")


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
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    area_by_hub = {hub: a.label for a in nav_registry.ANCHORS for hub in a.hubs}
    owner_hidden = nav_registry.owner_only_url_names() if _hide_owner_only(context) else frozenset()
    entries = []
    for e in nav_registry.palette_entries():
        mod = e["module_key"]
        if mod is not None and tenant is not None and not modules.is_module_active(tenant, mod):
            continue
        if e["url_name"] in owner_hidden:  # X0: сотрудник не видит owner-only экраны
            continue
        if not nav_registry.allowed_for_business(e["url_name"], tenant):
            continue  # X4: гейт по типу бизнеса (гастро-экраны)
        if tenant is not None and not packages.view_allowed(tenant, e["url_name"]):
            continue  # T-8.32b: экраны вне пакета в палитре не показываем
        entries.append(
            {
                "url_name": e["url_name"],
                # VF-10: вкладки-адреса («Aufträge» ?tab=job) — прыжок с query
                "query": e.get("query", ""),
                "label": e["label"],
                "area": area_by_hub.get(e["hub"], ""),
                "haystack": f"{e['label']} {e['search']}".lower(),
            }
        )
    return {"entries": entries}


_STAGE_BADGES = {
    "intake": "bg-amber-100 text-amber-800",
    "in_progress": "bg-indigo-100 text-indigo-800",
    "done": "bg-green-100 text-green-800",
    "terminal": "bg-gray-100 text-gray-500",
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
    return _STAGE_BADGES.get(stage or "", "bg-gray-100 text-gray-500")


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
    return nav_registry.anchor_for(nav)


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
def cab_can_export_finance(user):
    """KA-D7: кнопки финансовых выгрузок — владельцу и admin."""
    from apps.core.roles import can_export_finance

    try:
        return can_export_finance(user)
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
