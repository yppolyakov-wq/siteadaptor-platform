"""FB-27 R2: черновик экрана «Seitenaufbau» — правки копятся и попадают на сайт
только по «Speichern».

Решение владельца (2026-11-11): черновик свой у каждого типа страницы, «Speichern» /
«Verwerfen», счётчик изменений. Хранение — сессия (план, вариант V1): `site_config`
не трогается, поэтому нет гонки с автосейвом Студии; цена — черновик не переживает
закрытие браузера и не переходит на другое устройство.

Черновик хранит блоки страницы целиком и отпечаток сохранённого состояния, с которого
начат (`base`). Если к моменту «Speichern» сохранённое изменилось в другом месте,
запись отклоняется (`DraftConflict`) — владелец решает: отбросить черновик или записать
поверх.
"""

from __future__ import annotations

import copy
import hashlib
import json

from django.db import transaction

from apps.core import site_schema

SESSION_KEY = "aufbau_draft"
#: Потолок числа черновиков в сессии (страниц с несохранёнными правками).
MAX_DRAFTS = 10


class DraftConflict(Exception):
    """Сохранённое состояние страницы изменилось с момента начала черновика."""


def _saved_state(config: dict, home: bool, host: str) -> dict:
    state = {"items": site_schema.load_items(config, home, host)}
    if host == "info":
        state["contact"] = config.get("about_contact") is not False
    return state


def _fingerprint(state: dict) -> str:
    raw = json.dumps(state, sort_keys=True, default=str).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def _keys_fingerprint(config: dict, codes) -> str:
    """Отпечаток сохранённых значений настроек типа (FB-27 R4). Многие ключи общие для
    нескольких страниц (форма карточки, ширина текста) — так видно, что значение успели
    изменить на другой странице."""
    from apps.core import page_settings

    return _fingerprint({c: page_settings.stored(config, c) for c in codes or ()})


def _settings(draft: dict) -> dict:
    pending = draft.get("settings")
    return pending if isinstance(pending, dict) else {}


def _apply_settings(config: dict, draft: dict) -> dict:
    """Настройки черновика поверх `config` (для показа и превью). Недопустимая запись
    пропускается: превью не должно падать из-за устаревшего черновика."""
    from apps.core import page_settings

    for code, entry in _settings(draft).items():
        try:
            config = page_settings.apply_override(
                config, code, (entry or {}).get("v"), (entry or {}).get("o")
            )
        except (page_settings.PageSettingError, AttributeError, KeyError, TypeError, ValueError):
            continue
    return config


def _all(request) -> dict:
    session = getattr(request, "session", None)
    drafts = session.get(SESSION_KEY) if session is not None else None
    return drafts if isinstance(drafts, dict) else {}


def get(request, code: str) -> dict | None:
    draft = _all(request).get(code)
    return draft if isinstance(draft, dict) and isinstance(draft.get("items"), list) else None


def _put(request, code: str, draft: dict | None) -> None:
    drafts = dict(_all(request))
    if draft is None:
        drafts.pop(code, None)
    else:
        drafts.pop(code, None)  # свежий — в конец: при переполнении уходит самый старый
        drafts[code] = draft
        while len(drafts) > MAX_DRAFTS:
            drafts.pop(next(iter(drafts)))
    if drafts:
        request.session[SESSION_KEY] = drafts
    else:
        request.session.pop(SESSION_KEY, None)


def dirty_codes(request) -> list[str]:
    """Коды страниц с несохранёнными правками (для пометок в списке страниц)."""
    return [code for code in _all(request) if get(request, code)]


def overlay(config: dict, draft: dict) -> dict:
    """Копия `config` с блоками черновика на месте сохранённых — для показа схемы и
    превью. Базу не читает: хост записан в самом черновике."""
    out = copy.deepcopy(config)
    home, host = bool(draft.get("home")), str(draft.get("host") or "")
    items = copy.deepcopy(draft.get("items") or [])
    if home:
        out["sections"] = items
    elif host:
        page_blocks = dict(out.get("page_blocks") or {})
        page_blocks[host] = items
        out["page_blocks"] = page_blocks
    if host == "info" and "contact" in draft:
        if draft["contact"]:
            out.pop("about_contact", None)
        else:
            out["about_contact"] = False
    return _apply_settings(out, draft)


