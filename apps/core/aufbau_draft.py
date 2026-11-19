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
    from apps.core import page_title

    if host in page_title.HEAD_HOSTS:
        # FB-33 M2d: «Seitentitel» — часть страницы в черновике (правка в другом месте —
        # конфликт, возврат к сохранённому — черновика нет)
        state["title"] = page_title.clean_one((config.get("page_titles") or {}).get(host))
    from apps.core import detail_parts

    if detail_parts.object_kind(host):
        # R8: разделы объекта живут в нём самом — их правка в другом месте (вкладка
        # карточки, другая вкладка браузера) тоже конфликт черновика
        obj = detail_parts.object_for_host(host)
        state["override"] = getattr(obj, "page_override", None) or {}
    return state


def _has_section_rows(draft: dict) -> bool:
    from apps.core import detail_parts

    keys = set(detail_parts.section_keys(str(draft.get("host") or "")))
    return any(
        isinstance(r, dict) and r.get("key") in keys and not r.get("id")
        for r in draft.get("items") or []
    )


def _base_fingerprint(saved: dict, config: dict, draft: dict) -> str:
    """Отпечаток сохранённого состояния в форме черновика: черновик «Über uns», начатый до
    строк разделов (FB-32 S6a), считал отпечаток с карточкой контактов отдельным ключом — иначе
    чистый черновик выглядел бы конфликтом."""
    if draft.get("host") == "info" and "contact" in draft and not _has_section_rows(draft):
        saved = {**saved, "contact": config.get("about_contact") is not False}
    return _fingerprint(saved)


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
    from apps.core import page_settings

    pending = draft.get("settings")
    if not isinstance(pending, dict):
        return {}
    # FB-31 P2 (ревью): общие настройки правятся на «Design» — черновик, начатый до
    # переноса, их не пишет и не показывает (в панели их больше не отменить)
    return {k: v for k, v in pending.items() if k not in page_settings.DESIGN_SETTINGS}


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
        site_schema.lift_hero_choice(out, items)  # FB-29.2: выбор баннеров главной
        out["sections"] = items
    elif host:
        from apps.core import detail_parts

        if detail_parts.module_of(host):  # FB-31 P5: порядок/видимость разделов — на место
            items = detail_parts.lift(out, host, items)
        elif detail_parts.object_kind(host):
            # R8: разделы объекта — в служебный ключ превью (на сайт он не попадает)
            items, state = detail_parts.object_lift(out, host, items)
            if state is not None:
                from apps.core import object_structure

                obj = detail_parts.object_for_host(host)
                module = detail_parts.module_of(detail_parts.shared_host(host))
                drafts = dict(out.get(object_structure.DRAFT_KEY) or {})
                drafts[obj.pk.hex] = object_structure.schema_value(obj, module, state)
                out[object_structure.DRAFT_KEY] = drafts
        page_blocks = dict(out.get("page_blocks") or {})
        page_blocks[host] = items
        out["page_blocks"] = page_blocks
    if host == "info" and "contact" in draft and not _has_section_rows(draft):
        # FB-32 S6a: черновик, начатый до строк разделов, — карточка контактов как раньше
        if draft["contact"]:
            out.pop("about_contact", None)
        else:
            out["about_contact"] = False
    if "title" in draft:
        _put_title(out, host, draft["title"])
    return _apply_settings(out, draft)


def _put_title(config: dict, host: str, title) -> None:
    """FB-33 M2d: «Seitentitel» страницы `host` — в `page_titles` (пусто — ключа нет)."""
    from apps.core import page_title

    titles = dict(config.get("page_titles") or {})
    entry = page_title.clean_one(title)
    if entry:
        titles[host] = entry
    else:
        titles.pop(host, None)
    if titles:
        config["page_titles"] = titles
    else:
        config.pop("page_titles", None)


