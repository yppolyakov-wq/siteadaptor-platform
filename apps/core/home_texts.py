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

from django.utils.translation import gettext, gettext_lazy

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
        ("hero_title", gettext_lazy("Banner heading"), LINE, TITLE_MAX),
        ("hero_text", gettext_lazy("Banner text"), TEXT, TEXT_MAX),
    ),
    "about": (
        ("about_title", gettext_lazy("Headline"), LINE, TITLE_MAX),
        ("about_text", gettext_lazy("Text"), TEXT, TEXT_MAX),
    ),
    "cta": (
        ("cta_title", gettext_lazy("Headline"), LINE, TITLE_MAX),
        ("cta_text", gettext_lazy("Text (optional)"), TEXT, TEXT_MAX),
        ("cta_button_label", gettext_lazy("Button text"), LINE, TITLE_MAX),
        ("cta_button_url", gettext_lazy("Button link"), URL, URL_MAX),
    ),
    "testimonials": (
        (
            "testimonials_text",
            gettext_lazy("One per line: Name | Text | Stars 1–5 | Photo URL (both optional)."),
            LIST,
            LIST_MAX,
        ),
    ),
    "process": (
        ("process_text", gettext_lazy("One step per line: Title | Description."), LIST, LIST_MAX),
    ),
    "team": (("team_text", gettext_lazy("One per line: Name | Role."), LIST, LIST_MAX),),
    "trust": (
        ("trust_since", gettext_lazy("Founded in (year)"), LINE, TITLE_MAX),
        ("trust_marks", gettext_lazy("Credentials (one per line)"), LIST, LIST_MAX),
    ),
    "archetypes": (
        ("arch_label_", gettext_lazy("Title"), LINE, TITLE_MAX),
        ("arch_blurb_", gettext_lazy("Description"), TEXT, TEXT_MAX),
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
    """Ключи тизеров формы: активные архетипы тенанта (`storefront.teaser_specs`). M5e-1b:
    вместо тенанта — готовый список ключей (черновик окна знает их по своим полям)."""
    if isinstance(tenant, (list, tuple)):
        return list(tenant)
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
    return ov if _same(old, new) else None


def _same(old, new) -> bool:
    """Немецкий текст не менялся: сверка после `_nl` (стопка 16 T1a, architect №11: `\r\n` из
    формы не снимает перевод ложно)."""
    return _nl(_s(old)) == _nl(_s(new))


def drop_changed(config: dict, key: str, old, new, aligned: list | None = None) -> None:
    """§9 №3: правка немецкого снимает перевод именно изменённого поля у всех языков. Списки
    — после `realign_list_overlays`: перевод пункта j сверяется с пунктом-источником.
    `aligned` (стопка 16 T1a, полоса доверия окна) — пункт-источник для каждого нового пункта
    уже известен (по месту в сохранённом списке, а не по ключу: ключ пункта — сам переводимый
    текст); `None` в нём — новый пункт."""
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
                if name in node and not _same(old.get(name), new.get(name)):
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
                if aligned is not None:
                    src = aligned[j] if j < len(aligned) else None
                else:
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
    window: bool = False,
    window_tr: dict | None = None,
) -> bool:
    """Записать тексты секции `key` из формы (`get(name, default)` — request.POST.get и т. п.).

    `base_fp` — отпечаток секции, с которым открыта форма; не совпал с `stored` (сохранённое
    на начало запроса) — секция не пишется (`STALE`). `translating` — форма на языке перевода:
    значения ложатся в поля как есть (их разложит `siteconfig.split_translation`), переводы не
    выравниваются и не снимаются. `window` (стопка 16 T6, окно блока: показ и «Speichern»
    черновика) — пункты списков узнаются правилом D9 (`item_src`: дубли по порядку, переименование
    по месту), `window_tr` — переводы пунктов из окна ({язык: {место в сохранённом: {поле:
    текст}}}), ложатся за своим пунктом. Мутирует `config`; `WRITTEN` — секция записана,
    `ABSENT` — её полей в присланном нет."""
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
            drop_changed(config, key, old, new)
        config.update(new)
        return WRITTEN
    old = copy.deepcopy(config.get(key))
    if window and not translating and key in ITEM_FIELDS:
        src = _realign_items(config, key, old, new)
        config[key] = new
        if window_tr:
            from apps.core import block_i18n

            block_i18n.put_items(config, key, src, window_tr)
        return WRITTEN
    if not translating:
        if key in siteconfig.LIST_OVERLAY_KEYS:
            if not isinstance(old, list):
                logger.warning("home_texts: stored %s is not a list — nothing to realign", key)
            siteconfig.realign_list_overlays(config, {key: new})
        drop_changed(config, key, old, new)
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