def changes(saved: dict, draft: dict) -> int:
    """Число несохранённых изменений: добавлено + удалено + скрыто/показано +
    ширина + порядок (один раз) + карточка контактов."""

    def ident(item):
        return item.get("id") or item.get("key")

    old = {ident(i): i for i in saved["items"]}
    new = {ident(i): i for i in draft["items"]}
    common = [k for k in new if k in old]
    count = len(set(new) - set(old)) + len(set(old) - set(new))
    count += sum(
        1 for k in common if bool(old[k].get("enabled", True)) != bool(new[k].get("enabled", True))
    )
    # FB-27 R3: ширина и «с новой строки» — одно изменение на блок.
    count += sum(
        1
        for k in common
        if (old[k].get("width") or "contained", bool(old[k].get("newline")))
        != (new[k].get("width") or "contained", bool(new[k].get("newline")))
    )
    # FB-27 R3b: содержимое блока (текст, подпись, ссылка) — одно изменение на блок.
    count += sum(1 for k in common if (old[k].get("data") or {}) != (new[k].get("data") or {}))
    if [k for k in old if k in new] != common:
        count += 1
    if "contact" in draft and bool(draft["contact"]) != bool(saved.get("contact", True)):
        count += 1
    # FB-27 R4: настройки типа страницы — по одному изменению на настройку.
    count += len(_settings(draft))
    return count


def info(request, config: dict, code: str) -> dict:
    """Состояние черновика страницы для экрана: {"count", "conflict"} (count=0 — чисто)."""
    draft = get(request, code)
    if not draft:
        return {"count": 0, "conflict": False}
    saved = _saved_state(config, bool(draft.get("home")), str(draft.get("host") or ""))
    return {
        "count": changes(saved, draft),
        "conflict": _fingerprint(saved) != draft.get("base") or _keys_conflict(config, draft),
    }


def _keys_conflict(config: dict, draft: dict) -> bool:
    """Значение настройки, которую держит черновик, успели изменить в другом месте."""
    if "kbase" not in draft:  # черновик без настроек (или начатый до R4)
        return False
    return _keys_fingerprint(config, draft.get("kcodes")) != draft["kbase"]


def op(
    request,
    tenant,
    code: str,
    op_name: str,
    ref: str = "",
    block_type: str = "",
    value: str = "",
    fields: dict | None = None,
) -> str:
    """Одна правка схемы — в черновик (база не меняется). SchemaError на недопустимом."""
    from apps.tenants import siteconfig

    _pt, host, home = site_schema.resolve(tenant, code)
    config = siteconfig.normalize(tenant.site_config)
    saved = _saved_state(config, home, host)
    draft = get(request, code)
    if not draft:
        draft = {**copy.deepcopy(saved), "base": _fingerprint(saved), "home": home, "host": host}
    if host == "info" and ref == site_schema.CONTACT_REF:
        if op_name != "toggle":
            raise site_schema.SchemaError("fixed")
        draft["contact"] = not draft.get("contact", True)
    else:
        ref = site_schema.mutate(draft["items"], code, op_name, ref, block_type, value, fields)
    return _settle(request, code, draft, saved, ref)


def _settle(request, code: str, draft: dict, saved: dict, ref: str = "") -> str:
    current = {k: draft.get(k) for k in saved}
    # Вернулись к сохранённому (скрыл и снова показал) — черновика нет.
    clean = _fingerprint(current) == _fingerprint(saved) == draft.get("base") and not _settings(
        draft
    )
    _put(request, code, None if clean else draft)
    return ref


