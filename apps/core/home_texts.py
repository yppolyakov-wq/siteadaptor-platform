"""FB-33 стопка 15 M5e-1a: тексты секций главной — один писатель.

План — `docs/fb33-stack15-plan-2026-11-25.md` §2 «M5e-1», §14.1 A1–A4, A14, A15. Секции:
hero, about, cta, process, team, testimonials, trust, archetypes (подписи тизеров). Ключи
`site_config` и имена полей — те же, что у формы Студии; подписи — msgid Студии.

Пишут только через этот модуль (решение владельца A1): Студия (`put_form`), черновик превью
Студии (`put` с `translating=True` — переводы не трогает, как раньше), правка на канве и мастер
(`set_text`). Осознанные исключения — импорт сайта (`imports/site/apply.py`, `imports/cscart.py`)
и демо-сидеры (`tenants/demo.py`, `demo_kits`): они собирают конфиг целиком (замок
`test_home_texts_writers_ast`).

Правила:
- секция пишется, только если в присланном есть хоть одно её поле; не присланное поле секции
  остаётся как было (старые и чужие формы ничего не стирают);
- потолки — `TITLE_MAX`/`TEXT_MAX`/`LIST_MAX` (решение §9 №4); неизменённое присланное не
  режется; ссылка кнопки — только http(s)/mailto/tel/относительная, иначе остаётся прежняя;
- фото команды едет за именем (A15): форма «Name | Rolle» фото не несёт;
- правка немецкого снимает перевод ИМЕННО этого поля у всех языков (§9 №3); в режиме перевода
  (`translating=True`) — ни выравнивания переводов списков, ни снятия (A2);
- межзапросный писатель (Студия со старой вкладки) несёт отпечаток секции `htx_base_<ключ>`:
  не совпал с сохранённым — секция не пишется (A3), в лог — предупреждение.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging

from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _l

logger = logging.getLogger(__name__)

#: потолки ввода (решение владельца §9 №4): заголовки, тексты, списки «по строке»
TITLE_MAX = 120
TEXT_MAX = 2000
LIST_MAX = 4000
#: ссылка кнопки — как у пунктов меню (`siteconfig._menu_href`)
URL_MAX = 500

LINE, TEXT, LIST, URL = "line", "text", "list", "url"

#: секция → ((имя поля формы Студии, подпись, вид, потолок), …). Источник: из него выводится
#: `siteconfig.CONTENT_FIELDS` (A14). У архетипов имя — префикс, ключ модуля дописывается.
FIELDS = {
    "hero": (
        ("hero_title", _l("Banner heading"), LINE, TITLE_MAX),
        ("hero_text", _l("Banner text"), TEXT, TEXT_MAX),
    ),
    "about": (
        ("about_title", _l("Headline"), LINE, TITLE_MAX),
        ("about_text", _l("Text"), TEXT, TEXT_MAX),
    ),
    "cta": (
        ("cta_title", _l("Headline"), LINE, TITLE_MAX),
        ("cta_text", _l("Text (optional)"), TEXT, TEXT_MAX),
        ("cta_button_label", _l("Button text"), LINE, TITLE_MAX),
        ("cta_button_url", _l("Button link"), URL, URL_MAX),
    ),
    "testimonials": (
        (
            "testimonials_text",
            _l("One per line: Name | Text | Stars 1–5 | Photo URL (both optional)."),
            LIST,
            LIST_MAX,
        ),
    ),
    "process": (("process_text", _l("One step per line: Title | Description."), LIST, LIST_MAX),),
    "team": (("team_text", _l("One per line: Name | Role."), LIST, LIST_MAX),),
    "trust": (
        ("trust_since", _l("Founded in (year)"), LINE, TITLE_MAX),
        ("trust_marks", _l("Credentials (one per line)"), LIST, LIST_MAX),
    ),
    "archetypes": (
        ("arch_label_", _l("Title"), LINE, TITLE_MAX),
        ("arch_blurb_", _l("Description"), TEXT, TEXT_MAX),
    ),
}

#: секции, которые разбирает `siteconfig.parse_content_section` (форма «Studio», сентинел
#: `content_sections_present`)
CONTENT_KEYS = ("cta", "testimonials", "process", "team", "trust")
#: скалярные секции: имя поля = ключ `site_config`
SCALAR_KEYS = ("hero", "about")
#: вложенные словари: имя поля → поле словаря
_NESTED = {
    "cta": {
        "cta_title": "title",
        "cta_text": "text",
        "cta_button_label": "button_label",
        "cta_button_url": "button_url",
    },
    "trust": {"trust_since": "since", "trust_marks": "marks"},
}
#: правка на канве (`views.site_inline_edit`): поле канвы → (секция, имя поля)
INLINE_FIELDS = {
    "hero_title": ("hero", "hero_title"),
    "hero_text": ("hero", "hero_text"),
    "about_title": ("about", "about_title"),
    "about_text": ("about", "about_text"),
    "cta.title": ("cta", "cta_title"),
    "cta.text": ("cta", "cta_text"),
}


def names(key: str) -> tuple[str, ...]:
    return tuple(spec[0] for spec in FIELDS.get(key, ()))


def _spec(key: str, name: str):
    for spec in FIELDS.get(key, ()):
        if spec[0] == name or (key == "archetypes" and name.startswith(spec[0])):
            return spec
    return None


def _s(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _items(value) -> list[dict]:
    return [i for i in value if isinstance(i, dict)] if isinstance(value, list) else []


def _arch_keys(config: dict, tenant) -> list[str]:
    """Ключи тизеров формы: активные архетипы тенанта (`storefront.teaser_specs`)."""
    if tenant is None:
        return []
    from apps.tenants import storefront

    return [spec["key"] for spec in storefront.teaser_specs(tenant)]


# ───────────── чтение: значения формы и отпечаток ─────────────


def values(config: dict, key: str, tenant=None) -> dict:
    """{имя поля: текст} — то, что форма Студии показывает для сохранённого (round-trip)."""
    from apps.tenants import siteconfig

    config = config if isinstance(config, dict) else {}
    if key in SCALAR_KEYS:
        return {name: _s(config.get(name)) for name in names(key)}
    if key == "cta":
        cta = _dict(config.get("cta"))
        return {name: _s(cta.get(field)) for name, field in _NESTED["cta"].items()}
    if key == "trust":
        trust = _dict(config.get("trust"))
        marks = trust.get("marks") if isinstance(trust.get("marks"), list) else []
        return {
            "trust_since": _s(trust.get("since")),
            "trust_marks": "\n".join(_s(m) for m in marks if _s(m)),
        }
    if key == "testimonials":
        return {"testimonials_text": siteconfig.testimonials_to_text(_items(config.get(key)))}
    if key == "process":
        return {"process_text": siteconfig.pairs_to_text(_items(config.get(key)), "title", "text")}
    if key == "team":
        rows = [
            f"{_s(m.get('name'))} | {_s(m.get('role'))}".rstrip(" |")
            for m in _items(config.get(key))
        ]
        return {"team_text": "\n".join(rows)}
    if key == "archetypes":
        arch = _dict(config.get("archetypes"))
        out = {}
        for k in _arch_keys(config, tenant):
            entry = _dict(arch.get(k))
            out[f"arch_label_{k}"] = _s(entry.get("label"))
            out[f"arch_blurb_{k}"] = _s(entry.get("blurb"))
        return out
    return {}


def _stored_part(config: dict, key: str):
    if key in SCALAR_KEYS:
        return [config.get(name) for name in names(key)]
    if key == "archetypes":
        arch = _dict(config.get("archetypes"))
        return {
            k: [_dict(v).get("label"), _dict(v).get("blurb")]
            for k, v in sorted(arch.items(), key=str)
        }
    return config.get(key)


def fingerprint(config: dict, key: str) -> str:
    """Отпечаток сохранённых текстов секции и их переводов (A3: форма несёт его как
    `htx_base_<ключ>`; запись из устаревшей вкладки не возвращает старые тексты)."""
    config = config if isinstance(config, dict) else {}
    stores = names(key) if key in SCALAR_KEYS else (key,)
    overlays = {}
    for loc, node in sorted(_dict(config.get("i18n")).items(), key=str):
        node = _dict(node)
        part = {s: node.get(s) for s in stores if s in node}
        if part:
            overlays[loc] = part
    raw = json.dumps(
        [_stored_part(config, key), overlays], ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]


def fingerprints(config: dict) -> dict:
    return {key: fingerprint(config, key) for key in FIELDS}


# ───────────── запись ─────────────


#: итог `put` (ложный — секции в присланном нет)
WRITTEN, STALE, ABSENT = "written", "stale", ""
#: итог `set_text` (ложный — поля нет в реестре)
CHANGED, UNCHANGED, CAPPED, REJECTED = "changed", "unchanged", "capped", "rejected"


def _nl(value: str) -> str:
    """Переводы строк формы (`\r\n` браузера, старый `\r`) → `\n` — до сверки, потолка и записи."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def stale_note(name) -> str:
    return gettext(
        "Die Texte von „%(name)s“ wurden inzwischen an anderer Stelle geändert – Ihre Änderung "
        "daran wurde nicht übernommen."
    ) % {"name": str(name)}


