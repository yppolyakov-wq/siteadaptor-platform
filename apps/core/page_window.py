"""FB-33 M3-6 (макет M0-11): «Einstellungen der Seite» окном с вкладкой «Seite».

План — `docs/fb33-editor-model-2026-11-19.md` §«План M3» и план среза M3-6 (решения владельца
2026-11-20). Модуль даёт:

- ★-строку страницы `__page` (FB-33 M5b-2, макет V4) — у всех страниц, кроме главной, где
  правило `site_schema.page_row_ref` её даёт: «★ Seitentitel und Seite» (страницы со своим
  заголовком `page_title.HEAD_HOSTS`: поля заголовка и настройки типа на вкладке «Seite») или
  «★ Einstellungen der Seite»; строка не хранится и не правится операциями схемы
  (`site_schema.mutate` — `SchemaError`);
- строки-ссылки между ★-строкой и окном основного списка: «Darstellung … im Block › Wie
  anordnen» у списков со своим видом и «Wie die Liste aussieht: in ★ …» у прочих;
- часть «Texte» у такой строки — свой заголовок и описание для поисковиков, только на хостах
  `siteconfig.is_seo_page_host` (через черновик; запись при «Speichern» — тем же чистым
  писателем `content_pages.put_page_seo`, что у вкладки «Suchmaschinen» экрана «Seiten»);
  у категории — ссылка на форму категории;
- строку наследования вида товаров у страницы категории (по образцу M3-3c): откуда вид
  («Wie bei allen Kategorie-Seiten»), что у этой категории своё, и «zurücksetzen».

Ширины страницы, шаблона страницы и слияния строк здесь нет (решения владельца: ширина —
только общая «Design», «Seitenvorlage» не возвращается, слияние — M5).
"""

from __future__ import annotations

import copy

from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from apps.core import site_schema

#: черновик: свой заголовок/описание страницы для поисковиков (`clean_seo_page`)
SEO_KEY = "seo"
#: черновик: SEO страницы на момент первой правки в окне (ревью: «Trotzdem speichern» пишет
#: только поля, изменённые в окне, — чужую правку на экране «Seiten» не перетирает)
SEO_BASE_KEY = "seo_base"
#: поля SEO, которые правит окно (`noindex` — только экран «Seiten»)
SEO_EDITED = ("title", "description")
#: поля формы SEO окна (`f_` — общий префикс полей панели)
SEO_FIELDS = ("seo_title", "seo_description")
#: операция «zurücksetzen» строки наследования вида товаров категории
VIEW_RESET_OP = "view_reset"


def _entry_page(host: str) -> bool:
    """Детальная страница одной записи (товар, услуга, номер, событие, акция, набор, запись
    блога): заголовок — имя записи, полей заголовка в окне нет."""
    return host.endswith("_detail") or host == "blog_post"


def label(host: str) -> str:
    """Подпись ★-строки (решение владельца 2026-11-22): «Seitentitel und Seite» только у
    страниц со своим заголовком, иначе «Einstellungen der Seite»."""
    from apps.core import page_title

    if host in page_title.HEAD_HOSTS:
        return _("Seitentitel und Seite")
    return _("Einstellungen der Seite")


def summary(host: str, config: dict) -> str:
    """Сводка ★-строки: свой заголовок в кавычках или «Standard»; у деталей — «Titel = Name
    des Eintrags»; у прочих — "" ("wie alle …-Seiten" не выводим)."""
    from apps.core import page_title

    if host in page_title.HEAD_HOSTS:
        title = page_title.clean_one((config.get("page_titles") or {}).get(host)).get("title")
        return f"„{title}“" if title else _("Standard")
    if _entry_page(host):
        return _("Titel = Name des Eintrags")
    return ""


def pseudo_row(ref: str, page_ref: str, host: str = "", config: dict | None = None) -> dict | None:
    """★-строка `__page` для окна и экрана — там, где её даёт единое правило
    `site_schema.page_row_ref` (FB-33 M5b-1, V4 — M5b-2). Ключи — те, что знает окно
    (`block_window.ROW_KEYS`/`PANEL_KEYS`); у страниц со своим заголовком — поля «Seitentitel»
    (`site_schema.title_fields`, значения — из `config`, черновика)."""
    from apps.core import page_title

    if ref != site_schema.PAGE_REF or page_ref != site_schema.PAGE_REF:
        return None
    row = {
        "ref": site_schema.PAGE_REF,
        "key": site_schema.PAGE_REF,
        "label": label(host),
        "summary": summary(host, config or {}),
        "enabled": True,
        "main": True,  # не скрывается, не двигается, меню «⋯» нет
        "cblock": False,
        "fixed": True,
        "pinned": True,
        "carrier": True,  # часть «Seite» — настройки типа страницы
        "can_up": False,
        "can_down": False,
    }
    if host in page_title.HEAD_HOSTS:
        row["fields"] = site_schema.title_fields(config or {}, host)
        row["with_title"] = True  # «Überschrift der Seite» и «Einstellungen dieser Seitenart»
    return row


