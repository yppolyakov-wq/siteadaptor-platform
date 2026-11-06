"""AIS-M M-1c: экран «Richtungen & Funktionen» (`/dashboard/modules/`).

Четыре блока (план `ais-m1-directions-screen-plan-2026-11-05.md` §0):
1. **Ihre Richtungen** — активные направления карточками (Waren — тумблер «Online
   verkaufen» = модуль orders; Speisekarte — без тумблера);
2. **Funktionen** — дополнения активных направлений (и включённые — чтобы их можно было
   выключить);
3. **Weitere Richtung hinzufügen** — неактивные направления;
4. **Von Ihnen ausgeschaltet** — базовые модули, которые кто-то выключил.

Каждая карточка — своя маленькая POST-форма с одним ключом; пишут только
`modules.set_modules` и `directions.set_state` (класс W0/W6 — большого Save больше нет)."""

from __future__ import annotations

from django.utils.translation import gettext as _

from apps.core import directions, modules, packages

ACTION_DIRECTION = "direction"
ACTION_MODULE = "module"


def _selling(active_keys: set[str], tenant) -> bool:
    other = active_keys - {"waren", "speisekarte"}
    return bool(other) or modules.is_module_active(tenant, "orders")


def _addon_fits(spec, active_keys: set[str], selling: bool) -> bool:
    for target in spec.addon_for:
        if target == modules.ANY and active_keys:
            return True
        if target == modules.SELLING and selling:
            return True
        if target in active_keys:
            return True
    return False


def _module_row(tenant, spec) -> dict:
    disabled = set(tenant.disabled_modules or [])
    return {
        "key": spec.key,
        "label": spec.label_de,
        "icon": spec.icon,
        "description": spec.description_de,
        "on": spec.key not in disabled,
        "active": modules.is_module_active(tenant, spec.key),
        "in_package": packages.module_allowed(tenant, spec.key),
        "lite_locked": bool(
            modules.module_switch_problem(tenant, spec.key, False) == modules.SET_LITE
        ),
    }


def _direction_card(tenant, d, active: bool) -> dict:
    in_package = all(packages.module_allowed(tenant, m) for m in d.modules)
    card = {
        "key": d.key,
        "label": d.label,
        "blurb": d.blurb,
        "icon": d.icon,
        "active": active,
        "fixed": d.key in directions.FIXED,
        "in_package": in_package,
    }
    if d.key == "waren":
        orders = modules.get_module("orders")
        card["sell"] = _module_row(tenant, orders)
    return card


def _late_promo(tenant) -> str:
    """M-1d: у отеля/туров/ремесла акции включены, но пункт меню ждёт первой акции —
    карточка-вход. Пусто = карточки нет; иначе "craft" или "stay" (своя подпись)."""
    from apps.core import nav_registry

    btype = getattr(tenant, "business_type", "")
    if btype not in nav_registry.LATE_PROMO_TYPES:
        return ""
    if not modules.is_module_active(tenant, "promotions") or nav_registry.has_promotions(tenant):
        return ""
    return "craft" if btype in ("handwerker", "werkstatt") else "stay"


def context(tenant) -> dict:
    active_dirs = directions.active(tenant)
    active_keys = {d.key for d in active_dirs}
    selling = _selling(active_keys, tenant)
    mine = [_direction_card(tenant, d, True) for d in active_dirs]
    choices = {d.key for d in directions.choices_for(tenant)}
    more = [
        _direction_card(tenant, d, False)
        for d in directions.REGISTRY
        # Waren (FIXED: не выключается) неактивна — карточка нужна, иначе выключенный
        # orders у салона/отеля без товаров был бы недостижим (ревью M-1c, HIGH).
        if d.key not in active_keys and d.key != "speisekarte" and d.key in choices
    ]
    disabled = set(tenant.disabled_modules or [])
    addons = [
        _module_row(tenant, spec)
        for spec in modules.REGISTRY
        if spec.layer == "addon"
        and (_addon_fits(spec, active_keys, selling) or spec.key not in disabled)
    ]
    # Выключенные дополнения без подходящего направления — свёрнутым списком: контрол
    # у выключенного модуля есть ВСЕГДА (диагноз «X ist ausgeschaltet» ведёт сюда).
    shown = {r["key"] for r in addons}
    other_addons = [
        _module_row(tenant, spec)
        for spec in modules.REGISTRY
        if spec.layer == "addon" and spec.key not in shown
    ]
    base_off = [
        _module_row(tenant, spec)
        for spec in modules.REGISTRY
        if spec.layer == "base" and spec.key in disabled
    ]
    return {
        "late_promo": _late_promo(tenant),
        "mine": mine,
        "addons": addons,
        "other_addons": other_addons,
        "more": more,
        "base_off": base_off,
    }


def problem_text(code: str) -> str:
    return {
        modules.SET_PACKAGE: _("Nicht im Paket."),
        modules.SET_LITE: _("In Ihrem Paket immer eingeschaltet."),
        modules.SET_CORE: _("Immer eingeschaltet."),
        directions.STATE_FIXED: _("Diese Richtung ergibt sich aus Ihrem Angebot."),
        directions.STATE_SHARED: _("Wird von einer anderen Richtung genutzt."),
        directions.STATE_UNCHANGED: _("Für diese Richtung gibt es hier nichts umzuschalten."),
    }.get(code, _("Konnte nicht gespeichert werden."))


def apply(tenant, action: str, key: str, on: bool) -> dict[str, str] | None:
    """Записать один переключатель. None — неизвестное действие/ключ (400)."""
    if action == ACTION_DIRECTION and directions.get(key) is not None:
        problems = directions.set_state(tenant, key, on)
        if not problems and directions.is_active(tenant, key) != on:
            problems = {key: directions.STATE_UNCHANGED}  # не «Gespeichert» на пустом месте
        return problems
    if action == ACTION_MODULE:
        spec = modules.get_module(key)
        # Модули направлений — только через set_state (проверка общего модуля);
        # исключение — orders: тумблер «Online verkaufen» карточки Waren.
        if spec is None or (spec.layer not in ("base", "addon") and key != "orders"):
            return None
        return modules.set_modules(tenant, {key: on})
    return None
