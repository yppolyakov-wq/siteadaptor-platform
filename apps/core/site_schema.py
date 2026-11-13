"""FB-25: «Website › Seitenaufbau» — схема блоков каждого типа страницы витрины.

Чтение: типы страниц реестра Студии (`studio_pages.PAGE_TYPES`), у каждого — список блоков
(главная — `sections`, прочие — `page_blocks[<хост>]` с маркером «★ Hauptliste»).
Правка (FB-25b, решение владельца 2026-11-07): показать/скрыть, выше/ниже, удалить, добавить
блок. Пишет ТОЛЬКО `sections` или один хост `page_blocks` (targeted-write W9-3) под
блокировкой строки тенанта; переводы C-блоков выравниваются по личности блока
(`siteconfig.realign_block_overlays`, иначе перестановка сдвинула бы их на чужой блок).
Тонкие настройки блока — в Студии («In Studio bearbeiten»).
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import studio_pages

#: Типы, у которых нет своей страницы без параметра — превью строим по первой записи.
_SAMPLES = {
    "product": ("apps.catalog.models", "Product", {"is_active": True}),
    "category": ("apps.catalog.models", "Category", {"is_active": True}),
}


@dataclass
class PageRow:
    code: str
    label: str
    host: str  # "" у главной (у неё sections)
    count: int
    preview_url: str


def _sections_label(key: str) -> str:
    from apps.tenants import siteconfig

    for k, label, _default in siteconfig.SECTIONS:
        if k == key:
            return str(label)
    return str(siteconfig.CBLOCK_LABELS.get(key, key))


def _preview_url(pt) -> str:
    for name in pt.url_names:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    sample = _SAMPLES.get(pt.code)
    if sample:
        import importlib

        module, model_name, flt = sample
        model = getattr(importlib.import_module(module), model_name)
        obj = model.objects.filter(**flt).order_by("pk").first()
        if obj is not None and hasattr(obj, "get_absolute_url"):
            try:
                return obj.get_absolute_url()
            except Exception:  # noqa: BLE001 — превью необязательно
                return ""
    return ""


#: FB-27 R4: страницы, у которых блоки есть, а `block_host` в реестре типов не объявлен
#: (обзор акций: хост «promos» выводится шаблоном и знает основной список). Здесь, а не
#: в `studio_pages`: объявление там изменило бы и панель Студии.
EXTRA_HOSTS = {"promos": "promos"}


def _host(pt) -> str:
    return pt.block_host or EXTRA_HOSTS.get(pt.code, "")


_STRUCT_FIELDS = ("key", "id", "enabled", "width", "pos", "newline")


def structure_hash(config) -> str:
    """FB-27 R0: отпечаток СТРУКТУРЫ сайта — порядок, состав, видимость и ширина блоков
    главной и всех страниц. Тексты, фото и стили в него не входят.

    Нужен как предохранитель «два писателя»: Студия и «Seitenaufbau» пишут одни ключи
    (`sections`, `page_blocks`); форма с устаревшим отпечатком не должна перезаписать
    схему, сохранённую тем временем в другом месте."""
    import hashlib
    import json

    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(config if isinstance(config, dict) else {})

    def rows(items):
        return [[s.get(f) for f in _STRUCT_FIELDS] for s in (items or []) if isinstance(s, dict)]

    blocks = cfg.get("page_blocks") if isinstance(cfg.get("page_blocks"), dict) else {}
    payload = {
        "sections": rows(cfg.get("sections")),
        "page_blocks": {host: rows(blocks[host]) for host in sorted(blocks)},
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


#: FB-27 R8: что из строки блока принадлежит «Seitenaufbau», а не Студии (те же поля,
#: что видит отпечаток структуры, кроме состава и порядка — их задаёт сам список).
_OWNED_FIELDS = ("enabled", "width", "pos", "newline")


def merge_structure(saved: list, posted: list, fixed: bool = False) -> list:
    """FB-27 R8: блоки страницы после «Speichern» Студии. Порядок, состав, видимость и
    ширина — как СОХРАНЕНО (структуру правит «Seitenaufbau»); из формы Студии берётся
    только содержимое и вид блока, найденного по `id` (свой блок) или `key` (секция).

    Блок формы, которого в сохранённом нет (удалён тем временем), отбрасывается; блок,
    которого нет в форме (устаревшая вкладка, свёрнутая страница), остаётся как был.
    `fixed` — главная: встроенные секции, которых в сохранённом ещё нет, дописываются."""
    from apps.tenants import siteconfig

    def ident(item):
        # не строка (мусор в черновике) — не ключ: по ней блок не найти
        value = item.get("id") or item.get("key")
        return value if isinstance(value, str) else None

    def kind(item):
        key = item.get("key")
        return siteconfig.cblock_type(key) or key  # легаси-ключ блока = его новый тип

    by = {}
    for item in posted or []:
        if isinstance(item, dict) and not siteconfig.is_main_marker(item) and ident(item):
            by.setdefault(ident(item), item)
    out = []
    for old in saved or []:
        if not isinstance(old, dict):
            continue
        new = None if siteconfig.is_main_marker(old) else by.pop(ident(old), None)
        if new is None or kind(new) != kind(old):
            out.append(old)
            continue
        merged = {**new, "key": old.get("key")}
        # У встроенной секции главной ширину (Ganz/Randlos) в «Seitenaufbau» менять
        # негде — она остаётся виду Студии; её структура — только видимость.
        for field in _OWNED_FIELDS if old.get("id") else ("enabled",):
            if field in old:
                merged[field] = old[field]
            else:
                merged.pop(field, None)
        out.append(merged)
    if fixed:
        out += [item for item in by.values() if not item.get("id")]
    return out


def _structure_signature(items: list, only: set | None = None) -> list:
    out = []
    for item in items or []:
        if not isinstance(item, dict) or item.get("key") == "main":
            continue
        ref = item.get("id") or item.get("key")
        if only is not None and ref not in only:
            continue
        row = [ref, bool(item.get("enabled", True))]
        if item.get("id"):
            row += [
                item.get("width") or "contained",
                item.get("pos") or "",
                bool(item.get("newline")),
            ]
        out.append(row)
    return out


def structure_attempted(posted: list, merged: list) -> bool:
    """FB-27 R8: пыталась ли форма Студии изменить структуру (порядок, видимость,
    удаление, ширину своего блока) — тогда «Gespeichert» без пояснения было бы неправдой."""
    sent = _structure_signature(posted)
    refs = {row[0] for row in sent if isinstance(row[0], str)}
    return sent != _structure_signature(merged, only=refs)


def merge_pages(saved: dict, posted: dict) -> dict:
    """FB-27 R8: `page_blocks` после «Speichern» Студии — хосты и их состав как
    сохранено; страница, которой нет в форме, остаётся как была."""
    saved = saved if isinstance(saved, dict) else {}
    posted = posted if isinstance(posted, dict) else {}
    return {
        host: merge_structure(blocks, posted[host]) if host in posted else list(blocks)
        for host, blocks in saved.items()
    }


def page_rows(config: dict) -> list[PageRow]:
    """Типы страниц со своими блоками (главная первой) + число видимых блоков."""
    rows = []
    for pt in studio_pages.PAGE_TYPES:
        if pt.code != "home" and not _host(pt):
            continue
        blocks = blocks_for(config, pt.code)
        rows.append(
            PageRow(
                code=pt.code,
                label=str(pt.label),
                host=_host(pt) if pt.code != "home" else "",
                count=sum(1 for b in blocks if b["enabled"] and not b["main"]),
                preview_url=_preview_url(pt),
            )
        )
    return rows


def _page_type(code: str):
    base = code.split("@", 1)[0]
    # подстраницы есть у типа «Seite» и у категорий (FB-27 R7: своя схема категории)
    if "@" in code and base not in (TEXT, CATEGORY):
        return None
    for pt in studio_pages.PAGE_TYPES:
        if pt.code == base and (pt.code == "home" or _host(pt)):
            return pt
    return None


#: M21.11 (решение владельца): у типа «Seite» у КАЖДОЙ страницы свой набор блоков —
#: «Über uns» (хост info), «Versand» (versand) и каждая своя страница (seite:<slug>).
#: Код строки схемы: «text» = Über uns, «text@<хост>» = остальные.
TEXT = "text"
CONTACT_REF = "__contact"


@dataclass
class SubPage:
    code: str
    label: str
    host: str
    preview_url: str


#: FB-27 R7: своя схема категории — строка «category@catalog:<slug>».
CATEGORY = "category"
CATEGORY_ROWS_MAX = 200


def category_code(slug: str) -> str:
    from apps.tenants import siteconfig

    host = siteconfig.category_host(slug)
    return f"{CATEGORY}@{host}" if host else ""


def category_pages(config: dict) -> list[SubPage]:
    """Категории, у которых может быть своя схема: сначала те, у кого она уже есть, затем
    остальные по названию. Один запрос; адрес длиннее хоста — без строки."""
    from apps.catalog.models import Category
    from apps.tenants import siteconfig

    own, rest = [], []
    for cat in Category.objects.filter(is_active=True).order_by("slug")[:CATEGORY_ROWS_MAX]:
        host = siteconfig.category_host(cat.slug)
        if not host:
            continue
        page = SubPage(
            f"{CATEGORY}@{host}", str(cat), host, reverse("storefront-category", args=[cat.slug])
        )
        (own if siteconfig.has_own_schema(config, host) else rest).append(page)
    key = lambda p: p.label.lower()  # noqa: E731
    return sorted(own, key=key) + sorted(rest, key=key)


def category_items(config: dict, host: str, items: list[dict], op: str) -> list[dict]:
    """Новый состав схемы категории: `adopt` — копия блоков каталога (новые id, маркер
    основного списка на том же месте) и ниже свои блоки категории; `reset` — пусто
    (страница снова показывает блоки каталога). Только для хоста категории."""
    from apps.tenants import siteconfig

    if not host.startswith(siteconfig.CATEGORY_HOST_PREFIX):
        raise SchemaError("category")
    marker = {"key": siteconfig.MAIN_LIST_KEY}
    if op == "reset":
        return [marker]
    source = siteconfig.main_list_sequence(
        "catalog", (config.get("page_blocks") or {}).get("catalog", [])
    )
    own = [it for it in items if not siteconfig.is_main_marker(it)]
    copied = []
    for block in source:
        if siteconfig.is_main_marker(block):
            copied.append(dict(marker))
        elif block.get("id"):
            copied.append({**copy.deepcopy(block), "id": uuid.uuid4().hex[:12]})
    if sum(1 for b in copied if b.get("id")) + len(own) > siteconfig._MAX_CBLOCKS:
        raise SchemaError("full")
    return copied + own


def text_pages() -> list[SubPage]:
    """Страницы типа «Seite»: Über uns, Versand (если доступна) и свои страницы."""
    from apps.core import content_pages
    from apps.core.models import ContentPage

    out = [SubPage(TEXT, str(_("Über uns")), "info", reverse("storefront-about"))]
    try:
        out.append(
            SubPage(f"{TEXT}@versand", str(_("Versand")), "versand", reverse("storefront-shipping"))
        )
    except NoReverseMatch:
        pass
    pages = ContentPage.objects.exclude(slug__in=list(content_pages.SYSTEM_PAGES)).order_by(
        "sort_order", "title"
    )
    for page in pages[:200]:
        out.append(
            SubPage(
                f"{TEXT}@seite:{page.slug}",
                page.title,
                f"seite:{page.slug}",
                content_pages.content_url(page.slug),
            )
        )
    return out


def host_for(code: str, known_slugs: set[str] | None = None) -> str:
    """Хост блоков строки схемы ("" у главной). Неизвестная подстраница → "".

    `known_slugs` — слаги существующих страниц, если вызывающий уже загрузил их
    (список опций): без него каждая опция стоила бы запроса."""
    from apps.tenants import siteconfig

    pt = _page_type(code)
    if pt is None or pt.code == "home":
        return ""
    if "@" not in code:
        return _host(pt)
    host = code.split("@", 1)[1]
    if pt.code == CATEGORY:
        # FB-27 R7: только существующая категория — иначе POST плодил бы хосты-призраки.
        slug = host[len(siteconfig.CATEGORY_HOST_PREFIX) :]
        if not host.startswith(siteconfig.CATEGORY_HOST_PREFIX) or (
            siteconfig.category_host(slug) != host
        ):
            return ""
        if known_slugs is not None:
            return host if slug in known_slugs else ""
        from apps.catalog.models import Category

        return host if Category.objects.filter(slug=slug).exists() else ""
    if pt.code != TEXT:
        return ""
    if host == "versand":
        return host
    if host.startswith("seite:") and siteconfig.is_page_block_host(host):
        # Ревью безопасности: только существующая страница — иначе POST плодил бы
        # хосты-призраки и вытеснял настоящие (у page_blocks общий потолок хостов).
        from apps.core.models import ContentPage

        slug = host.split(":", 1)[1]
        if known_slugs is not None:
            return host if slug in known_slugs else ""
        if ContentPage.objects.filter(slug=slug).exists():
            return host
    return ""


def _textpage_summaries(rows: list[dict], items: list[dict]) -> None:
    """FB-27 R6: в строке блока «Textseite» — название выбранной страницы. Один запрос
    на все такие блоки страницы; без них — ни одного."""
    wanted = {
        it["id"]: (it.get("data") or {}).get("page")
        for it in items
        if it.get("id") and it.get("key") == "textpage" and (it.get("data") or {}).get("page")
    }
    if not wanted:
        return
    from django.core.exceptions import ValidationError
    from django.db import DatabaseError

    from apps.core.models import ContentPage

    try:
        titles = {
            str(pk): title
            for pk, title in ContentPage.objects.filter(pk__in=set(wanted.values())).values_list(
                "pk", "title"
            )
        }
    except (DatabaseError, ValidationError, ValueError):
        return
    gone = _("Seite nicht mehr vorhanden")
    for row in rows:
        if row["ref"] in wanted:
            row["summary"] = str(titles.get(wanted[row["ref"]], gone))[:60]


def blocks_for(
    config: dict, code: str, host: str | None = None, summaries: bool = True
) -> list[dict]:
    """Строки схемы: {ref, key, label, enabled, main, cblock, summary} по порядку страницы."""
    from apps.tenants import siteconfig

    pt = _page_type(code)
    if pt is None:
        return []
    if host is None:
        host = host_for(code)
    if pt.code == "home":
        items = config.get("sections") or []
    elif not host:
        return []
    else:
        items = siteconfig.main_list_sequence(host, (config.get("page_blocks") or {}).get(host, []))
    out = []
    if host == "info":
        # M21.11: карточка «Kontakt & Öffnungszeiten» стоит на «Über uns» над блоками —
        # строкой схемы, которую можно выключить (порядок фиксирован, удалить нельзя).
        out.append(
            {
                "ref": CONTACT_REF,
                "key": "contact",
                "label": str(_("Kontakt & Öffnungszeiten")),
                "enabled": config.get("about_contact") is not False,
                "main": False,
                "cblock": False,
                "fixed": True,
                "summary": "",
            }
        )
    main_label = _("Hauptliste")  # не внутри f-строки: xgettext её не извлекает
    names = width_names()
    for item in items:
        key = item.get("key", "")
        main = siteconfig.is_main_marker(item)
        cblock = bool(item.get("id")) and not main
        data = item.get("data") or {}
        out.append(
            {
                "ref": item.get("id") or key,
                "key": key,
                "label": f"★ {main_label}" if main else _sections_label(key),
                "enabled": True if main else bool(item.get("enabled", True)),
                "main": main,
                "cblock": cblock,
                "summary": str(data.get("title") or data.get("label") or "")[:60],
                "fixed": False,
                "width": item.get("width") or "",
                "newline": bool(item.get("newline")),
                "width_label": WIDTH_LABELS.get(item.get("width") or "", ""),
                "flex": WIDTH_FLEX.get(item.get("width") or "", 12),
                "widths": [(v, lab, names.get(v, lab)) for v, lab in width_choices(item)]
                if cblock
                else [],
                "width_value": item.get("width") or "contained",
                "fields": panel_fields(item) if cblock else [],
                # FB-27 R3b-2: данные блока «Liste» — вид строит панель (`list_panel`)
                "list_data": dict(data)
                if cblock and (siteconfig.cblock_type(key) or key) == "list"
                else None,
                "narrow": cblock and item.get("width") in siteconfig.NARROW_WIDTHS,
            }
        )
    if summaries:  # строке списка страниц нужен только счёт блоков — без запроса
        _textpage_summaries(out, items)
    for b in out:
        b.setdefault("width", "")
        b.setdefault("newline", False)
        b.setdefault("width_label", "")
        b.setdefault("flex", 12)
        b.setdefault("widths", [])
        b.setdefault("width_value", "contained")
        b.setdefault("fields", [])
        b.setdefault("list_data", None)
        b.setdefault("narrow", False)
    # FB-27 R1: «выше/ниже» двигает блок среди ВИДИМЫХ — скрытый сосед не «съедает»
    # нажатие (раньше порядок на странице не менялся, а кнопка была активна).
    movable = [b for b in out if not b["fixed"] and b["enabled"]]
    for b in out:
        b["can_up"] = b["can_down"] = False
    for i, b in enumerate(movable):
        b["can_up"] = i > 0
        b["can_down"] = i < len(movable) - 1
    return out


#: FB-27 R1: подписи и доли ширины блока в схеме (ширины — `siteconfig.CBLOCK_WIDTHS`).
WIDTH_LABELS = {"w23": "⅔", "w12": "½", "w13": "⅓", "w14": "¼", "w15": "⅕", "w16": "⅙"}
WIDTH_FLEX = {"w23": 8, "w12": 6, "w13": 4, "w14": 3, "w15": 2.4, "w16": 2}

#: Группы select «Seitentyp»: (код группы, подпись, модуль-владелец | None, типы).
_TYPE_GROUPS = (
    (
        "shop",
        gettext_lazy("Sortiment"),
        "catalog",
        ("catalog", "category", "product", "cart", "wishlist", "combos", "lookbook", "finder"),
    ),
    ("termine", gettext_lazy("Termine"), "booking", ("services", "service")),
    ("unterkunft", gettext_lazy("Unterkunft"), "stays", ("stays", "stay")),
    ("events", gettext_lazy("Veranstaltungen"), "events", ("events", "event", "tours")),
    ("anfragen", gettext_lazy("Anfragen"), "jobs", ("anfrage",)),
)
_CONTENT_GROUP = gettext_lazy("Inhalte")
_CATEGORY_GROUP = gettext_lazy("Kategorien")


def _category_type(tenant):
    """Тип «Kategorie», если он есть у бизнеса (иначе None)."""
    from apps.core import page_settings

    pt = _page_type(CATEGORY)
    return pt if pt is not None and page_settings.type_active(tenant, CATEGORY) else None


#: FB-27 R3 (решение владельца Q1): до ⅙ сужаются только ПРОСТЫЕ блоки. Всё остальное —
#: сетки карточек, формы, баннер, цифры, рассылка — не уже половины: в узкой колонке
#: (⅙ ≈ 128 px на планшете) карточки и поля ввода ломаются. Белый список, а не чёрный:
#: новый тип блока по умолчанию остаётся широким.
_NARROW_OK_BLOCKS = frozenset({"text", "image", "button", "spacer"})
_WIDTH_ORDER = ("contained", "w23", "w12", "w13", "w14", "w15", "w16")
_WIDE_WIDTHS = ("contained", "w23", "w12")


#: FB-27 R3b: поля содержимого, которые правятся в панели «Seitenaufbau»
#: (тип блока → [(поле данных, подпись, вид)]). Остальное — стиль, фото, оформление —
#: по-прежнему на странице («Auf der Seite bearbeiten»).
PANEL_FIELDS = {
    "text": (
        ("title", gettext_lazy("Überschrift"), "line"),
        ("body", gettext_lazy("Text"), "area"),
    ),
    "image_text": (
        ("title", gettext_lazy("Überschrift"), "line"),
        ("body", gettext_lazy("Text"), "area"),
    ),
    "button": (
        ("label", gettext_lazy("Beschriftung"), "line"),
        ("url", gettext_lazy("Link"), "line"),
    ),
    "image": (("caption", gettext_lazy("Bildunterschrift"), "line"),),
    # FB-27 R6: у блоков-ссылок в панели только выбор — что показать и как; пункты
    # селектов дополняет `fill_options` (нужен запрос — только для открытого блока).
    "textpage": (
        ("page", gettext_lazy("Welche Seite"), "select"),
        ("mode", gettext_lazy("Wie viel Text"), "select"),
    ),
    "contact_card": (("style", gettext_lazy("Darstellung"), "select"),),
}


def panel_fields(item: dict) -> list[dict]:
    """Поля панели блока с текущими значениями: [{name, label, kind, value}]."""
    from apps.tenants import siteconfig

    key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
    data = item.get("data") or {}
    return [
        {"name": name, "label": str(label), "kind": kind, "value": data.get(name, "")}
        for name, label, kind in PANEL_FIELDS.get(key, ())
    ]


def fill_options(block: dict, host: str) -> None:
    """FB-27 R6: пункты селектов панели открытого блока (на месте). Сохранённое значение,
    которого среди пунктов нет (страницу удалили), остаётся выбранным пунктом (W0)."""
    from apps.core import content_pages
    from apps.core.list_panel import _select

    key = block.get("key")
    options = {}
    if key == "textpage":
        options = {
            "page": [("", _("Bitte wählen")), *content_pages.embed_choices(host)],
            "mode": [("", _("Ganzer Text")), ("teaser", _("Anfang mit „Weiterlesen“"))],
        }
    elif key == "contact_card":
        options = {
            "style": [
                ("", _("Karte")),
                ("split", _("Karte mit Lageplan daneben")),
                ("map_first", _("Lageplan oben")),
                ("compact", _("Eine Zeile, ohne Karte")),
            ]
        }
    for f in block.get("fields") or []:
        if f["name"] in options:
            f["options"] = _select(f["name"], f["label"], f["value"], options[f["name"]])["options"]
            f["value"] = str(f["value"] or "")
    if key == "contact_card":
        block["source_url"] = reverse("settings")
        block["source_label"] = _("Adresse und Öffnungszeiten ändern")
    elif key == "textpage":
        block["source_url"] = reverse("content-pages")
        block["source_label"] = _("Texte der Seiten ändern")


def width_choices(item: dict) -> list[tuple[str, str]]:
    """Ширины, которые можно выбрать этому блоку: [(значение, подпись)]. Уже
    выбранная ширина остаётся в списке, даже если новой её не выбрать (W0)."""
    from apps.tenants import siteconfig

    key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
    allowed = list(_WIDTH_ORDER if key in _NARROW_OK_BLOCKS else _WIDE_WIDTHS)
    current = item.get("width") or "contained"
    if current not in allowed and current in siteconfig.CBLOCK_WIDTHS:
        allowed.append(current)
    labels = {"contained": str(_("Ganz")), "full": str(_("Randlos")), **WIDTH_LABELS}
    return [(v, labels.get(v, v)) for v in allowed]


def width_names() -> dict[str, str]:
    """Ширина словами — для читалок (глиф «⅙» они произносят как придётся)."""
    return {
        "contained": str(_("ganze Breite")),
        "full": str(_("randlos, über die ganze Bildschirmbreite")),
        "w23": str(_("zwei Drittel")),
        "w12": str(_("die Hälfte")),
        "w13": str(_("ein Drittel")),
        "w14": str(_("ein Viertel")),
        "w15": str(_("ein Fünftel")),
        "w16": str(_("ein Sechstel")),
    }


def structure_types(tenant) -> list:
    """Типы страниц, у которых есть блоки И которые есть у этого бизнеса.

    Модуль выключен → типа нет (раньше магазин видел «Zimmer» и «Termine»). Один пункт
    на хост блоков: «Katalog» и «Kategorie» делят хост и правили одно и то же."""
    from apps.core import page_settings

    out, hosts = [], set()
    for pt in studio_pages.PAGE_TYPES:
        if pt.code != "home":
            if not _host(pt) or _host(pt) in hosts:
                continue
            if not page_settings.type_active(tenant, pt.code):
                continue
            hosts.add(_host(pt))
        out.append(pt)
    return out


def _row(
    config: dict,
    pt,
    code: str | None = None,
    label: str = "",
    preview: str = "",
    host: str | None = None,
) -> PageRow:
    code = code or pt.code
    if host is None:
        host = host_for(code)
    blocks = blocks_for(config, code, host=host, summaries=False)
    return PageRow(
        code=code,
        label=label or str(pt.label),
        host=host,
        count=sum(1 for b in blocks if b["enabled"] and not b["main"] and not b["fixed"]),
        preview_url=preview or _preview_url(pt),
    )


def type_groups(tenant, config: dict) -> list[tuple[str, list[PageRow]]]:
    """Опции select «Seitentyp» группами: главная, затем группа главного направления
    бизнеса, остальные направления, в конце «Inhalte» (вкл. каждую текстовую страницу)."""
    from apps.core import archetypes

    types = {pt.code: pt for pt in structure_types(tenant)}
    primary = archetypes.primary_module(tenant) or ""
    ordered = sorted(_TYPE_GROUPS, key=lambda g: g[2] != primary)  # стабильно: главное первым
    groups: list[tuple[str, list[PageRow]]] = []
    if "home" in types:
        groups.append((str(types["home"].label), [_row(config, types["home"])]))
    used = {"home"}
    for _key, label, _module, codes in ordered:
        rows = [_row(config, types[c]) for c in codes if c in types]
        used.update(codes)
        if rows:
            groups.append((str(label), rows))
        pt = _category_type(tenant) if "catalog" in codes and "catalog" in types else None
        if pt is not None:
            # FB-27 R7: каждая категория — своя строка (своя схема заменяет блоки каталога)
            cats = [
                _row(config, pt, code=p.code, label=p.label, preview=p.preview_url, host=p.host)
                for p in category_pages(config)
            ]
            if cats:
                groups.append((str(_CATEGORY_GROUP), cats))
    content = []
    for code, pt in types.items():
        if code in used:
            continue
        if code == TEXT:
            content.extend(
                _row(config, pt, code=p.code, label=p.label, preview=p.preview_url, host=p.host)
                for p in text_pages()
            )
        else:
            content.append(_row(config, pt))
    if content:
        groups.append((str(_CONTENT_GROUP), content))
    return groups


def schema_layout(blocks: list[dict]) -> dict:
    """Схема страницы: ряды видимых блоков (узкие соседи — в одном ряду, как на витрине)
    и отдельный список скрытых. Чистая функция."""
    from apps.tenants import siteconfig

    visible = [b for b in blocks if b["enabled"]]
    rows = []
    for g in siteconfig.group_block_rows(visible):
        rows.append(g["row"] if g.get("key") == "_row" else [g])
    return {"rows": rows, "hidden": [b for b in blocks if not b["enabled"]]}


def add_options(code: str) -> list[tuple[str, str]]:
    """Какие блоки можно добавить на этот тип страницы (повторяемые + ссылочные на страницах)."""
    from apps.tenants import siteconfig

    keys = list(siteconfig.REPEATABLE_BLOCKS)
    if code != "home":
        keys += list(siteconfig.PAGE_REF_BLOCKS)
    return [(k, str(siteconfig.CBLOCK_LABELS.get(k, k))) for k in keys]


#: FB-27 R6: меню «+ Block» — три группы (решение владельца). Тип вне списков попадает
#: в первую группу: новый блок не должен пропасть из меню молча.
_ADD_GROUPS = (
    ("inhalt", gettext_lazy("Inhalt"), ()),
    ("listen", gettext_lazy("Listen & Aktionen"), ("list", "promo", "newsletter")),
    (
        "quellen",
        gettext_lazy("Von anderen Stellen"),
        ("textpage", "contact_card", *("faq_ref", "team_ref", "gallery_ref", "testimonials_ref")),
    ),
    ("formulare", gettext_lazy("Formulare"), ("anfrage_ref", "message_ref")),
)


def add_groups(code: str) -> list[dict]:
    """Пункты «+ Block» группами: [{key, title, options: [(тип, подпись)]}]."""
    options = add_options(code)
    placed = {k for _key, _title, keys in _ADD_GROUPS for k in keys}
    out = []
    for key, title, keys in _ADD_GROUPS:
        mine = [(k, lab) for k, lab in options if (k in keys if keys else k not in placed)]
        if mine:
            out.append({"key": key, "title": str(title), "options": mine})
    return out


#: FB-27 R6: «Fertige Zeilen» — несколько блоков одним действием, уже в один ряд.
#: Пресет → (подпись, [(тип, ширина, данные | None = демо типа)]).
_CARD = {"title": "Überschrift", "body": "Kurzer Text zu diesem Punkt."}
ROW_PRESETS = {
    "text_image": (gettext_lazy("Text + Foto"), (("text", "w12", None), ("image", "w12", None))),
    "image_text": (gettext_lazy("Foto + Text"), (("image", "w12", None), ("text", "w12", None))),
    "three_cards": (
        gettext_lazy("Drei Karten"),
        (("text", "w13", _CARD), ("text", "w13", _CARD), ("text", "w13", _CARD)),
    ),
    "text_contact": (
        gettext_lazy("Text + Kontakt"),
        (("text", "w12", None), ("contact_card", "w12", None)),
    ),
}


def row_options() -> list[tuple[str, str]]:
    return [(key, str(label)) for key, (label, _blocks) in ROW_PRESETS.items()]


def preset_blocks(preset: str) -> list[dict]:
    """Блоки готовой строки (новые id); первый начинает новый ряд."""
    from apps.tenants import siteconfig

    if preset not in ROW_PRESETS:
        raise SchemaError("row")
    out = []
    for i, (key, width, data) in enumerate(ROW_PRESETS[preset][1]):
        demo = siteconfig.CBLOCK_DEMO_DATA.get(key, {}) if data is None else data
        block = {
            "key": key,
            "id": uuid.uuid4().hex[:12],
            "enabled": True,
            "data": siteconfig._clean_cblock_data(key, copy.deepcopy(demo)),
            "width": width,
        }
        if i == 0:
            block["newline"] = True
        out.append(block)
    return out


class SchemaError(ValueError):
    """Недопустимая операция схемы (неизвестный тип/блок/операция)."""


def resolve(tenant, code: str):
    """(pt, host, home) строки схемы либо SchemaError. Тип, которого у бизнеса нет,
    не правится и POST'ом в обход экрана — иначе появлялись бы блоки «в запас»,
    всплывающие при включении модуля (FB-27 R1)."""
    from apps.core import page_settings

    pt = _page_type(code)
    if pt is None:
        raise SchemaError("page")
    if pt.code != "home" and not page_settings.type_active(tenant, pt.code):
        raise SchemaError("page")
    host = host_for(code)
    home = pt.code == "home"
    if not home and not host:
        raise SchemaError("page")
    return pt, host, home


def load_items(config: dict, home: bool, host: str) -> list[dict]:
    """Копия блоков страницы в том виде, в котором их правит схема."""
    from apps.tenants import siteconfig

    if home:
        return copy.deepcopy(config.get("sections") or [])
    return copy.deepcopy(
        siteconfig.main_list_sequence(host, (config.get("page_blocks") or {}).get(host, []))
    )


def mutate(
    items: list[dict],
    code: str,
    op: str,
    ref: str = "",
    block_type: str = "",
    value: str = "",
    fields: dict | None = None,
) -> str:
    """Одна правка списка блоков НА МЕСТЕ (без записи): общая для немедленной правки
    и черновика. Возвращает ref блока (у `add` — id нового)."""
    from apps.tenants import siteconfig

    idx = next((i for i, it in enumerate(items) if (it.get("id") or it.get("key")) == ref), None)
    if op == "add":
        if block_type not in dict(add_options(code)):
            raise SchemaError("type")
        if sum(1 for it in items if it.get("id")) >= siteconfig._MAX_CBLOCKS:
            # normalize молча отбросил бы лишний блок при сохранении
            raise SchemaError("full")
        new = {
            "key": block_type,
            "id": uuid.uuid4().hex[:12],
            "enabled": True,
            "data": copy.deepcopy(siteconfig.CBLOCK_DEMO_DATA.get(block_type, {})),
        }
        items.append(new)
        return new["id"]
    if op == "add_row":
        # FB-27 R6: готовая строка — все блоки разом либо ни одного (потолок блоков).
        new_blocks = preset_blocks(value)
        own = sum(1 for it in items if it.get("id"))
        if own + len(new_blocks) > siteconfig._MAX_CBLOCKS:
            raise SchemaError("full")
        items.extend(new_blocks)
        return new_blocks[0]["id"]
    if idx is None:
        raise SchemaError("block")
    item = items[idx]
    main = siteconfig.is_main_marker(item)
    if op == "toggle":
        if main:
            raise SchemaError("main")
        item["enabled"] = not item.get("enabled", True)
    elif op in ("up", "down"):
        step = -1 if op == "up" else 1
        j = idx + step
        if main or item.get("enabled", True):
            # через скрытых соседей — до ближайшего видимого (см. blocks_for)
            while 0 <= j < len(items) and not (
                siteconfig.is_main_marker(items[j]) or items[j].get("enabled", True)
            ):
                j += step
        if 0 <= j < len(items):
            items.insert(j, items.pop(idx))
    elif op == "delete":
        if main or not item.get("id"):
            raise SchemaError("fixed")  # фикс-секции и основной список не удаляются
        items.pop(idx)
    elif op == "width":
        # FB-27 R3: ширина — только у своих блоков; узкие соседи встают в один ряд.
        if main or not item.get("id"):
            raise SchemaError("fixed")
        if value not in {v for v, _label in width_choices(item)}:
            raise SchemaError("width")
        item["width"] = value
        if value not in siteconfig.NARROW_WIDTHS:
            item.pop("newline", None)
            item.pop("pos", None)
    elif op == "update":
        # FB-27 R3b: короткое содержимое простого блока — прямо в панели. ПАТЧ: меняются
        # только присланные поля, остальное (стиль, фото, оформление) остаётся (W0).
        key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
        if key == "list":
            from apps.core import list_panel

            allowed = list(list_panel.NAMES)
        else:
            allowed = [name for name, _label, _kind in PANEL_FIELDS.get(key, ())]
        if main or not item.get("id") or not allowed:
            raise SchemaError("fields")
        sent = {n: str(fields[n]) for n in allowed if fields is not None and n in fields}
        data = dict(item.get("data") or {})
        if key == "button" and sent.get("url") and sent["url"] != data.get("url"):
            # Небезопасная схема (javascript:, data:, //host) отбрасывается уже при записи;
            # витрина дополнительно фильтрует на выводе (`safe_href`).
            from apps.tenants.templatetags.siteui import safe_href

            if safe_href(sent["url"]) == "#" and sent["url"].strip() != "#":
                raise SchemaError("url")
        if key == "textpage" and sent.get("page") and sent["page"] != data.get("page"):
            # FB-27 R6: только существующая страница и не та, на которой стоит блок.
            from apps.core import content_pages
            from apps.core.models import ContentPage

            page_pk = (siteconfig.clean_pick([sent["page"]]) or [""])[0]
            slug = (
                ContentPage.objects.filter(pk=page_pk).values_list("slug", flat=True).first()
                if page_pk
                else None
            )
            if slug is None or content_pages.embeds_itself(slug, host_for(code)):
                raise SchemaError("page")
        patched = {**data, **sent}
        if key == "list" and "source" in sent and sent["source"] != (data.get("source") or ""):
            # FB-27 R5: ключи записей одного источника в другом ничего не значат
            patched.pop("pick", None)
        if key == "list" and "endet" in sent:
            # «Zeitraum» — один селект на срок и «Demnächst» (хранится ключом `phase`):
            # без сброса старая фаза пережила бы выбор «Alle».
            patched.pop("phase", None)
        cleaned = siteconfig._clean_cblock_data(key, patched)
        # Ничего не прислано или не изменилось — блок не трогаем вовсе (иначе канонизация
        # данных создала бы «правку», которой владелец не делал).
        if cleaned == siteconfig._clean_cblock_data(key, data):
            return ref
        item["data"] = cleaned
    elif op in _PICK_OPS:
        # FB-27 R5: ручной состав блока «Liste» («Einzeln»).
        from apps.core import list_blocks

        key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
        data = dict(item.get("data") or {})
        source = data.get("source")
        if source not in siteconfig.LIST_SOURCES:
            source = siteconfig.LIST_SOURCE_DEFAULT
        if (
            main
            or not item.get("id")
            or key != "list"
            or source not in siteconfig.LIST_PICK_SOURCES
        ):
            raise SchemaError("pick")
        pick = siteconfig.clean_pick(data.get("pick"))
        target = (siteconfig.clean_pick([value]) or [""])[0]
        if op == "pick_clear":
            pick = []
        elif not target:
            raise SchemaError("pick")
        elif op == "pick_add":
            if target not in pick:
                if len(pick) >= siteconfig.LIST_LIMIT_MAX:
                    raise SchemaError("full")
                # только существующая запись своего источника, которую сайт показывает
                if not list_blocks.is_live(source, target):
                    raise SchemaError("pick")
                pick.append(target)
        elif target not in pick:
            raise SchemaError("pick")
        elif op == "pick_remove":
            pick.remove(target)
        else:
            i = pick.index(target)
            j = i - 1 if op == "pick_up" else i + 1
            if 0 <= j < len(pick):
                pick[i], pick[j] = pick[j], pick[i]
        if pick:
            data["pick"] = pick
        else:
            data.pop("pick", None)
        item["data"] = siteconfig._clean_cblock_data(key, {**data, "source": source})
    elif op == "newline":
        if main or not item.get("id") or item.get("width") not in siteconfig.NARROW_WIDTHS:
            raise SchemaError("width")
        if item.get("newline"):
            item.pop("newline", None)
        else:
            item["newline"] = True
    else:
        raise SchemaError("op")
    return ref


#: FB-27 R4: чьи ещё настройки правятся на строке типа — у этих типов своей строки в
#: «Seitenaufbau» нет (категория делит блоки с каталогом, страницы акций — с обзором).
SETTINGS_FOLLOWERS = {"catalog": ("category",), "promos": ("promo_group", "promo")}


def settings_url(type_code: str, setting: str = "") -> str:
    """Адрес строки «Seitenaufbau», где правятся настройки типа `type_code` (замена
    экрана «Seitenvorlagen»). Тип без своей строки ведёт на строку-хозяина; неизвестный
    — просто на экран. `setting` — какую настройку раскрыть."""
    from urllib.parse import urlencode

    from apps.tenants import siteconfig

    owner = next((row for row, more in SETTINGS_FOLLOWERS.items() if type_code in more), "")
    code = owner or ("text" if type_code == "legal" else type_code)
    pt = _page_type(code)
    url = reverse("site-schema")
    if pt is None:
        return url
    block = siteconfig.MAIN_LIST_KEY if _host(pt) in siteconfig.MAIN_LIST_HOSTS else PAGE_REF
    query = {"seite": pt.code, "block": block}
    if setting:
        query["offen"] = setting
    return f"{url}?{urlencode(query)}#schema-panel"


def setting_types(tenant, code: str) -> list[str]:
    """Типы страниц, чьи настройки правятся на строке `code` (сам тип первым)."""
    from apps.core import page_settings

    pt, _host, _home = resolve(tenant, code)
    out = [pt.code]
    out += [t for t in SETTINGS_FOLLOWERS.get(pt.code, ()) if page_settings.type_active(tenant, t)]
    return out


def setting_codes(tenant, code: str) -> list[str]:
    """Коды настроек, которые можно менять на строке `code` (по порядку, без повторов)."""
    from apps.core import page_settings

    out: list[str] = []
    for type_code in setting_types(tenant, code):
        for s in page_settings.cabinet_settings(type_code):
            if s.code not in out and page_settings.applies(tenant, s):
                out.append(s.code)
    return out


#: Строка «Einstellungen der Seite» — у страниц без основного списка (главная, детали,
#: корзина, текстовые): настройки типа некуда больше положить.
PAGE_REF = "__page"
#: Ключи сайта, общие для многих страниц — панель подписывает их «gilt für alle Seiten».
SHARED_SETTINGS = frozenset({"product_card_form", "promo_card_form", "text_width"})


def settings_groups(tenant, code: str, config: dict) -> list[dict]:
    """Настройки строки `code` по значениям `config` (черновик): [{label, settings}].
    Первая группа — сам тип (без заголовка), дальше типы без своей строки."""
    from apps.core import page_settings

    seen: set[str] = set()
    out = []
    for i, type_code in enumerate(setting_types(tenant, code)):
        found = page_settings.schema(tenant, (type_code,), config=config)
        if not found:
            continue
        rows = [s for s in found[0].settings if s.code not in seen]
        seen.update(s.code for s in rows)
        if rows:
            out.append(
                {
                    "label": "" if i == 0 else str(found[0].label),
                    "settings": [{"s": s, "current": _current_label(s)} for s in rows],
                }
            )
    return out


def _current_label(state) -> str:
    """Текущее значение настройки словами — для свёрнутой строки панели."""
    if state.kind == "bool":
        want = "1" if state.value else "0"
        return next((str(c.label) for c in state.choices if c.value == want), "")
    return next((str(c.label) for c in state.choices if c.value == state.value), str(state.value))


_PICK_OPS = frozenset({"pick_add", "pick_remove", "pick_up", "pick_down", "pick_clear"})


def store_items(config: dict, home: bool, host: str, items: list[dict]) -> None:
    """Кладёт блоки страницы в `config` (на месте) и выравнивает переводы C-блоков."""
    from apps.tenants import siteconfig

    if home:
        siteconfig.realign_block_overlays(config, new_sections=items)
        config["sections"] = items
        return
    # ВСЕ хосты: выравнивание сверяет каждый хост оверлея с новым набором, и
    # переданный один хост стёр бы переводы блоков остальных страниц.
    page_blocks = dict(config.get("page_blocks") or {})
    page_blocks[host] = items
    siteconfig.realign_block_overlays(config, new_page_blocks=page_blocks)
    config["page_blocks"] = page_blocks


@transaction.atomic
def apply(
    tenant,
    code: str,
    op: str,
    ref: str = "",
    block_type: str = "",
    value: str = "",
    fields: dict | None = None,
) -> str:
    """Одна правка схемы страницы `code` СРАЗУ в базу. Бросает SchemaError на
    недопустимом. Возвращает ref блока, с которым работали (у `add` — id нового).
    Экран «Seitenaufbau» правит через черновик (`aufbau_draft`), это — для прочих."""
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    _pt, host, home = resolve(tenant, code)
    locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
    config = siteconfig.normalize(locked.site_config)
    if host == "info" and ref == CONTACT_REF:
        if op != "toggle":
            raise SchemaError("fixed")
        if config.get("about_contact") is False:
            config.pop("about_contact", None)
        else:
            config["about_contact"] = False
    else:
        items = load_items(config, home, host)
        ref = mutate(items, code, op, ref, block_type, value, fields)
        store_items(config, home, host, items)
    locked.site_config = siteconfig.normalize(config)
    locked.save(update_fields=["site_config", "updated_at"])
    tenant.site_config = locked.site_config
    return ref
