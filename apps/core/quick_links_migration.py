"""FB-33 M2c-2: перенос «Быстрых ссылок» из баннера главной в отдельный блок.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2c» (решения владельца 2026-11-19):

* набор-ссылки (`site_defaults.hero_widget` из `hero_tiles.QUICK_LINK_SETS`) → блок
  `quick_links` сразу после баннера; у баннера «Bento» (плиток он не рисовал) — блок
  СКРЫТЫЙ, вид сайта не меняется;
* `stays` (форма дат) → секция «Suche» (`stay_search`) включена и стоит сразу после баннера;
* `services` (топ услуг) → секция «Leistungen», если она включена, — сразу после баннера;
  иначе блок «Liste» из трёх услуг строками;
* ключ `hero_widget` снимается. Повтор — 0 изменений (ключа уже нет).

`detach` — чистая функция (без базы); запись — общий писатель `config_migration`
(блокировка, сверка, снимок, откат), команда — `detach_quick_links`.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass

REASON = "fb33.m2c-quick-links"
#: ключи настроек, которые меняет перенос (их и хранит снимок)
TOUCHED = ("sections", "site_defaults")
#: топ услуг из баннера — три услуги строками (как прежний виджет)
SERVICES_LIST = {"source": "services", "limit": 3, "card": "compact"}


@dataclass
class Result:
    action: str = ""  # что сделано: "block", "block-hidden", "stay_search", "services", …
    changed: bool = False


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _after_hero(rows: list) -> int:
    """Куда ставить: сразу после баннера; баннера нет — в начало."""
    for i, row in enumerate(rows):
        if isinstance(row, dict) and row.get("key") == "hero" and not row.get("id"):
            return i + 1
    return 0


def _move_after_hero(rows: list, key: str, *, enable: bool) -> None:
    at = next((i for i, r in enumerate(rows) if isinstance(r, dict) and r.get("key") == key), None)
    row = rows.pop(at) if at is not None else {"key": key}
    if enable:
        row["enabled"] = True
    rows.insert(_after_hero(rows), row)


def detach(config: dict) -> tuple[dict, Result]:
    """Новые настройки и что сделано. Чистая функция: `config` не меняется."""
    from apps.core.hero_tiles import QUICK_LINK_SETS

    defaults = config.get("site_defaults") if isinstance(config.get("site_defaults"), dict) else {}
    widget = defaults.get("hero_widget") or ""
    if not widget:
        return config, Result()
    new = copy.deepcopy(config)
    from apps.tenants import siteconfig

    # полный список секций (как его видит витрина): без него «после баннера» некуда — у
    # сайта без сохранённого порядка баннер появился бы только при нормализации
    rows = siteconfig.normalize_sections(new.get("sections"))
    new["sections"] = rows
    bento = new.get("hero_style") == "bento"  # у bento плиток не было — вид не меняем
    if widget in QUICK_LINK_SETS:
        has_block = any(isinstance(r, dict) and r.get("key") == "quick_links" for r in rows)
        if has_block:
            action = "block-exists"
        else:
            block = {
                "key": "quick_links",
                "id": _new_id(),
                "enabled": not bento,
                "data": {"set": widget},
            }
            rows.insert(_after_hero(rows), block)
            action = "block-hidden" if bento else "block"
    elif widget == "stays":
        _move_after_hero(rows, "stay_search", enable=not bento)
        action = "stay_search"
    elif widget == "services":
        services = next(
            (r for r in rows if isinstance(r, dict) and r.get("key") == "services"), None
        )
        if services is not None and services.get("enabled"):
            _move_after_hero(rows, "services", enable=True)
            action = "services"
        else:
            block = {
                "key": "list",
                "id": _new_id(),
                "enabled": not bento,
                "data": dict(SERVICES_LIST),
            }
            rows.insert(_after_hero(rows), block)
            action = "services-list"
    else:
        action = "unknown"  # мусорный ключ — просто снимаем (баннер его и так не рисовал)
    new_defaults = {k: v for k, v in defaults.items() if k != "hero_widget"}
    new["site_defaults"] = new_defaults
    return new, Result(action=action, changed=True)


def verify(before: dict, after: dict, action: str = "") -> str:
    """Сверка после нормализации: блок/секция на месте и баннер больше не рисует виджет.
    "" — сошлось; иначе причина (сайт не трогается)."""
    from apps.tenants import siteconfig
    from apps.tenants.templatetags.siteui import banner_tiles

    widget = ((before.get("site_defaults") or {}).get("hero_widget")) or ""
    norm = siteconfig.normalize(after)
    if banner_tiles(norm):
        return "banner-still-draws"
    rows = norm.get("sections") or []
    from apps.core.hero_tiles import QUICK_LINK_SETS

    if (
        action in ("block", "block-hidden")
        and widget in QUICK_LINK_SETS
        and not any(
            r.get("key") == "quick_links" and (r.get("data") or {}).get("set") == widget
            for r in rows
            if isinstance(r, dict)
        )
    ):
        return "block-missing"
    return ""


ROLLED_BACK = "rolled_back"
BUSY = "busy"
_ATTEMPTS = 3


def apply_tenant(tenant, *, dry_run: bool = False) -> Result:
    """Перенести один сайт: расчёт без блокировки, под блокировкой — сверка «настройки не
    менялись» и одна запись со снимком (общий писатель `config_migration`)."""
    from django.db import OperationalError, transaction

    from apps.core import config_migration as cm
    from apps.tenants.models import Tenant

    if cm.rolled_back(tenant.pk, REASON):
        return Result(action=ROLLED_BACK)  # владелец откатил — не повторяем
    for _attempt in range(_ATTEMPTS):
        row = Tenant.objects.filter(pk=tenant.pk).values_list("site_config", flat=True).first()
        if row is None:
            return Result()  # сайт удалили во время прогона
        before = row or {}
        new, result = detach(before)
        if not result.changed:
            return result
        problem = verify(before, new, result.action)
        if problem:
            return Result(action=f"skip:{problem}")
        if dry_run:
            return result
        try:
            with transaction.atomic():
                written = cm.write_with_snapshot(
                    tenant.pk, before, new, reason=REASON, touched=TOUCHED
                )
        except OperationalError:  # строка занята дольше lock_timeout
            return Result(action=BUSY)
        if written is None:
            continue  # кабинет успел сохранить — считаем заново
        transaction.on_commit(lambda s=written: cm.bump(s, label="detach_quick_links"))
        return result
    return Result(action=BUSY)


def undo_tenant(tenant) -> str:
    from apps.core import config_migration as cm

    return cm.undo(tenant.pk, reason=REASON, touched=TOUCHED, label="detach_quick_links")


def residue(tenant) -> bool:
    """Остался ли у сайта `hero_widget` (M2c-4 снимет чтение, когда остатка нет нигде)."""
    cfg = tenant.site_config or {}
    return bool((cfg.get("site_defaults") or {}).get("hero_widget"))
