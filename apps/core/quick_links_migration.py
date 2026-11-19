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
from dataclasses import dataclass

REASON = "fb33.m2c-quick-links"
#: ключи настроек, которые меняет перенос (их и хранит снимок). ⚠️ Снимок возвращает
#: `site_defaults` ЦЕЛИКОМ — это безопасно, только пока откат сверяет хэш ВСЕГО конфига
#: (`config_migration.undo`): любая правка после переноса → «changed», откат не трогает.
TOUCHED = ("sections", "site_defaults")
#: топ услуг из баннера — три услуги строками (как прежний виджет)
SERVICES_LIST = {"source": "services", "limit": 3, "card": "compact"}


@dataclass
class Result:
    action: str = ""  # что сделано: "block", "block-hidden", "stay_search", "services", …
    changed: bool = False


#: постоянные id автоблоков: повторное применение шаблона/кита даёт тот же конфиг
#: (идемпотентность — замок `test_template_sweep`); блоки владельца — со своими id
QUICK_LINKS_ID = "quicklinks"
SERVICES_LIST_ID = "services3"


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


def drop_after_hero(config: dict) -> None:
    """Сборка «без плиток» (`hero_widget: "none"`) снимает блок, стоящий СРАЗУ после
    баннера (его ставит сборка/перенос); блок, который владелец поставил сам ниже, не трогает.
    Меняет `config` на месте."""
    rows = config.get("sections")
    if not isinstance(rows, list):
        return
    at = _after_hero(rows)
    if at < len(rows) and isinstance(rows[at], dict) and rows[at].get("key") == "quick_links":
        rows.pop(at)


def detach(config: dict, *, replace: bool = False) -> tuple[dict, Result]:
    """Новые настройки и что сделано. Чистая функция: `config` не меняется.

    `replace` — для писателей (сборки, шаблоны, киты): блок сразу после баннера получает
    набор новой сборки. Перенос (`replace=False`) блок владельца не трогает."""
    from apps.core.hero_tiles import QUICK_LINK_SETS

    defaults = config.get("site_defaults") if isinstance(config.get("site_defaults"), dict) else {}
    widget = defaults.get("hero_widget") or ""
    if not widget:
        return config, Result()
    from apps.tenants import siteconfig

    if not isinstance(widget, str) or widget not in siteconfig.HERO_WIDGETS:
        # мусор (не строка, неизвестный набор) — не переносим и не стираем молча: сайт
        # пропускается с причиной, данные остаются как были (ревью M2c-2)
        return config, Result(action="skip:bad-widget")
    new = copy.deepcopy(config)
    # полный список секций (как его видит витрина): без него «после баннера» некуда — у
    # сайта без сохранённого порядка баннер появился бы только при нормализации
    rows = siteconfig.normalize_sections(new.get("sections"))
    new["sections"] = rows
    bento = new.get("hero_style") == "bento"  # у bento плиток не было — вид не меняем
    if widget in QUICK_LINK_SETS:
        has_block = any(isinstance(r, dict) and r.get("key") == "quick_links" for r in rows)
        nxt = rows[_after_hero(rows)] if _after_hero(rows) < len(rows) else {}
        if replace and isinstance(nxt, dict) and nxt.get("key") == "quick_links":
            nxt["data"] = {"set": widget}
            nxt["enabled"] = not bento
            action = "block-updated"
        elif has_block:
            action = "block-exists"
        else:
            block = {
                "key": "quick_links",
                "id": QUICK_LINKS_ID,
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
                "id": SERVICES_LIST_ID,
                "enabled": not bento,
                "data": dict(SERVICES_LIST),
            }
            rows.insert(_after_hero(rows), block)
            action = "services-list"
    new_defaults = {k: v for k, v in defaults.items() if k != "hero_widget"}
    new["site_defaults"] = new_defaults
    return new, Result(action=action, changed=True)


def _after_hero_row(rows: list):
    at = _after_hero(rows)
    return rows[at] if at < len(rows) else {}


def verify(before: dict, after: dict, action: str = "") -> str:
    """Сверка ПОСЛЕ нормализации (как увидит витрина): то, во что превратился виджет, стоит
    сразу после баннера и (кроме bento) включено; баннер виджет больше не рисует.
    "" — сошлось; иначе причина — сайт не трогается (ревью M2c-2: проверка по действию)."""
    from apps.tenants import siteconfig
    from apps.tenants.templatetags.siteui import banner_tiles

    widget = (before.get("site_defaults") or {}).get("hero_widget") or ""
    norm = siteconfig.normalize(after)
    if banner_tiles(norm):
        return "banner-still-draws"
    rows = [r for r in norm.get("sections") or [] if isinstance(r, dict)]
    nxt = _after_hero_row(rows)
    on = not (norm.get("hero_style") == "bento")
    data = nxt.get("data") if isinstance(nxt.get("data"), dict) else {}
    if action in ("block", "block-hidden"):
        ok = nxt.get("key") == "quick_links" and data.get("set") == widget
        ok = ok and bool(nxt.get("enabled")) == on
        return "" if ok else "block-missing"
    if action == "stay_search":
        ok = nxt.get("key") == "stay_search" and bool(nxt.get("enabled")) == on
        return "" if ok else "search-missing"
    if action == "services":
        return "" if nxt.get("key") == "services" and nxt.get("enabled") else "services-missing"
    if action == "services-list":
        ok = nxt.get("key") == "list" and data.get("source") == "services"
        return "" if ok and bool(nxt.get("enabled")) == on else "services-missing"
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
            return result  # нечего переносить или пропуск (skip:bad-widget)
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
        except OperationalError as exc:
            # занято — только lock_timeout (55P03); обрыв соединения и пр. — настоящая ошибка
            if getattr(exc.__cause__, "pgcode", None) != "55P03":
                raise
            return Result(action=BUSY)
        if written is None:
            continue  # кабинет успел сохранить — считаем заново
        cm.bump(written, label="detach_quick_links")  # после выхода из atomic — записано
        return result
    return Result(action=BUSY)


def undo_tenant(tenant) -> str:
    from apps.core import config_migration as cm

    return cm.undo(tenant.pk, reason=REASON, touched=TOUCHED, label="detach_quick_links")


def residue(tenant) -> bool:
    """Остался ли у сайта `hero_widget` (M2c-4 снимет чтение, когда остатка нет нигде)."""
    cfg = tenant.site_config or {}
    return bool((cfg.get("site_defaults") or {}).get("hero_widget"))