#: поля вида строки/★, каждое изменение которых — правка черновика
_VIEW_FIELDS = ("style", "grid", "grouping", "focus")


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
    # FB-30.16 (ревью R4): вид блоков каталога (вид «Kategorien», вид/сетка ★)
    count += sum(
        1
        for k in common
        # FB-31 P3 (ревью R5): и абзацы ★ «Aktionen», и «Im Fokus»
        if tuple(old[k].get(f) for f in _VIEW_FIELDS) != tuple(new[k].get(f) for f in _VIEW_FIELDS)
    )
    if [k for k in old if k in new] != common:
        count += 1
    if (
        "contact" in draft
        and not _has_section_rows(draft)
        and bool(draft["contact"]) != bool(saved.get("contact", True))
    ):
        count += 1
    # FB-33 M2d: «Seitentitel» — одно изменение
    if "title" in draft and draft["title"] != saved.get("title", {}):
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
        "conflict": _base_fingerprint(saved, config, draft) != draft.get("base")
        or _keys_conflict(config, draft),
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
    if (
        op_name in ("add", "add_row", "adopt")
        and host.startswith(siteconfig.CATEGORY_HOST_PREFIX)
        and siteconfig.category_hosts_full(config, host)
    ):
        raise site_schema.SchemaError("hosts")
    elif (
        op_name in ("add", "add_row")
        and siteconfig.is_object_host(host)
        and siteconfig.object_hosts_full(config, host)
        and not _room_after_purge(tenant, host)
    ):
        raise site_schema.SchemaError("objects")
    elif op_name in ("adopt", "reset"):
        # FB-27 R7: своя схема категории — взять блоки каталога или вернуться к ним.
        draft["items"] = site_schema.category_items(config, host, draft["items"], op_name)
        ref = ""
    elif ref == site_schema.TITLE_REF:
        # FB-33 M2d: «Seitentitel» — не строка `page_blocks`: тексты и вид — в черновике
        ref = site_schema.title_op(host, draft, op_name, fields)
    else:
        ref = site_schema.mutate(
            draft["items"],
            code,
            op_name,
            ref,
            block_type,
            value,
            fields,
            config.get("block_templates"),
        )
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
        _base_fingerprint(_saved_state(config, home, host), config, draft) != draft.get("base")
        or _keys_conflict(config, draft)
    ):
        raise DraftConflict(code)
    site_schema.store_items(config, home, host, copy.deepcopy(draft["items"]))
    _commit_object(config, host, draft["items"], getattr(request, "user", None))
    if "title" in draft:
        _put_title(config, host, draft["title"])
    if host == "info" and "contact" in draft and not _has_section_rows(draft):
        # FB-32 S6a: черновик, начатый до строк разделов, — карточка контактов как раньше
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


#: R8 (ревью безопасности): разделы страницы объекта — то же право, что у формы объекта
OBJECT_EDIT_VIEWS = {
    "product": "catalog:product-edit",
    "service": "booking:service-edit",
    "stay": "stays:unit-edit",
    "event": "events:edit",
    "tour": "events:tour-edit",
}


def _commit_object(config: dict, host: str, items: list[dict], user=None) -> None:
    """R8: разделы схемы объекта — в его `page_override` (в транзакции `commit`, после
    блокировки строки бизнеса — тот же порядок блокировок везде). Состояние считается по
    объекту, заблокированному здесь же (ревью: вкладка карточки могла успеть записать)."""
    from apps.core import detail_parts, object_structure, view_perms

    kind = detail_parts.object_kind(host)
    if not kind:
        return
    obj = detail_parts.object_for_host(host)
    if obj is None:
        return  # объект удалили, пока шла правка — блоки сохранены, разделов больше нет
    locked = type(obj).objects.select_for_update().filter(pk=obj.pk).first()
    if locked is None:
        return
    _rows, state = detail_parts.object_lift(config, host, copy.deepcopy(items), obj=locked)
    if state is None:
        return
    module = detail_parts.module_of(detail_parts.shared_host(host))
    value = object_structure.schema_value(locked, module, state)
    if value == object_structure._raw(locked):
        return
    if user is not None and not view_perms.allowed(user, OBJECT_EDIT_VIEWS[kind], "POST"):
        # сотрудник с правом на сайт, но без права на этот объект: разделы не меняет
        raise site_schema.SchemaError("rights")
    locked.page_override = value
    fields = ["page_override"]
    if any(f.name == "updated_at" for f in locked._meta.concrete_fields):
        fields.append("updated_at")  # как у формы объекта (sitemap, портал)
    locked.save(update_fields=fields)


def _room_after_purge(tenant, host) -> bool:
    """FB-29.4b: места для своих блоков объекта нет — сначала убрать блоки удалённых
    объектов (хосты-призраки), затем проверить ещё раз."""
    from apps.core import object_structure
    from apps.tenants import siteconfig

    if not object_structure.purge_ghost_hosts(tenant):
        return False
    tenant.refresh_from_db(fields=["site_config"])
    return not siteconfig.object_hosts_full(siteconfig.normalize(tenant.site_config), host)


def prune(request, known_codes) -> None:
    """Убрать черновики страниц, которых на экране больше нет (тип выключен, страница
    удалена) — открыть их нельзя, а место в сессии они занимали бы до её конца."""
    known = set(known_codes)
    for code in [c for c in _all(request) if c not in known]:
        _put(request, code, None)