def url_note(label) -> str:
    return gettext("%(field)s: bitte mit https:// beginnen.") % {"field": str(label)}


def _clean_url(value: str) -> str:
    from apps.tenants import siteconfig

    return siteconfig._menu_href(value)


def _read(key: str, get, current: dict, notes: list | None) -> dict | None:
    """Присланное по полям секции (None — секции в присланном нет). Не присланное поле —
    прежнее; длинное новое режется по потолку; небезопасная ссылка — прежняя."""
    posted = {}
    for name in current:
        value = get(name, None)
        if value is not None:
            posted[name] = value if isinstance(value, str) else str(value)
    if not posted:
        return None
    out = dict(current)
    for name, value in posted.items():
        value = _nl(value).strip()
        old = current.get(name, "")
        if value == _nl(old):
            continue  # неизменённое (в том числе старое длинное или с `\r\n`) — как было
        _name, label, kind, cap = _spec(key, name)
        if len(value) > cap:
            value = value[:cap].strip()
            if notes is not None:
                from apps.tenants import siteconfig

                notes.append(siteconfig.cap_note())
        if kind == URL and value and not _clean_url(value):
            if notes is not None:
                notes.append(url_note(label))
            continue
        out[name] = value
    return out


def _build(config: dict, key: str, raw: dict, tenant=None):
    """Новое значение `site_config` секции из полей формы."""
    from apps.tenants import siteconfig

    if key in SCALAR_KEYS:
        return {name: raw[name] for name in names(key)}
    if key in CONTENT_KEYS:
        new = siteconfig.parse_content_section(key, lambda name, default="": raw.get(name, default))
        if key == "team":
            # A15: форма «Name | Rolle» фото не несёт — фото едет за ИМЕНЕМ (и после перестановки);
            # у двух участников с одним именем оба получат фото первого, новое имя — без фото,
            # переименование теряет фото (его снова ставит загрузчик)
            photos = {}
            for m in _items(config.get("team")):
                photos.setdefault(_s(m.get("name")), _s(m.get("photo")))
            for m in new:
                m["photo"] = photos.get(m["name"], "")
        return new
    if key == "archetypes":
        arch = copy.deepcopy(_dict(config.get("archetypes")))
        for k in _arch_keys(config, tenant):
            label, blurb = f"arch_label_{k}", f"arch_blurb_{k}"
            if label not in raw:
                continue
            entry = dict(_dict(arch.get(k)))
            entry["label"] = raw[label]
            entry["blurb"] = raw[blurb]
            arch[k] = entry
        return arch
    return None