def star_name(text: str, visible: bool = True):
    """Имя ★-строки в тексте ссылки: `★` скрыт от чтения; `visible=False` — имя только для
    чтения с экрана (видимое «in ★ bearbeiten», WCAG 2.5.3)."""
    if visible:
        return format_html('<span aria-hidden="true">★</span> {}', text)
    return format_html('<span aria-hidden="true">★</span><span class="sr-only">„{}“</span>', text)


def main_has_view(main: dict | None) -> bool:
    """У основного списка свой вид в окне («Wie anordnen»: каталог, категория, акции, группа
    акций, Team, Galerie, туры) — по уже заполненным плиткам вида строки."""
    return bool(main) and bool(main.get("mainview") or main.get("groupview"))


def list_links(selected, blocks: list[dict], page_ref: str, host: str) -> None:
    """Строки-ссылки между ★-строкой и окном основного списка (решение владельца
    2026-11-22, «Liste/Raster» — настройки типа на ★-строке):

    - у ★-строки страницы, чей список со своим видом, — «Darstellung der Liste – im Block
      „…“ › Wie anordnen» (`list_link`);
    - у окна основного списка без своего вида — «Wie die Liste aussieht: in ★ …» на вкладку
      «Seite» ★-строки (`page_link`): иначе окно было бы пустым."""
    if not selected or page_ref != site_schema.PAGE_REF:
        return
    main = next((b for b in blocks if b.get("main") and not b.get("cblock")), None)
    if main is None:
        return
    if is_page_row(selected) and main_has_view(main):
        selected["list_link"] = {
            "name": str(main.get("label") or ""),
            "ref": main["ref"],
            "tab": "wie",
        }
    elif selected.get("ref") == main["ref"] and not main_has_view(selected):
        selected["page_link"] = {"where": star_name(label(host)), "ref": page_ref, "tab": "seite"}


def is_page_row(selected) -> bool:
    return bool(selected) and selected.get("ref") == site_schema.PAGE_REF


# ───────────── «Texte»: заголовок и описание для поисковиков ─────────────


def saved_seo(config: dict, host: str) -> dict:
    """Сохранённая запись SEO страницы (`{}` — не задана)."""
    from apps.tenants import siteconfig

    seo = (config or {}).get("seo")
    pages = seo.get("pages") if isinstance(seo, dict) else None
    entry = pages.get(host) if isinstance(pages, dict) else None
    return siteconfig.clean_seo_page(entry)


def is_seo_edit(host: str, ref: str, op_name: str, fields) -> bool:
    from apps.tenants import siteconfig

    return (
        ref == site_schema.PAGE_REF
        and op_name == "update"
        and isinstance(fields, dict)
        and any(name in fields for name in SEO_FIELDS)
        and siteconfig.is_seo_page_host(host)
    )


def seo_op(config: dict, draft: dict, host: str, fields: dict, saved: dict) -> str:
    """Правка заголовка/описания в черновике (патч: неприсланное остаётся; «noindex» правится
    только на экране «Seiten» и переезжает как был). Черновик, начатый до среза (без ключа),
    берёт сохранённое и пересчитывает отпечаток — только если конфликта нет."""
    from apps.core import aufbau_draft
    from apps.tenants import siteconfig

    if SEO_KEY not in draft:
        clean = aufbau_draft._base_fingerprint(saved, config, draft) == draft.get("base")
        draft[SEO_KEY] = copy.deepcopy(saved.get(SEO_KEY) or {})
        if clean:
            draft["base"] = aufbau_draft._base_fingerprint(saved, config, draft)
    draft.setdefault(SEO_BASE_KEY, copy.deepcopy(draft.get(SEO_KEY) or {}))
    current = dict(draft.get(SEO_KEY) or {})
    for name in SEO_FIELDS:
        if name in fields:
            current[name.removeprefix("seo_")] = str(fields[name])
    draft[SEO_KEY] = siteconfig.clean_seo_page(current)
    return site_schema.PAGE_REF


def put_shown(config: dict, host: str, draft: dict) -> None:
    """SEO черновика — для показа и превью (тем же писателем, что «Speichern»)."""
    from apps.core import content_pages
    from apps.tenants import siteconfig

    if SEO_KEY in draft and siteconfig.is_seo_page_host(host):
        content_pages.put_page_seo(config, host, draft[SEO_KEY])


def commit(config: dict, host: str, draft: dict) -> None:
    """«Speichern»: SEO черновика — в `config` под блокировкой строки бизнеса (её держит
    `aufbau_draft.commit`; `save_page_seo` здесь не звать — он сам блокирует и пишет).
    Пишутся только поля, изменённые в окне (`seo_base`), поверх сохранённого СЕЙЧАС: без правки
    в окне — ничего (при «Trotzdem speichern» чужой заголовок/«noindex» не перетираются)."""
    from apps.core import content_pages
    from apps.tenants import siteconfig

    if SEO_KEY not in draft or SEO_BASE_KEY not in draft or not siteconfig.is_seo_page_host(host):
        return
    mine, base = draft.get(SEO_KEY) or {}, draft.get(SEO_BASE_KEY) or {}
    entry = dict(saved_seo(config, host))
    for name in SEO_EDITED:
        if mine.get(name, "") != base.get(name, ""):
            if mine.get(name):
                entry[name] = mine[name]
            else:
                entry.pop(name, None)
    content_pages.put_page_seo(config, host, entry)


