"""Шаблонные теги кабинета (AB1 язык задач + анти-Битрикс v2 хаб-табы)."""

from django import template

from apps.core import modules, nav_registry

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


# S1/S2/S3 → W8: реестр табов переехал в apps/core/nav_registry.py (ЕДИНЫЙ
# источник навигации: якоря, табы, подсветка, палитра). HUB_TABS — производная
# в прежней форме кортежей (url_name, label, nav_key, module_key, advanced):
# потребители и замки целы, источник правды один.
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


@register.inclusion_tag("tenant/_hub_tabs.html", takes_context=True)
def hub_tabs(context, hub):
    """Отрисовать tab-bar хаба `hub` (реестр HUB_TABS), подсветив активный по `nav`.

    Табы с module_key прячутся, если модуль не активен у тенанта (fail-open, если
    request/tenant в контексте нет — простой тест-рендер без запроса). advanced-табы
    уходят в свёрнутый ящик «Erweitert» (открыт, если активна одна из его вкладок).
    X0: owner-only табы прячутся у сотрудников (см. _hide_owner_only)."""
    cur = context.get("nav")
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    owner_hidden = nav_registry.owner_only_url_names() if _hide_owner_only(context) else frozenset()
    tabs, more = [], []
    for u, lbl, k, mod, advanced in HUB_TABS.get(hub, ()):
        if mod is not None and tenant is not None and not modules.is_module_active(tenant, mod):
            continue
        if u in owner_hidden:
            continue
        if not nav_registry.allowed_for_business(u, tenant):
            continue  # X4: гастро-экраны (KDS/Tisch-QR) — только гастро-типам
        entry = {"url_name": u, "label": lbl, "nav_key": k, "active": k == cur, "module": mod}
        entry["group"] = nav_registry.group_for(hub, u)
        (more if advanced else tabs).append(entry)
    more_active = any(t["active"] for t in more)
    # X5-1: у хаба с группами главные вкладки идут ПОДПИСАННЫМИ рядами (девять
    # вкладок настроек уезжали в горизонтальный скролл — Abo/Team не видны).
    # Хабы без групп рендерятся прежним плоским рядом (rows пуст).
    rows = []
    if any(t["group"] for t in tabs):
        for key, label in nav_registry.TAB_GROUPS:
            group_tabs = [t for t in tabs if t["group"] == key]
            if group_tabs:
                rows.append({"key": key, "label": label, "tabs": group_tabs})
        rest = [t for t in tabs if not t["group"]]
        if rest:
            rows.append({"key": "", "label": "", "tabs": rest})
    return {"tabs": tabs, "rows": rows, "more_tabs": more, "more_active": more_active}


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
        entries.append(
            {
                "url_name": e["url_name"],
                "label": e["label"],
                "area": area_by_hub.get(e["hub"], ""),
                "haystack": f"{e['label']} {e['search']}".lower(),
            }
        )
    return {"entries": entries}


@register.filter
def nav_anchor(nav_key):
    """W8: nav_key страницы → nav_key якоря сайдбара (карта из nav_registry) —
    подсветка «где я» работает на ВСЕХ экранах кабинета, а не на 7 якорных."""
    return nav_registry.anchor_for(nav_key or "")


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