def _drop_node(old, new, ov):
    """Перевод `ov` без полей, чей немецкий текст изменился (None — переводить нечего)."""
    if isinstance(ov, dict) and isinstance(new, dict):
        old = _dict(old)
        out = {}
        for field, tr in ov.items():
            if field not in new:
                out[field] = tr
                continue
            kept = _drop_node(old.get(field), new.get(field), tr)
            if kept is not None:
                out[field] = kept
        return out or None
    if isinstance(new, list) or isinstance(old, list):
        return ov if old == new else None
    return ov if _s(old) == _s(new) else None


def _drop_changed(config: dict, key: str, old, new) -> None:
    """§9 №3: правка немецкого снимает перевод именно изменённого поля у всех языков. Списки
    — после `realign_list_overlays`: перевод пункта j сверяется с пунктом-источником."""
    from apps.tenants import siteconfig

    overlay = config.get("i18n")
    if not isinstance(overlay, dict):
        return
    field = siteconfig.LIST_OVERLAY_KEYS.get(key)
    for node in overlay.values():
        if not isinstance(node, dict):
            continue
        if key in SCALAR_KEYS:
            for name in names(key):
                if name in node and _s(old.get(name)) != _s(new.get(name)):
                    node.pop(name)
            continue
        if key not in node:
            continue
        tr = node[key]
        if field and not (isinstance(tr, list) and isinstance(new, list)):
            logger.warning("home_texts: i18n %s is not a list — translations left as is", key)
            continue
        if field:
            by_key = {}
            for item in _items(old):
                by_key.setdefault(str(item.get(field, "")), item)
            moved = []
            for j, item in enumerate(new):
                entry = tr[j] if j < len(tr) else {}
                src = by_key.get(str(item.get(field, "")))
                if isinstance(entry, dict) and src is not None:
                    entry = _drop_node(src, item, entry) or {}
                moved.append(entry)
            node[key] = moved
            continue
        kept = _drop_node(old, new, tr)
        if kept is None:
            node.pop(key)
        else:
            node[key] = kept