# ───────────── FB-33 стопка 15 M5e-1b: окно блока «Seitenaufbau», вкладка «Texte» ─────────────
# Окно — второй вход к тем же данным: те же имена полей, тот же писатель (`put`). Правка — в
# черновик страницы (`aufbau_draft`: `htx` = {секция: {имя поля Студии: текст}}, `htx_base` =
# {секция: отпечаток сохранённого на первой правке}); «Speichern» пишет `commit` под
# блокировкой строки. Пункты списков (шаги, команда, отзывы) — отдельными полями
# `htx_<секция>_<i>_<поле>`, собираются в ту же строку «A | B», что у Студии.

DRAFT_KEYS = ("htx", "htx_base")
#: пункт списка: (поле пункта, подпись) — подписи уже есть в каталогах (`Name`, `Titel`, …)
ITEM_FIELDS = {
    "process": (("title", gettext_lazy("Titel")), ("text", gettext_lazy("Text"))),
    "team": (("name", gettext_lazy("Name")), ("role", gettext_lazy("Rolle"))),
    "testimonials": (("text", gettext_lazy("Zitat")), ("name", gettext_lazy("Name"))),
}
#: поле пункта, без которого пункта нет (как у Студии: строка без первой части пропадает)
_ITEM_KEY = {"process": "title", "team": "name", "testimonials": "name"}
#: стопка 16 T6 (решение владельца 2026-11-26): переводимые в окне поля пункта — шаг: Titel и
#: Text, команда: Rolle, отзыв: Zitat; имена людей не переводятся (как `PROPER_NAMES` демо)
TR_ITEM_FIELDS = {"process": ("title", "text"), "team": ("role",), "testimonials": ("text",)}
ITEM_LEGENDS = {
    "process": gettext_lazy("Schritt %(n)s"),
    "team": gettext_lazy("Mitglied %(n)s"),
    "testimonials": gettext_lazy("Stimme %(n)s"),
}
#: переводимые в окне поля (кнопки языка — `block_i18n`): тексты, не ссылки и не списки
_TR_KINDS = (LINE, TEXT)
#: сессия: ошибка поля окна после отказа (Y1: у поля, набранное видно; один раз)
ERROR_KEY = "aufbau_htx_error"


def hero_from_banner(choice) -> bool:
    """Баннер главной показывает баннер библиотеки, а не свои заголовок и текст главной — тот
    же предикат, что у витрины (`siteui.hero_slides` → `siteui.hero_lead`): выбран и сегодня
    активен. Выбран, но выключен или вне срока — витрина показывает тексты главной."""
    choice = _dict(choice)
    if not choice.get("pick"):
        return False
    from apps.tenants.templatetags import siteui

    slides = siteui.hero_slides({}, [], choice)
    return bool(siteui.hero_lead({"hero_banners": choice}, slides)["from_banner"])


def has_texte(row: dict | None, config: dict | None = None) -> bool:
    """Одно правило «у строки есть «Texte» секции главной» — для окна (`window_key`),
    переводов (`block_i18n.kinds`) и правки (`aufbau_draft.is_htx_edit`). Выбор баннеров —
    из строки (черновик и сохранённое несут его в `data`, строка окна — в `banner_choice`)."""
    if not isinstance(row, dict) or row.get("id") or row.get("key") not in FIELDS:
        return False
    if row["key"] != "hero":
        return True
    if isinstance(row.get("data"), dict):
        choice = row["data"]
    elif isinstance(row.get("banner_choice"), dict):
        choice = row["banner_choice"]
    else:
        choice = (config or {}).get("hero_banners")
    return not hero_from_banner(choice)


