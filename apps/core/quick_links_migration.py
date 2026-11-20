"""FB-33 M2c-2: перенос «Быстрых ссылок» из баннера главной в отдельный блок.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2c» (решения владельца 2026-11-19):

* набор-ссылки (`site_defaults.hero_widget` из `hero_tiles.QUICK_LINK_SETS`) → блок
  `quick_links` сразу после баннера; у баннера «Bento» (плиток он не рисовал) — блок
  СКРЫТЫЙ, вид сайта не меняется;
* `stays` (форма дат) → секция «Suche» (`stay_search`) включена и стоит сразу после баннера;
* `services` (топ услуг) → секция «Leistungen», если она включена, — сразу после баннера;
  иначе блок «Liste» из трёх услуг строками;
* ключ `hero_widget` снимается. Повтор — 0 изменений (ключа уже нет).

M2c-4 (2026-11-20): витрина и нормализатор ключ не читают; писатели (шаблоны, сборки,
демо-киты) ставят блок сами через `place` — ключ больше не переносчик между ними.

`place`/`detach` — чистые функции (без базы); запись — общий писатель `config_migration`
(блокировка, сверка, снимок, откат), команда — `detach_quick_links`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from apps.core.hero_tiles import QUICK_LINK_SETS

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


def _hero_shown(rows: list) -> bool:
    hero = next(
        (r for r in rows if isinstance(r, dict) and r.get("key") == "hero" and not r.get("id")),
        None,
    )
    return bool(hero) and hero.get("enabled", True) is not False


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


def drop_auto_blocks(config: dict) -> None:
    """Сборка «без плиток» или сборка без оси плиток снимает АВТОблоки (постоянные id
    `QUICK_LINKS_ID`/`SERVICES_LIST_ID` ставят только перенос и писатели); блоки, которые
    владелец поставил сам (свои id), не трогаются. Меняет `config` на месте."""
    rows = config.get("sections")
    if not isinstance(rows, list):
        return
    auto = {QUICK_LINKS_ID, SERVICES_LIST_ID}
    rows[:] = [r for r in rows if not (isinstance(r, dict) and r.get("id") in auto)]


#: значения прежнего ключа `site_defaults.hero_widget`, которые понимает перенос: наборы-
#: ссылки блока + форма дат и топ услуг (они становятся секциями). После M2c-4 ключ читает
#: только перенос (`detach`, копии баз со старым ключом) — витрина и нормализатор его не знают.
LEGACY_WIDGETS = (*QUICK_LINK_SETS, "stays", "services")


def place(config: dict, widget: str, *, replace: bool = False) -> tuple[dict, Result]:
    """Поставить набор первого экрана `widget` на главную. Чистая функция: `config` не
    меняется. Единая точка для переноса и писателей (шаблоны, сборки, демо-киты, M2c-4):

    * набор-ссылки → блок `quick_links` сразу после баннера;
    * `stays` → секция «Suche» включена и стоит сразу после баннера;
    * `services` → секция «Leistungen» (если включена) сразу после баннера, иначе список
      из трёх услуг;
    * у «Bento» и при выключенном баннере (плиток не было видно) — СКРЫТЫМ.

    `replace` — для писателей: уже стоящий блок получает новый набор (место и видимость не
    трогаются). Перенос (`replace=False`) блок владельца не трогает вовсе. Пустой `widget` —
    без изменений; неизвестный — пропуск с причиной (`skip:bad-widget`)."""
    if not widget:
        return config, Result()
    if not isinstance(widget, str) or widget not in LEGACY_WIDGETS:
        # мусор (не строка, неизвестный набор) — не переносим и не стираем молча: сайт
        # пропускается с причиной, данные остаются как были (ревью M2c-2)
        return config, Result(action="skip:bad-widget")
    from apps.tenants import siteconfig

    new = copy.deepcopy(config)
    # полный список секций (как его видит витрина): без него «после баннера» некуда — у
    # сайта без сохранённого порядка баннер появился бы только при нормализации
    rows = siteconfig.normalize_sections(new.get("sections"))
    new["sections"] = rows
    # плиток на сайте не было видно — у bento (не читал виджет) и при выключенном баннере
    # (стенд M2c: виджет живёт внутри баннера): то, во что он превращается, ставится
    # СКРЫТЫМ — вид сайта не меняется
    bento = new.get("hero_style") == "bento" or not _hero_shown(rows)
    if widget in QUICK_LINK_SETS:
        existing = next(
            (r for r in rows if isinstance(r, dict) and r.get("key") == "quick_links"), None
        )
        if existing is not None and replace:
            # писатель (сборка, шаблон, кит) задаёт набор: меняется только НАБОР уже
            # стоящего блока — место и «показан/скрыт» остаются владельцу (ревью M2c-3)
            data = existing.get("data") if isinstance(existing.get("data"), dict) else {}
            existing["data"] = {**data, "set": widget}
            action = "block-updated"
        elif existing is not None:
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
    else:  # services
        services = next(
            (r for r in rows if isinstance(r, dict) and r.get("key") == "services"), None
        )
        if services is not None and services.get("enabled"):
            _move_after_hero(rows, "services", enable=True)
            action = "services"
        elif any(isinstance(r, dict) and r.get("id") == SERVICES_LIST_ID for r in rows):
            action = "services-list-exists"  # уже поставлен прежним применением — без дубля
        else:
            block = {
                "key": "list",
                "id": SERVICES_LIST_ID,
                "enabled": not bento,
                "data": dict(SERVICES_LIST),
            }
            rows.insert(_after_hero(rows), block)
            action = "services-list"
    return new, Result(action=action, changed=True)


def detach(config: dict, *, replace: bool = False) -> tuple[dict, Result]:
    """Перенос старого ключа: прочитать `site_defaults.hero_widget` → `place` → снять ключ.
    Чистая функция: `config` не меняется. Нет ключа — без изменений; мусор — пропуск с
    причиной, ключ остаётся (данные не стираются молча)."""
    defaults = config.get("site_defaults") if isinstance(config.get("site_defaults"), dict) else {}
    widget = defaults.get("hero_widget") or ""
    if not widget:
        return config, Result()
    new, result = place(config, widget, replace=replace)
    if not result.changed:
        return config, result
    new["site_defaults"] = {k: v for k, v in defaults.items() if k != "hero_widget"}
    return new, result


def _after_hero_row(rows: list):
    at = _after_hero(rows)
    return rows[at] if at < len(rows) else {}


def verify(before: dict, after: dict, action: str = "") -> str:
    """Сверка ПОСЛЕ нормализации (как увидит витрина): то, во что превратился виджет, стоит
    сразу после баннера и (кроме bento) включено; ключа в новых настройках нет.
    "" — сошлось; иначе причина — сайт не трогается (ревью M2c-2: проверка по действию)."""
    from apps.tenants import siteconfig

    widget = (before.get("site_defaults") or {}).get("hero_widget") or ""
    if "hero_widget" in (after.get("site_defaults") or {}):
        return "key-left"
    norm = siteconfig.normalize(after)
    rows = [r for r in norm.get("sections") or [] if isinstance(r, dict)]
    nxt = _after_hero_row(rows)
    on = norm.get("hero_style") != "bento" and _hero_shown(rows)
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
    """Остался ли у сайта старый ключ `hero_widget` (с M2c-4 витрина его не читает: остаток
    — копия базы до переноса, её доводит шаг деплоя `detach_quick_links`)."""
    cfg = tenant.site_config or {}
    return bool((cfg.get("site_defaults") or {}).get("hero_widget"))