def put(
    config: dict,
    key: str,
    get,
    *,
    translating: bool = False,
    notes: list | None = None,
    tenant=None,
    base_fp: str | None = None,
    stored: dict | None = None,
) -> bool:
    """Записать тексты секции `key` из формы (`get(name, default)` — request.POST.get и т. п.).

    `base_fp` — отпечаток секции, с которым открыта форма; не совпал с `stored` (сохранённое
    на начало запроса) — секция не пишется (`STALE`). `translating` — форма на языке перевода:
    значения ложатся в поля как есть (их разложит `siteconfig.split_translation`), переводы не
    выравниваются и не снимаются. Мутирует `config`; `WRITTEN` — секция записана, `ABSENT` —
    её полей в присланном нет."""
    from apps.tenants import siteconfig

    if key not in FIELDS or not isinstance(config, dict):
        return ABSENT
    if base_fp and stored is not None and base_fp != fingerprint(stored, key):
        from django.db import connection

        logger.warning(
            "home_texts: %s changed meanwhile — stale form not written (%s)",
            key,
            getattr(connection, "schema_name", ""),
        )
        return STALE
    current = values(config, key, tenant)
    raw = _read(key, get, current, notes)
    if raw is None:
        return ABSENT
    new = _build(config, key, raw, tenant)
    if key in SCALAR_KEYS:
        old = {name: config.get(name) for name in names(key)}
        if not translating:
            _drop_changed(config, key, old, new)
        config.update(new)
        return WRITTEN
    old = copy.deepcopy(config.get(key))
    if not translating:
        if key in siteconfig.LIST_OVERLAY_KEYS:
            if not isinstance(old, list):
                logger.warning("home_texts: stored %s is not a list — nothing to realign", key)
            siteconfig.realign_list_overlays(config, {key: new})
        _drop_changed(config, key, old, new)
    config[key] = new
    return WRITTEN


def put_teaser_visibility(config: dict, get, tenant) -> None:
    """Галочка «показывать» тизера архетипа — только у тизеров, чьи поля пришли в форме."""
    arch = _dict(config.get("archetypes"))
    for k in _arch_keys(config, tenant):
        if get(f"arch_label_{k}", None) is None:
            continue
        entry = dict(_dict(arch.get(k)))
        entry["hidden"] = get(f"arch_visible_{k}", None) != "on"
        arch[k] = entry
    config["archetypes"] = arch