def window_key(row: dict | None, config: dict, tenant=None) -> str:
    """Секция главной, у окна которой есть «Texte» ("" — нет): `has_texte` и, у «Unser
    Angebot», хоть один тизер у бизнеса."""
    if not has_texte(row, config):
        return ""
    key = row["key"]
    if key == "archetypes" and not _arch_keys(config, tenant):
        return ""
    return key


def no_change_note() -> str:
    return gettext("Diese Änderung ist hier nicht möglich.")


def clean_htx(draft: dict | None) -> dict:
    """Тексты черновика, которые можно показать и записать: {секция реестра: {имя: текст}}.
    Остальное (чужой ключ, не словарь — старый или испорченный черновик) — в лог."""
    raw = (draft or {}).get("htx")
    if not isinstance(raw, dict):
        if raw is not None:
            logger.warning("home_texts: draft htx is not a dict — ignored")
        return {}
    out = {}
    for key, entry in raw.items():
        if key in FIELDS and isinstance(entry, dict):
            out[key] = {n: v for n, v in entry.items() if isinstance(v, str)}
        else:
            logger.warning("home_texts: draft htx entry %r ignored", key)
    return out


def dropped(draft: dict | None) -> bool:
    raw = (draft or {}).get("htx")
    return isinstance(raw, dict) and len(clean_htx(draft)) != len(raw)


def pending(draft: dict | None, key: str) -> dict | None:
    htx = (draft or {}).get("htx")
    entry = htx.get(key) if isinstance(htx, dict) else None
    return dict(entry) if isinstance(entry, dict) else None


def arch_keys_of(entry: dict) -> list[str]:
    """Ключи тизеров по полям записи черновика (`arch_label_<ключ>`)."""
    return [n[len("arch_label_") :] for n in entry if n.startswith("arch_label_")]


def state(config: dict, key: str, draft: dict | None, tenant=None) -> dict:
    """Тексты секции, которые видит окно: черновика, иначе сохранённые."""
    mine = pending(draft, key)
    return mine if mine is not None else values(config, key, tenant)


def items(key: str, entry: dict) -> list[dict]:
    """Пункты списка из записи формы (тем же разбором, что у Студии)."""
    from apps.tenants import siteconfig

    return siteconfig.parse_content_section(key, lambda n, d="": entry.get(n, d))


def item_src(key: str, new_items, old_items) -> list:
    """Стопка 16 T6: место в сохранённом списке для каждого пункта окна (`None` — новый). Ключ
    пункта — `_ITEM_KEY` (сам переводимый текст у шага); одно правило D9
    `siteconfig._match_items`: две «Anna» — k-я ↔ k-й, переименование при той же длине — по
    месту, добавление и удаление — только по ключу."""
    from apps.tenants import siteconfig

    field = _ITEM_KEY[key]
    old = old_items if isinstance(old_items, list) else []
    return siteconfig._match_items(
        [siteconfig._item_identity(_dict(it), field) for it in new_items or ()],
        [[siteconfig._item_identity(_dict(it), field)] for it in old],
        by_place=True,
    )


def window_items(config: dict, key: str, draft: dict | None) -> tuple[list, list]:
    """Пункты секции, которые видит окно, и место каждого в сохранённом списке (`item_src`)."""
    win = items(key, state(config, key, draft))
    return win, item_src(key, win, config.get(key))