def changed(draft: dict, saved: dict) -> bool:
    return SEO_KEY in draft and draft[SEO_KEY] != saved.get(SEO_KEY, {})


def _category(code: str):
    from apps.tenants import siteconfig

    host = site_schema.host_for(code)
    if not host.startswith(siteconfig.CATEGORY_HOST_PREFIX):
        return None
    from apps.catalog.models import Category

    return Category.objects.filter(slug=host.removeprefix(siteconfig.CATEGORY_HOST_PREFIX)).first()


def decorate(selected, config: dict, host: str, code: str) -> None:
    """Части окна «Texte» и строки наследования у `__page`, ★ и строки категории."""
    from apps.tenants import siteconfig

    if not selected:
        return
    page = is_page_row(selected)
    if page and siteconfig.is_seo_page_host(host):
        entry = saved_seo(config, host)
        selected["seo"] = {
            "title": entry.get("title", ""),
            "description": entry.get("description", ""),
            "title_max": siteconfig.SEO_PAGE_TITLE_MAX,
            "description_max": siteconfig.SEO_PAGE_DESCRIPTION_MAX,
        }
        return
    # FB-33 M5b-2 (architect A-H2): у категории ссылка на её форму (SEO) — у ★-строки
    # страницы, строка наследования вида товаров — у ★ «Produkte» (вкладка «Wie anordnen»)
    star = selected.get("main") and not selected.get("cblock") and not page
    if not (page or star) or not host.startswith(siteconfig.CATEGORY_HOST_PREFIX):
        return
    category = _category(code)
    if category is None:
        return
    if star:
        selected["page_inherit"] = category_inherit(config, host, category)
        return
    try:
        url = reverse("catalog:category-edit", args=[category.pk])
    except NoReverseMatch:
        url = ""
    if url:
        selected["seo_link"] = {"url": url}


# ───────────── строка наследования вида товаров у категории (по образцу M3-3c) ─────────────


def _view_label(value: str) -> str:
    return next(
        (str(label) for v, label, _h, _t in site_schema.MAIN_VIEW_LABELS if v == value),
        str(site_schema.MAIN_VIEW_LABELS[0][1]),
    )


def _marker(rows):
    return next(
        (
            r
            for r in rows or ()
            if isinstance(r, dict) and r.get("key") == "main" and not r.get("id")
        ),
        None,
    )


def category_inherit(config: dict, host: str, category) -> dict:
    """«Wie bei allen Kategorie-Seiten: <вид> · für alle ändern — hier geändert gilt nur für
    „<категория>“ · zurücksetzen»: вид из общей схемы категорий и свой вид этой категории
    (поля вида у ★ её хоста — их читает витрина, `catalog_parts.effective`)."""
    from apps.catalog import catalog_parts, category_styles
    from apps.core import banners
    from apps.tenants import siteconfig

    default = ((config.get("site_defaults") or {}).get("category_page_style")) or ""
    code = category_styles.page_style(category, default)
    shared = siteconfig.shared_category_host(config)
    base = catalog_parts.effective(config, shared, code=code).products
    marker = _marker(((config.get("page_blocks") or {}).get(host)) or [])
    own = bool(marker and ("style" in marker or "grid" in marker))
    own_value = (marker or {}).get("style") or "raster"
    return {
        "summary": _view_label(base if base in site_schema.MAIN_VIEW_CHOICES else "raster"),
        "own": _view_label(own_value) if own else "",
        "name": banners._place_label(category),
        # architect A-M7: «für alle ändern» — вид ★ общей схемы категорий (не правило строки)
        "link": f"{reverse('site-schema')}?seite={site_schema.CATEGORY}&block="
        f"{siteconfig.MAIN_LIST_KEY}&tab=wie#schema-panel",
    }


def is_view_reset(host: str, ref: str, op_name: str) -> bool:
    from apps.tenants import siteconfig

    return (
        op_name == VIEW_RESET_OP
        and ref == siteconfig.MAIN_LIST_KEY
        and host.startswith(siteconfig.CATEGORY_HOST_PREFIX)
    )


def view_reset(draft: dict, ref: str) -> str:
    """«zurücksetzen»: у ★ категории снять свой вид товаров (вид и сетку) — снова как у
    всех страниц категорий. Прочие поля строки и блоки не трогаются."""
    marker = _marker(draft.get("items"))
    if marker is not None:
        for key in ("style", "grid"):
            marker.pop(key, None)
    return ref