def setting_op(
    request,
    tenant,
    code: str,
    setting: str,
    value,
    output: dict | None = None,
    apply_all: bool = False,
) -> list[str]:
    """FB-27 R4: настройка типа страницы — в черновик. Возвращает коды «на все списки»,
    которым значение не подошло (их пропустили). SchemaError / PageSettingError — если
    саму настройку здесь менять нельзя или значение недопустимо."""
    from apps.core import page_settings
    from apps.tenants import siteconfig

    _pt, host, home = site_schema.resolve(tenant, code)
    codes = site_schema.setting_codes(tenant, code)
    if setting not in codes:
        raise site_schema.SchemaError("setting")
    config = siteconfig.normalize(tenant.site_config)
    saved = _saved_state(config, home, host)
    draft = get(request, code)
    if not draft:
        draft = {**copy.deepcopy(saved), "base": _fingerprint(saved), "home": home, "host": host}
    targets = [setting]
    if apply_all and setting in page_settings.APPLY_ALL_LAYOUTS:
        targets += [
            other
            for other in page_settings.APPLY_ALL_LAYOUTS
            if other != setting
            and page_settings.type_active(tenant, page_settings.APPLY_ALL_TYPES[other])
        ]
    pending = dict(_settings(draft))
    gate = page_settings.composition_gate(config)
    skipped = []
    for target in targets:
        shown = _apply_settings(copy.deepcopy(config), {"settings": pending})
        try:
            cleaned = page_settings.validate(tenant, target, value, gate, config=shown)
            after = page_settings.apply_override(config, target, cleaned, output)
        except page_settings.PageSettingError:
            if target == setting:
                raise
            skipped.append(target)
            continue
        # Равно сохранённому — записи в черновике нет («вернул как было»).
        same = siteconfig.normalize(after) == config
        if same:
            pending.pop(target, None)
        else:
            pending[target] = {"v": cleaned, "o": output}
    if pending:
        draft["settings"] = pending
        if "kbase" not in draft:
            tracked = sorted(set(codes) | set(pending))
            draft["kcodes"] = tracked
            draft["kbase"] = _keys_fingerprint(config, tracked)
    else:
        for key in ("settings", "kbase", "kcodes"):
            draft.pop(key, None)
    _settle(request, code, draft, saved)
    return skipped


def discard(request, code: str) -> None:
    _put(request, code, None)


@transaction.atomic
def commit(request, tenant, code: str, *, force: bool = False) -> bool:
    """Записать черновик страницы на сайт. `DraftConflict`, если сохранённое успели
    изменить в другом месте (и не задан `force`). False — черновика нет (двойная
    отправка, сессия истекла): вызывающий не должен сообщать об успехе."""
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    draft = get(request, code)
    if not draft:
        return False
    try:
        _pt, host, home = site_schema.resolve(tenant, code)
    except site_schema.SchemaError:
        # Страницы больше нет (модуль выключен, страница удалена): черновик некуда
        # записать — убираем его, иначе он висел бы невидимым до конца сессии.
        _put(request, code, None)
        raise
    gate = None
    if _settings(draft):
        from apps.core import page_settings

        # ~10 EXISTS по таблицам тенанта — до блокировки строки, как в `write`
        gate = page_settings.composition_gate(tenant.site_config or {})
    locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
    config = siteconfig.normalize(locked.site_config)
    if not force and (
        _fingerprint(_saved_state(config, home, host)) != draft.get("base")
        or _keys_conflict(config, draft)
    ):
        raise DraftConflict(code)
    site_schema.store_items(config, home, host, copy.deepcopy(draft["items"]))
    if host == "info" and "contact" in draft:
        if draft["contact"]:
            config.pop("about_contact", None)
        else:
            config["about_contact"] = False
    if _settings(draft):
        # FB-27 R4: настройки типа — в той же транзакции, что блоки; каждая проверяется
        # заново по заблокированной строке. Недопустимая → PageSettingError, ничего не
        # записано, черновик остаётся.
        config = page_settings.apply_many(locked, config, _settings(draft), gate)
    locked.site_config = siteconfig.normalize(config)
    locked.save(update_fields=["site_config", "updated_at"])
    tenant.site_config = locked.site_config
    _put(request, code, None)
    return True


def prune(request, known_codes) -> None:
    """Убрать черновики страниц, которых на экране больше нет (тип выключен, страница
    удалена) — открыть их нельзя, а место в сессии они занимали бы до её конца."""
    known = set(known_codes)
    for code in [c for c in _all(request) if c not in known]:
        _put(request, code, None)