def _realign_items(config: dict, key: str, old, new: list) -> list:
    """Переводы пунктов — за своим пунктом (`item_src`), удалённый уносит свои, у нового их нет;
    перевод поля, чей немецкий текст изменился, снимается (`drop_changed` с `aligned`)."""
    old = old if isinstance(old, list) else []
    src = item_src(key, new, old)
    overlay = config.get("i18n")
    if not isinstance(overlay, dict):
        return src
    for node in overlay.values():
        if not isinstance(node, dict) or key not in node:
            continue
        tr = node[key]
        if not isinstance(tr, list):
            continue  # `drop_changed` предупредит в лог
        node[key] = [
            copy.deepcopy(tr[s])
            if isinstance(s, int) and s < len(tr) and isinstance(tr[s], dict)
            else {}
            for s in src
        ]
    aligned = [
        old[s] if isinstance(s, int) and s < len(old) and isinstance(old[s], dict) else None
        for s in src
    ]
    drop_changed(config, key, old, new, aligned=aligned)
    for node in overlay.values():
        rows = node.get(key) if isinstance(node, dict) else None
        if not isinstance(rows, list):
            continue
        while rows and rows[-1] in ({}, None):
            rows.pop()
        if not rows:
            node.pop(key)
    return src


def _window_tr(draft: dict, key: str) -> dict:
    from apps.core import block_i18n

    return block_i18n.explicit_items(draft, key) if key in ITEM_FIELDS else {}


def _item_text(value) -> str:
    # «|» — разделитель строки формы Студии: внутри поля пункта он разрезал бы пункт
    return " ".join(_nl(value if isinstance(value, str) else "").split()).replace("|", "/")


def _window_get(key: str, fields: dict, current: dict):
    """Поля окна → `get` формы Студии. Пункты — `htx_<ключ>_<i>_<поле>`; поле, которого нет в
    присланном, — прежнее (у отзыва звёзды и фото окно не правит — по номеру пункта)."""
    if key not in ITEM_FIELDS:
        return lambda name, default=None: fields.get(name, default)
    old = items(key, current)
    rows = []
    for i in range(len(old) + 1):
        src = old[i] if i < len(old) else {}
        got = {field: fields.get(f"htx_{key}_{i}_{field}") for field, _label in ITEM_FIELDS[key]}
        if all(v is None for v in got.values()):
            if src:
                rows.append(src)
            continue
        row = dict(src)
        for field, value in got.items():
            if value is not None:
                row[field] = _item_text(value)
        if row.get(_ITEM_KEY[key]):
            rows.append(row)
    if key == "process":
        text = "\n".join(f"{r.get('title', '')} | {r.get('text', '')}".rstrip(" |") for r in rows)
    elif key == "team":
        text = "\n".join(f"{r.get('name', '')} | {r.get('role', '')}".rstrip(" |") for r in rows)
    else:
        from apps.tenants import siteconfig

        text = siteconfig.testimonials_to_text(rows)
    name = names(key)[0]
    return lambda n, default=None: text if n == name else default


def window_op(
    config: dict, draft: dict, key: str, fields: dict, notes: list | None, tenant=None, session=None
) -> None:
    """Форма «Texte» окна → черновик. Отпечаток формы (`htx_fp`) не совпал с сохранённым при
    первой правке — отказ с заметкой; небезопасная ссылка — ошибка у поля (Y1)."""
    saved = values(config, key, tenant)
    current = state(config, key, draft, tenant)
    if pending(draft, key) is None and _s(fields.get("htx_fp")) != fingerprint(config, key):
        # ревью D: форма без отпечатка (или со старым) до первой правки — не знаем, с чего
        # её открыли: отказ, как у устаревшей вкладки
        if notes is not None:
            notes.append(stale_note(section_label(key)))
        return
    said: list = []
    raw = _read(key, _window_get(key, fields, current), current, said)
    if raw is None:
        logger.info("home_texts: window form of %s carried no fields", key)
        if notes is not None:
            notes.append(no_change_note())
        return
    for spec in FIELDS[key]:
        if spec[2] != URL:
            continue
        note = url_note(spec[1])
        if note in said and session is not None:
            session[ERROR_KEY] = {
                "key": key,
                "name": spec[0],
                "value": _s(fields.get(spec[0]))[:URL_MAX],
                "msg": note,
            }
    if notes is not None:
        notes.extend(said)
    htx = dict(draft.get("htx") or {}) if isinstance(draft.get("htx"), dict) else {}
    base = dict(draft.get("htx_base") or {}) if isinstance(draft.get("htx_base"), dict) else {}
    if raw == saved:
        htx.pop(key, None)
        base.pop(key, None)
    else:
        htx[key] = raw
        base.setdefault(key, fingerprint(config, key))
    if htx:
        draft["htx"], draft["htx_base"] = htx, base
    else:
        for k in DRAFT_KEYS:
            draft.pop(k, None)


