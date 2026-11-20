"""FB-33 M3-6 (макет M0-11): «Einstellungen der Seite» окном с вкладкой «Seite».

План — `docs/fb33-editor-model-2026-11-19.md` §«План M3» и план среза M3-6 (решения владельца
2026-11-20). Модуль даёт:

- псевдо-строку `__page` — у страниц без основного списка и без строки-носителя (детали,
  корзина, текстовые) настройки типа страницы открываются тем же окном блока, что у ★;
  строка не хранится и не правится операциями схемы (`site_schema.mutate` — `SchemaError`);
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


def pseudo_row(ref: str, blocks: list[dict]) -> dict | None:
    """Строка `__page` для окна — только там, где настройкам больше негде жить (нет ★ и
    строки-носителя). Ключи — те, что знает окно (`block_window.ROW_KEYS`/`PANEL_KEYS`)."""
    if ref != site_schema.PAGE_REF:
        return None
    if any(b.get("main") or b.get("carrier") for b in blocks):
        return None
    return {
        "ref": site_schema.PAGE_REF,
        "key": site_schema.PAGE_REF,
        "label": _("Einstellungen der Seite"),
        "enabled": True,
        "main": True,  # не скрывается, не двигается, меню «⋯» нет
        "cblock": False,
        "fixed": True,
        "pinned": True,
        "carrier": True,  # часть «Seite» — настройки типа страницы
        "can_up": False,
        "can_down": False,
    }


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
    main = selected.get("main") and not selected.get("cblock")
    if is_page_row(selected) and siteconfig.is_seo_page_host(host):
        entry = saved_seo(config, host)
        selected["seo"] = {
            "title": entry.get("title", ""),
            "description": entry.get("description", ""),
            "title_max": siteconfig.SEO_PAGE_TITLE_MAX,
            "description_max": siteconfig.SEO_PAGE_DESCRIPTION_MAX,
        }
        return
    if main and host.startswith(siteconfig.CATEGORY_HOST_PREFIX):
        category = _category(code)
        if category is None:
            return
        try:
            url = reverse("catalog:category-edit", args=[category.pk])
        except NoReverseMatch:
            url = ""
        if url:
            selected["seo_link"] = {"url": url}
        selected["page_inherit"] = category_inherit(config, host, category)


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
        "link": f"{reverse('site-schema')}?seite={site_schema.CATEGORY}&block="
        f"{siteconfig.MAIN_LIST_KEY}#schema-panel",
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