def put_form(
    config: dict,
    get,
    keys,
    *,
    stored: dict,
    translating: bool = False,
    notes: list | None = None,
    tenant=None,
) -> tuple[list[str], dict]:
    """Форма Студии: секции `keys`, у каждой — свой отпечаток `htx_base_<ключ>`.

    Форма с сентинелом `htx_base_present` без отпечатка присланной секции — устаревшая
    (секция не пишется); без сентинела (вкладка, открытая до выкладки) — пишется, в лог —
    сведение. Возвращает (пропущенные секции, {записанная секция: отпечаток}) — второе
    сверяет `recheck` под блокировкой строки."""
    stale, written = [], {}
    sentinel = bool(get("htx_base_present", None))
    for key in keys:
        base_fp = _s(get(f"htx_base_{key}", None)) or None
        if base_fp is None and any(
            get(name, None) is not None for name in values(config, key, tenant)
        ):
            if sentinel:
                logger.info("home_texts: %s posted without its fingerprint — not written", key)
                stale.append(key)
                continue
            logger.info("home_texts: %s posted by a form without fingerprints (old tab)", key)
        result = put(
            config,
            key,
            get,
            translating=translating,
            notes=notes,
            tenant=tenant,
            base_fp=base_fp,
            stored=stored,
        )
        if result == STALE:
            stale.append(key)
        elif result == WRITTEN:
            written[key] = base_fp
    return stale, written


def _restore(config: dict, fresh: dict, key: str) -> None:
    """Тексты секции и их переводы — как в свежей строке (секция не пишется этой формой)."""
    stores = names(key) if key in SCALAR_KEYS else (key,)
    for name in stores:
        if name in fresh:
            config[name] = copy.deepcopy(fresh[name])
        else:
            config.pop(name, None)
    fresh_i18n = _dict(fresh.get("i18n"))
    mine = config.get("i18n")
    if not isinstance(mine, dict):
        mine = {}
    for loc in set(mine) | set(fresh_i18n):
        node = dict(_dict(mine.get(loc)))
        src = _dict(fresh_i18n.get(loc))
        for name in stores:
            if name in src:
                node[name] = copy.deepcopy(src[name])
            else:
                node.pop(name, None)
        if node:
            mine[loc] = node
        else:
            mine.pop(loc, None)
    if mine:
        config["i18n"] = mine
    else:
        config.pop("i18n", None)


def recheck(config: dict, fresh: dict, stale, written: dict) -> list[str]:
    """Под блокировкой строки (A3, без гонки): секция, записанная по отпечатку, который уже не
    совпадает со свежей строкой, и пропущенные секции — как в свежей строке. Возвращает
    секции, ставшие устаревшими только сейчас."""
    late = []
    for key, base_fp in written.items():
        if base_fp and base_fp != fingerprint(fresh, key):
            logger.warning("home_texts: %s changed while saving — stale form not written", key)
            _restore(config, fresh, key)
            late.append(key)
    for key in stale:
        _restore(config, fresh, key)
    return late


def _path(key: str, name: str) -> tuple:
    if key in _NESTED:
        return (key, _NESTED[key][name])
    return (name,)


def set_text(config: dict, key: str, name: str, value, locale: str = "") -> str:
    """Одно поле (канва, мастер). На языке перевода — перевод этого поля; на основном — база
    тем же путём, что `put` (потолки, ссылка, снятие перевода изменённого поля). Итог —
    `CHANGED`, `UNCHANGED`, `CAPPED` (записано обрезанным) или `REJECTED` (небезопасная ссылка,
    не записано); "" — поля нет в реестре (списки и архетипы так не пишутся)."""
    from apps.tenants import siteconfig

    if key not in SCALAR_KEYS and key not in _NESTED:
        return ""
    spec = _spec(key, name)
    if spec is None or spec[2] == LIST:
        return ""
    value = _nl(_s(value))
    if locale:
        if spec[2] == URL and value and not _clean_url(value):
            return REJECTED
        result = CHANGED
        if len(value) > spec[3]:
            value = value[: spec[3]].strip()
            result = CAPPED
        siteconfig.set_overlay_value(config, locale, _path(key, name), value)
        return result
    before = values(config, key)
    current = dict(before)
    current[name] = value
    notes: list = []
    put(config, key, current.get, notes=notes)
    if url_note(spec[1]) in notes:
        return REJECTED
    if siteconfig.cap_note() in notes:
        return CAPPED
    return UNCHANGED if values(config, key) == before else CHANGED