def section_label(key: str) -> str:
    from apps.tenants import siteconfig

    labels = {k: label for k, label, _default in siteconfig.SECTIONS}
    return str(labels.get(key, key))


def conflicts(config: dict, draft: dict) -> list[str]:
    """Секции черновика, чьи тексты изменили в другом месте после первой правки (Студия, канва)."""
    htx = clean_htx(draft)
    base = draft.get("htx_base") if isinstance(draft.get("htx_base"), dict) else {}
    return [k for k in htx if base.get(k) != fingerprint(config, k)]


def put_shown(config: dict, draft: dict) -> None:
    """Показ черновика (окно, «Vorschau»): тем же писателем, что «Speichern»."""
    moved = conflicts(config, draft)
    for key, entry in clean_htx(draft).items():
        tr = None if key in moved else _window_tr(draft, key)
        put(config, key, entry.get, tenant=arch_keys_of(entry), window=True, window_tr=tr)


def commit(
    config: dict, draft: dict, force: bool, notes: list | None = None, *, home: bool = True
) -> None:
    """«Speichern» (под блокировкой, после проверки `conflicts`): тексты секций — писателем
    `put`; запись поверх изменённого в другом месте (force) — в лог. Не главная, секции нет
    среди строк черновика, испорченная запись — не пишется, заметка и лог (не молча)."""
    htx = clean_htx(draft)
    skipped = dropped(draft)
    if not home:
        if htx or skipped:
            logger.warning("home_texts: htx in a draft of another page — not written")
            if notes is not None:
                notes.append(no_change_note())
        return
    rows = {
        it.get("key")
        for it in draft.get("items") or ()
        if isinstance(it, dict) and not it.get("id")
    }
    for key in [k for k in htx if k not in rows]:
        logger.warning("home_texts: section %s is not on the page — texts not written", key)
        htx.pop(key)
        skipped = True
    if skipped and notes is not None:
        notes.append(no_change_note())
    moved = conflicts(config, draft)
    if moved and force:
        from django.db import connection

        logger.warning(
            "home_texts: %s changed meanwhile — written over (%s)",
            ",".join(moved),
            getattr(connection, "schema_name", ""),
        )
    for key, entry in htx.items():
        tr = _window_tr(draft, key)
        if tr and key in moved:
            # стопка 16 T6: места пунктов — от списка, который тем временем изменили
            logger.warning(
                "home_texts: %s changed meanwhile — window item translations skipped", key
            )
            if notes is not None:
                from apps.core import block_i18n

                notes.append(block_i18n.window_skipped_note())
            tr = None
        put(
            config,
            key,
            entry.get,
            notes=notes,
            tenant=arch_keys_of(entry),
            window=True,
            window_tr=tr,
        )


def snapshot(proto: dict, source: dict, key: str) -> None:
    """Прообраз текстов секции окна — для «Abbrechen» (только своей секции)."""
    proto["htx_ref"] = {
        "key": key,
        "val": pending(source, key),
        "base": (source.get("htx_base") or {}).get(key)
        if isinstance(source.get("htx_base"), dict)
        else None,
    }


def revert(draft: dict, proto: dict) -> None:
    entry = proto.get("htx_ref")
    if not isinstance(entry, dict) or not entry.get("key"):
        return
    key = entry["key"]
    htx = dict(draft.get("htx") or {}) if isinstance(draft.get("htx"), dict) else {}
    base = dict(draft.get("htx_base") or {}) if isinstance(draft.get("htx_base"), dict) else {}
    if isinstance(entry.get("val"), dict):
        htx[key] = copy.deepcopy(entry["val"])
        base[key] = entry.get("base")
    else:
        htx.pop(key, None)
        base.pop(key, None)
    if htx:
        draft["htx"], draft["htx_base"] = htx, base
    else:
        for k in DRAFT_KEYS:
            draft.pop(k, None)


def _field(spec, value: str, ident: str, error: dict | None) -> dict:
    name, label, kind, cap = spec
    err = error if error and error.get("name") == name else None
    fmt = f"{ident}-fmt" if kind == URL else ""
    return {
        "name": name,
        "label": str(label),
        "kind": kind,
        "value": err["value"] if err else value,
        "id": ident,
        # Y1/§9 №4: потолок — атрибутом, но старое длинное значение им не режется
        "max": cap if len(value) <= cap and kind != LIST else "",
        "error": err["msg"] if err else "",
        # E: формат ссылки — видимой подсказкой (тот же msgid, что у кнопки-блока)
        "fmt": gettext("z. B. /kontakt oder https://…") if fmt else "",
        "described": " ".join(x for x in (f"{ident}-err" if err else "", fmt) if x),
    }


def decorate(
    selected: dict | None, saved: dict, draft: dict | None, home: bool, tenant=None, session=None
) -> None:
    """Модель части «hometext» окна (`selected["home_texts"]`); у прочих строк — ничего."""
    if not selected or not home:
        return
    key = window_key(selected, saved, tenant)
    if not key:
        return
    error = session.pop(ERROR_KEY, None) if session is not None else None
    if not isinstance(error, dict) or error.get("key") != key:
        error = None
    current = state(saved, key, draft, tenant)
    fields, groups = [], []
    if key in ITEM_FIELDS:
        rows = items(key, current)
        for i, row in enumerate([*rows, {}]):
            groups.append(
                {
                    "i": i,  # стопка 16 T6: позиция пункта в окне (поля перевода — `block_i18n`)
                    # E: пустой пункт для нового — с меткой в легенде (не только пустотой)
                    "legend": str(ITEM_LEGENDS[key]) % {"n": i + 1}
                    + (
                        f" – {gettext('neu – leer lassen, wenn nicht benötigt')}"
                        if i == len(rows)
                        else ""
                    ),
                    "fields": [
                        {
                            "name": f"htx_{key}_{i}_{field}",
                            "label": str(label),
                            "kind": TEXT if field == "text" else LINE,
                            "value": _s(row.get(field)),
                            "id": f"schema-f-htx_{key}_{i}_{field}",
                            "max": TEXT_MAX if field == "text" else TITLE_MAX,
                            "error": "",
                            "fmt": "",
                            "described": "",
                        }
                        for field, label in ITEM_FIELDS[key]
                    ],
                }
            )
    elif key == "archetypes":
        from apps.tenants import storefront

        for spec in storefront.teaser_specs(tenant):
            k = spec["key"]
            group = []
            for prefix, label, kind, cap in FIELDS["archetypes"]:
                name = f"{prefix}{k}"
                group.append(
                    _field(
                        (name, label, kind, cap), current.get(name, ""), f"schema-f-{name}", error
                    )
                )
            groups.append({"legend": str(spec["default_label"]), "fields": group})
    else:
        for spec in FIELDS[key]:
            fields.append(_field(spec, current.get(spec[0], ""), f"schema-f-{spec[0]}", error))
    first = next(iter([*fields, *(x for g in groups for x in g["fields"])]), None)
    if first is not None:  # E: общая подсказка — у первого поля, не у каждого
        first["described"] = " ".join(x for x in ("bw-htx-hint", first["described"]) if x)
    selected["home_texts"] = {
        "key": key,
        "fields": fields,
        "groups": groups,
        "fp": fingerprint(saved, key),
    }


def translatable(key: str, name: str) -> bool:
    """Поле, перевод которого правится в окне (кнопки языка `block_i18n`)."""
    spec = _spec(key, name)
    return spec is not None and spec[2] in _TR_KINDS


def tr_path(key: str, name: str) -> tuple:
    """Путь перевода поля в `i18n[<язык>]` (зеркало базы, `siteconfig.set_overlay_value`)."""
    if key == "archetypes":
        for prefix in ("arch_label_", "arch_blurb_"):
            if name.startswith(prefix):
                return (
                    "archetypes",
                    name[len(prefix) :],
                    "label" if "label" in prefix else "blurb",
                )
    return _path(key, name)
