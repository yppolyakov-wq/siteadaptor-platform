"""M21.6: свои страницы сайта (`core.ContentPage`) — единственное место правил.

- адрес страницы — ``/<slug>/`` (M21.11; старый ``/seite/<slug>/`` — 301);
- slug из ``SYSTEM_PAGES`` — текст СИСТЕМНОЙ страницы (``versand`` → ``/versand/``,
  ``ueber-uns`` → ``/ueber-uns/``): одна страница — один адрес, второй адрес даёт 301;
- неопубликованная страница видна только члену команды (предпросмотр).

План — ``docs/m21-6-content-pages-plan-2026-11-10.md``.
"""

from __future__ import annotations

import copy
import re

from django.db import IntegrityError, connection, transaction
from django.urls import NoReverseMatch, reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.richtext import sanitize_page

#: slug → url-name системной страницы, на которой выводится текст этой страницы.
SYSTEM_PAGES = {
    "versand": "storefront-shipping",
    "ueber-uns": "storefront-about",
}
SYSTEM_LABELS = {
    "versand": _("Wird auf der Seite „Versand“ angezeigt"),
    "ueber-uns": _("Wird auf der Seite „Über uns“ angezeigt"),
}
#: M21.10: заголовок новой системной страницы по умолчанию.
SYSTEM_TITLES = {
    "ueber-uns": _("Über uns"),
    "versand": _("Versand & Zahlung"),
}
#: M21.11: метка вида в строке списка «Seiten».
SYSTEM_ART = {"ueber-uns": _("Über uns"), "versand": _("Versand")}
SLUG_MAX = 80
#: M21.10: потолок текста страницы (DoS через гигантский POST/nh3).
BODY_MAX = 200_000
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PageError(ValueError):
    """Ошибка ввода страницы — текст для владельца."""


def make_slug(value: str) -> str:
    """Адрес из заголовка: «Über uns & Team» → «ueber-uns-team»."""
    text = (value or "").strip().lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    return slugify(text)[:SLUG_MAX].strip("-")


def clean_slug(value: str, *, exclude_pk=None) -> str:
    from apps.core.models import ContentPage

    slug = make_slug(value)
    if not slug or not _SLUG_RE.match(slug):
        raise PageError(_("Bitte eine Adresse aus Buchstaben, Ziffern und „-“ angeben."))
    taken = ContentPage.objects.filter(slug=slug)
    if exclude_pk is not None:
        taken = taken.exclude(pk=exclude_pk)  # pk есть и у несохранённой: исключит ничто
    if taken.exists():
        raise PageError(_("Diese Adresse ist schon vergeben."))
    return slug


def check_short_slug(slug: str, old_slug: str = "") -> None:
    """M21.11: новый адрес не может совпасть с адресом страницы витрины (/sortiment/,
    /aktionen/, /impressum/ …) — иначе своя страница по короткому адресу не открылась бы.
    Прежний адрес страницы не проверяем: он работал и до коротких адресов."""
    if slug != old_slug and slug not in SYSTEM_PAGES and not short_url_free(slug):
        raise PageError(_("Diese Adresse ist für eine Seite Ihrer Website reserviert."))


def save_page(
    page, *, title: str, slug: str, body: str, is_published: bool, show_shipping_methods=None
):
    """Единственный писатель полей страницы из кабинета (HTML — через санитайзер)."""
    title = (title or "").strip()[:200]
    if not title:
        raise PageError(_("Bitte einen Titel angeben."))
    if len(body or "") > BODY_MAX:
        raise PageError(_("Der Text ist zu lang."))
    old_slug = "" if page._state.adding else page.slug
    # M21.10: адрес системной страницы закреплён — иначе текст «Versand» уехал бы
    # на /seite/<…>/, а /versand/ остался бы без него.
    if old_slug in SYSTEM_PAGES or (page._state.adding and page.slug in SYSTEM_PAGES):
        slug = old_slug or page.slug
    elif page._state.adding and make_slug(slug or title) in SYSTEM_PAGES:
        # Новая своя страница не занимает адрес системной (её правят в «Seiten Ihrer Website»).
        raise PageError(_("Diese Adresse ist für eine Seite Ihrer Website reserviert."))
    new_slug = clean_slug(slug or old_slug or title, exclude_pk=page.pk)
    check_short_slug(new_slug, old_slug)
    page.title = title
    page.slug = new_slug
    page.body = sanitize_page(body or "")
    page.is_published = bool(is_published)
    if show_shipping_methods is not None:  # None — поля в форме не было (не трогаем)
        page.show_shipping_methods = bool(show_shipping_methods)
    try:
        with transaction.atomic():
            page.save()
    except IntegrityError as exc:  # тот же адрес сохранили параллельно
        raise PageError(_("Diese Adresse ist schon vergeben.")) from exc
    if old_slug and old_slug != new_slug:
        retarget_menus(old_slug, new_slug)
        move_page_blocks(old_slug, new_slug)
    return page


def _walk_nodes(nodes, old: str, new: str | None) -> int:
    """Пункты меню ``cpage:old`` → ``cpage:new`` (new=None — только посчитать)."""
    hits = 0
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        if node.get("type") == "cpage" and node.get("target") == old:
            hits += 1
            if new is not None:
                node["target"] = new
        hits += _walk_nodes(node.get("children"), old, new)
        hits += _walk_nodes(node.get("items"), old, new)
    return hits


def _menu_lists(config: dict):
    menus = config.get("menus") if isinstance(config.get("menus"), dict) else {}
    for key in ("top", "bottom"):
        part = menus.get(key)
        if isinstance(part, dict):
            yield part.get("items")
    footer = menus.get("footer")
    if isinstance(footer, dict):
        yield footer.get("columns")


def menu_references(slug: str, tenant=None) -> int:
    """Сколько пунктов меню/подвала ведут на страницу (предупреждение перед удалением)."""
    tenant = tenant or getattr(connection, "tenant", None)
    config = getattr(tenant, "site_config", None) or {}
    return sum(_walk_nodes(nodes, slug, None) for nodes in _menu_lists(config))


def retarget_menus(old: str, new: str) -> int:
    """После смены адреса страницы пункты меню и подвала ведут на новый адрес (иначе
    пункт молча выпал бы из меню). Пишет только ``site_config["menus"]``."""
    from apps.tenants.models import Tenant

    tenant = getattr(connection, "tenant", None)
    if tenant is None or not getattr(tenant, "pk", None):
        return 0
    with transaction.atomic():
        fresh = Tenant.objects.select_for_update().filter(pk=tenant.pk).first()
        if fresh is None:
            return 0
        config = dict(fresh.site_config or {})
        config["menus"] = copy.deepcopy(config.get("menus") or {})
        hits = sum(_walk_nodes(nodes, old, new) for nodes in _menu_lists(config))
        if hits:
            fresh.site_config = config
            fresh.save(update_fields=["site_config"])
            tenant.site_config = config
    return hits


def _move_seo(config: dict, src: str, dst: str | None) -> bool:
    """FB-27 «Seiten»: запись SEO страницы едет за её адресом (и уходит с удалением).
    Стопка 16 T1b: и переводы SEO этой страницы у всех языков (`seo_tr_path`)."""
    moved = False
    seo = config.get("seo")
    pages = seo.get("pages") if isinstance(seo, dict) else None
    if isinstance(pages, dict) and src in pages:
        entry = pages.pop(src)
        if dst:
            pages[dst] = entry
        moved = True
    for node in _i18n_nodes(config):
        tr = _seo_tr_pages(node)
        if tr is None or src not in tr:
            continue
        entry = tr.pop(src)
        if dst:
            tr[dst] = entry
        _prune_seo_tr(node)
        moved = True
    return moved


#: стопка 16 T1b: поля SEO страницы, у которых есть перевод (`noindex` — только база)
SEO_TR_FIELDS = ("title", "description")


def seo_tr_path(host: str, field: str) -> tuple:
    """Путь перевода поля SEO страницы в `i18n[<язык>]` (как `page_title.tr_path`): по ключу
    хоста, не по позиции. `seo` не в `TRANSLATABLE_KEYS` и `localize` его не накладывает
    (D9) — читает только `page_seo`, пишет только `block_i18n` (окно) и снимает `put_page_seo`."""
    return ("seo", "pages", host, field)


def _i18n_nodes(config: dict) -> list:
    root = config.get("i18n")
    return [n for n in root.values() if isinstance(n, dict)] if isinstance(root, dict) else []


def _seo_tr_pages(node):
    seo = node.get("seo") if isinstance(node, dict) else None
    pages = seo.get("pages") if isinstance(seo, dict) else None
    return pages if isinstance(pages, dict) else None


def _prune_seo_tr(node: dict) -> None:
    pages = _seo_tr_pages(node)
    if pages is None:
        return
    for host in [h for h, v in pages.items() if v in ({}, None)]:
        pages.pop(host)
    if not pages:
        node["seo"].pop("pages", None)
    if not node["seo"]:
        node.pop("seo", None)


def _seo_overlay(config: dict, locale: str, host: str) -> dict:
    """Перевод SEO страницы на `locale` ({title?, description?}) — с проверкой формы:
    `_clean_i18n` пропускает любой словарь, `normalize_seo` чистит только базу. Битый оверлей
    (строка, список, больше `_MAX_SEO_PAGES` хостов, не словарь у самой страницы) — пусто:
    витрина показывает немецкое, а не 500. Битый ЧУЖОЙ ключ (не хост SEO, не словарь) перевод
    этой страницы не гасит (ревью D2). О любом битом — предупреждение в лог (одно на запрос:
    `siteui.page_seo` читает раз на запрос)."""
    import logging

    from apps.tenants import siteconfig

    root = config.get("i18n") if isinstance(config, dict) else None
    node = root.get(locale) if isinstance(root, dict) else None
    if not isinstance(node, dict) or "seo" not in node:
        return {}
    seo = node.get("seo")
    pages = seo.get("pages") if isinstance(seo, dict) else None
    entry = pages.get(host) if isinstance(pages, dict) else None
    fatal = (
        not isinstance(pages, dict)
        or len(pages) > siteconfig._MAX_SEO_PAGES
        or (entry is not None and not isinstance(entry, dict))
    )
    foreign = not fatal and any(
        not siteconfig.is_seo_page_host(h) or not isinstance(v, dict) for h, v in pages.items()
    )
    if fatal or foreign:
        logging.getLogger(__name__).warning(
            "page_seo: broken seo overlay ignored (%s, %s)", locale, host
        )
    if fatal:
        return {}
    clean = siteconfig.clean_seo_page(entry)
    return {k: v for k, v in clean.items() if k in SEO_TR_FIELDS}


def page_seo(tenant, host: str, locale: str = "", config: dict | None = None) -> dict:
    """Свои заголовок/описание/noindex страницы (`{}` — не заданы). Стопка 16 T1b: `locale`
    (язык посетителя) — перевод поверх немецкого по полю, `noindex` — всегда из базы;
    `config` — показываемый конфиг (черновик в превью), иначе сохранённый."""
    from django.conf import settings

    from apps.tenants import siteconfig

    if config is None:
        config = getattr(tenant, "site_config", None) or {}
    if not siteconfig.is_seo_page_host(host):
        return {}
    seo = config.get("seo") if isinstance(config, dict) else None
    pages = seo.get("pages") if isinstance(seo, dict) else None
    entry = siteconfig.clean_seo_page(pages.get(host) if isinstance(pages, dict) else None)
    loc = (locale or "")[:2]
    if loc and loc != settings.LANGUAGE_CODE[:2] and loc in siteconfig.overlay_locales():
        entry.update(_seo_overlay(config, loc, host))
    return entry


def seo_tr_locales(config: dict, host: str, fields) -> list[str]:
    """Языки, у которых есть перевод одного из полей `fields` SEO страницы `host`."""
    out = []
    root = config.get("i18n") if isinstance(config.get("i18n"), dict) else {}
    for loc, node in sorted(root.items()):
        entry = (_seo_tr_pages(node) or {}).get(host)
        if isinstance(entry, dict) and any(entry.get(f) for f in fields):
            out.append(loc)
    return out


def _drop_seo_tr(config: dict, host: str, fields) -> None:
    for node in _i18n_nodes(config):
        entry = (_seo_tr_pages(node) or {}).get(host)
        if not isinstance(entry, dict):
            continue
        for field in fields:
            entry.pop(field, None)
        _prune_seo_tr(node)


def put_page_seo(config: dict, host: str, values) -> dict:
    """FB-33 M3-6: запись SEO одной страницы в `config` (на месте, без базы) — один писатель
    для вкладки «Suchmaschinen» (`save_page_seo`) и «Speichern» черновика «Seitenaufbau»
    (тот держит блокировку строки сам). Пустая запись — ключа нет.

    Стопка 16 T1b: изменённое немецкое ПОЛЕ снимает перевод этого поля у всех языков —
    сравнение по полю (`noindex` и запись без правки переводов не трогают); перевод, введённый
    в той же форме окна, пишет `block_i18n.apply` ПОСЛЕ (порядок «Speichern»)."""
    from apps.tenants import siteconfig

    entry = siteconfig.clean_seo_page(values)
    seo = dict(config.get("seo") or {}) if isinstance(config.get("seo"), dict) else {}
    pages = dict(seo.get("pages") or {}) if isinstance(seo.get("pages"), dict) else {}
    old = siteconfig.clean_seo_page(pages.get(host))
    changed = [f for f in SEO_TR_FIELDS if old.get(f, "") != entry.get(f, "")]
    if changed:
        _drop_seo_tr(config, host, changed)
    if entry:
        pages[host] = entry
    else:
        pages.pop(host, None)
    if pages:
        seo["pages"] = pages
    else:
        seo.pop("pages", None)
    if seo:
        config["seo"] = seo
    else:
        config.pop("seo", None)
    return entry


def save_page_seo(tenant, host: str, values: dict, dropped: list | None = None) -> dict:
    """Точечная запись SEO одной страницы под блокировкой строки: остальной `site_config`
    не трогается (экран открыт долго — целиком конфиг писать нельзя). `dropped` — языки, у
    которых правка немецкого сняла перевод (для сообщения экрана «Seiten»)."""
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    if not siteconfig.is_seo_page_host(host):
        raise PageError(_("Diese Seite hat keine eigenen Angaben für Suchmaschinen."))
    entry = siteconfig.clean_seo_page(values)
    with transaction.atomic():
        fresh = Tenant.objects.select_for_update().get(pk=tenant.pk)
        config = copy.deepcopy(fresh.site_config or {})
        old = page_seo(fresh, host, config=config)
        changed = [f for f in SEO_TR_FIELDS if old.get(f, "") != entry.get(f, "")]
        gone = seo_tr_locales(config, host, changed) if changed else []
        put_page_seo(config, host, entry)
        fresh.site_config = config
        fresh.save(update_fields=["site_config"])
        tenant.site_config = config
    if dropped is not None:
        dropped.extend(gone)
    return entry


def move_page_blocks(old: str, new: str | None, prefix: str = "seite:") -> bool:
    """M21.11: блоки своей страницы живут в ``page_blocks["seite:<slug>"]``. Смена адреса
    переносит их, удаление страницы — убирает (иначе хост-призрак занимал бы место в
    потолке хостов). Переводы блоков переезжают вместе с хостом.

    FB-27 R7: то же для своей схемы категории — ``prefix="catalog:"``."""
    from apps.tenants.models import Tenant

    tenant = getattr(connection, "tenant", None)
    if tenant is None or not getattr(tenant, "pk", None) or not old:
        return False
    src, dst = f"{prefix}{old}", f"{prefix}{new}" if new else None
    with transaction.atomic():
        fresh = Tenant.objects.select_for_update().filter(pk=tenant.pk).first()
        if fresh is None:
            return False
        config = copy.deepcopy(fresh.site_config or {})
        blocks = config.get("page_blocks") or {}
        seo_moved = _move_seo(config, src, dst)  # и у страницы без блоков
        if src not in blocks:
            if seo_moved:
                fresh.site_config = config
                fresh.save(update_fields=["site_config"])
                tenant.site_config = config
            return seo_moved
        moved = blocks.pop(src)
        if dst:
            blocks[dst] = moved
        config["page_blocks"] = blocks
        for loc_cfg in (config.get("i18n") or {}).values():
            pb = loc_cfg.get("page_blocks") if isinstance(loc_cfg, dict) else None
            if isinstance(pb, dict) and src in pb:
                over = pb.pop(src)
                if dst:
                    pb[dst] = over
        fresh.site_config = config
        fresh.save(update_fields=["site_config"])
        tenant.site_config = config
    return True


def system_url(slug: str, tenant=None) -> str | None:
    """Адрес системной страницы для slug (None — не системный или страница недоступна:
    «Versand» есть, пока магазин принимает заказы)."""
    name = SYSTEM_PAGES.get(slug)
    if not name:
        return None
    if name == "storefront-shipping":
        from django.db import connection

        from apps.core import modules

        tenant = tenant or getattr(connection, "tenant", None)
        try:
            active = modules.is_module_active(tenant, "orders")
        except Exception:  # noqa: BLE001 — нет тенанта: свой адрес страницы
            active = False
        if not active:
            return None
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def short_url_free(slug: str) -> bool:
    """M21.11: открывается ли /<slug>/ своей страницей (а не системным маршрутом)."""
    from django.urls import Resolver404, resolve

    try:
        return resolve(f"/{slug}/").url_name == "storefront-content-page"
    except Resolver404:
        return False


def content_url(slug: str) -> str:
    """Адрес своей страницы: короткий /<slug>/, если он не занят маршрутом витрины."""
    if short_url_free(slug):
        return reverse("storefront-content-page", args=[slug])
    return reverse("storefront-content-page-legacy", args=[slug])


def page_url(page, tenant=None) -> str:
    return system_url(page.slug, tenant) or content_url(page.slug)


def published(slug: str):
    """Опубликованная страница по slug или None (ошибки БД не роняют чужую страницу;
    savepoint — чтобы сбой не сломал внешнюю транзакцию)."""
    from django.db import DatabaseError, transaction

    from apps.core.models import ContentPage

    try:
        with transaction.atomic():
            return ContentPage.objects.filter(slug=slug, is_published=True).first()
    except DatabaseError:
        return None


def published_urls(tenant=None) -> dict:
    """{slug: адрес} всех опубликованных страниц — одним запросом (для меню)."""
    from django.db import DatabaseError, transaction

    from apps.core.models import ContentPage

    try:
        with transaction.atomic():
            slugs = list(
                ContentPage.objects.filter(is_published=True).values_list("slug", flat=True)
            )
    except DatabaseError:
        return {}
    out = {}
    for slug in slugs:
        try:
            out[slug] = system_url(slug, tenant) or content_url(slug)
        except NoReverseMatch:
            continue
    return out


def system_body(slug: str) -> str:
    """Текст своей страницы для системной (уже санитайзнутый), «» — нет такой."""
    page = published(slug)
    return sanitize_page(page.body_localized()) if page else ""


def system_title(slug: str) -> str:
    """Заголовок своей страницы для системной («» — нет такой)."""
    page = published(slug)
    return page.title_localized() if page else ""


def system_shows_shipping_methods(slug: str = "versand") -> bool:
    """M21.9: показывать ли под текстом «Versand» способы доставки (без своей
    страницы — показываем всегда: это единственная информация о доставке)."""
    page = published(slug)
    return page.show_shipping_methods if page else True


# --- M21.10: системные страницы в «Seiten» ---------------------------------------------


def system_available(slug: str, tenant=None) -> bool:
    """Показывать ли системную страницу в «Seiten» (у «Versand» — пока магазин
    принимает заказы: без модуля /versand/ отдаёт 404)."""
    if slug not in SYSTEM_PAGES:
        return False
    return slug == "ueber-uns" or system_url(slug, tenant) is not None


def _about_html(tenant) -> str:
    """Текст «Über uns» с главной (плоский) → абзацы страницы. Экранируем ДО разметки:
    в плоском тексте «<b>» — это буквы, а не тег."""
    from django.utils.html import escape

    text = ((getattr(tenant, "site_config", None) or {}).get("about_text") or "").strip()
    if not text:
        return ""
    paras = [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]
    return "".join("<p>" + escape(p).replace("\n", "<br>") + "</p>" for p in paras)


def initial_system_page(slug: str, tenant=None):
    """Несохранённая системная страница для формы «Bearbeiten» (GET ничего не пишет:
    запись — только «Speichern»). «Über uns» начинается с текста главной."""
    from apps.core.models import ContentPage

    body = _about_html(tenant) if slug == "ueber-uns" else ""
    return ContentPage(
        slug=slug, title=str(SYSTEM_TITLES.get(slug, slug)), body=body, is_published=True
    )


def system_rows(tenant=None) -> list:
    """Строки «Systemseiten» хаба — только чтение. state: own | draft | auto."""
    from types import SimpleNamespace

    from apps.core.models import ContentPage

    pages = {p.slug: p for p in ContentPage.objects.filter(slug__in=list(SYSTEM_PAGES))}
    rows = []
    for slug in SYSTEM_PAGES:
        if not system_available(slug, tenant):
            continue
        page = pages.get(slug)
        if page is None:
            state = "auto"
        else:
            state = "own" if page.is_published else "draft"
        rows.append(
            SimpleNamespace(
                slug=slug,
                title=page.title if page else str(SYSTEM_TITLES[slug]),
                url=system_url(slug, tenant) or "",
                page=page,
                state=state,
            )
        )
    return rows


# --- M21.11: один список всех страниц ---------------------------------------------------

#: Правовые страницы: вид → url-name витрины. Impressum и Datenschutz нельзя удалить
#: (§ 5 DDG, Art. 13 DSGVO); остальные «удаляются» очисткой своего текста в форме.
LEGAL_PAGES = (
    ("impressum", "storefront-impressum"),
    ("datenschutz", "storefront-privacy"),
    ("widerruf", "storefront-withdrawal"),
    ("agb", "storefront-agb"),
)
#: Ссылки подвала, которые витрина ставит сама (`storefront/_base.html`).
_AUTO_FOOTER = {"impressum", "datenschutz", "widerruf"}


def _menu_urls(tenant) -> tuple[set, set]:
    """Адреса пунктов шапки/нижнего меню и колонок подвала (fail-safe: пусто)."""
    from apps.tenants import menu

    def walk(items, out):
        for item in items or []:
            if item.get("url"):
                out.add(item["url"].split("#")[0])
            walk(item.get("children"), out)

    in_menu, in_footer = set(), set()
    try:
        walk(menu.resolve_menu(tenant, "top"), in_menu)
        walk(menu.resolve_menu(tenant, "bottom"), in_menu)
        for col in menu.resolve_footer(tenant):
            walk(col.get("items"), in_footer)
    except Exception:  # noqa: BLE001 — колонка «Sichtbar» не роняет список страниц
        pass
    return in_menu, in_footer


def all_rows(tenant=None) -> list:
    """Строки списка «Seiten» — системные, правовые и свои вперемешку (решение
    владельца M21.11: без групп). Только чтение. Порядок: страницы, на которые есть
    ссылка с сайта (меню/подвал), затем остальные; внутри — по названию."""
    from types import SimpleNamespace

    from django.db import DatabaseError

    from apps.core.models import ContentPage, LegalDoc

    tenant = tenant or getattr(connection, "tenant", None)
    in_menu, in_footer = _menu_urls(tenant)
    locale = (getattr(tenant, "default_locale", "") or "de").split("-")[0]

    def where(url, auto_footer=False):
        places = []
        if url and url in in_menu:
            places.append("menu")
        if auto_footer or (url and url in in_footer):
            places.append("footer")
        return places

    rows = []
    system = {row.slug: row for row in system_rows(tenant)}
    for slug, row in system.items():
        rows.append(
            SimpleNamespace(
                key=f"system:{slug}",
                kind="system",
                art=str(SYSTEM_ART[slug]),
                title=row.title,
                url=row.url,
                state=row.state,
                langs=[],
                page=row.page,
                edit_name="content-page-edit" if row.page else "content-page-system",
                edit_arg=row.page.pk if row.page else slug,
                deletable=bool(row.page),
                places=where(row.url, auto_footer=(slug == "versand")),
            )
        )
    try:
        langs: dict = {}
        for kind, loc in (
            LegalDoc.objects.exclude(text="").values_list("kind", "locale").order_by("locale")
        ):
            langs.setdefault(kind, []).append(loc)
    except DatabaseError:
        langs = {}
    labels = dict(LegalDoc.KIND_CHOICES)
    for kind, url_name in LEGAL_PAGES:
        have = langs.get(kind, [])
        if locale in have or (kind == "agb" and have):
            state = "own"
        elif kind == "agb":
            state = "off"  # без текста страницы /agb/ нет
        else:
            state = "auto"
        url = reverse(url_name)
        rows.append(
            SimpleNamespace(
                key=f"legal:{kind}",
                kind="legal",
                art=str(labels[kind]),
                title=str(labels[kind]),
                url=url,
                state=state,
                langs=have,
                page=None,
                edit_name="legal-page-edit",
                edit_arg=kind,
                deletable=False,
                places=where(
                    url, auto_footer=kind in _AUTO_FOOTER or (kind == "agb" and state == "own")
                ),
            )
        )
    for page in ContentPage.objects.exclude(slug__in=list(system)):
        url = page_url(page, tenant)
        rows.append(
            SimpleNamespace(
                key=f"page:{page.slug}",
                kind="own",
                art="",
                title=page.title,
                url=url,
                state="own" if page.is_published else "draft",
                langs=[],
                page=page,
                edit_name="content-page-edit",
                edit_arg=page.pk,
                deletable=True,
                places=where(url) if page.is_published else [],
            )
        )
    rows.sort(key=lambda r: (not r.places, r.title.lower()))
    _attach_blocks(rows, tenant)
    return rows


def schema_ref(slug: str, tenant=None) -> tuple[str, str]:
    """FB-27 «Seiten»: (хост блоков, код строки «Seitenaufbau») страницы с адресом `slug`.
    Стопка 16 (ревью V1, после E10): системный слаг без своей системной страницы («Versand»
    без заказов) живёт своей страницей на `/seite/<slug>/` и рисует блоки и SEO хоста
    `seite:<slug>` (`content_page_views.storefront_page`, `studio_pages.resolve_match`)."""
    from apps.core import site_schema

    host = {"ueber-uns": "info", "versand": "versand"}.get(slug)
    # только «Versand» доступна не всегда (`system_url`); «Über uns» — всегда (и без urlconf)
    if host is None or (host == "versand" and system_url(slug, tenant) is None):
        host = f"seite:{slug}"
    return host, (site_schema.TEXT if host == "info" else f"{site_schema.TEXT}@{host}")


def edit_url_for_code(code: str) -> str:
    """Адрес редактора страницы, чью схему открывает код «Seitenaufbau» (`text`,
    `text@versand`, `text@seite:<slug>`); «» — такой страницы нет. Адрес собирается по
    имени маршрута — возврат из «Seitenaufbau» не принимает адрес из запроса."""
    from apps.core import site_schema
    from apps.core.models import ContentPage

    base, _sep, host = str(code or "").partition("@")
    if base != site_schema.TEXT:
        return ""
    if not host:
        slug = "ueber-uns"
    elif host == "versand":
        slug = host
    elif host.startswith("seite:"):
        slug = host[len("seite:") :]
    else:
        return ""
    pk = ContentPage.objects.filter(slug=slug).values_list("pk", flat=True).first()
    if pk is not None:
        return reverse("content-page-edit", args=[pk])
    if slug in SYSTEM_PAGES:
        return reverse("content-page-system", args=[slug])
    return ""


def _attach_blocks(rows: list, tenant) -> None:
    """FB-27 «Seiten»: колонка «Blöcke» — что стоит на странице кроме её текста, и адрес
    её схемы в «Seitenaufbau». Один normalize на весь список, без запросов на строку; у
    правовых текстов блоков нет."""
    import logging

    from apps.core import site_schema
    from apps.tenants import siteconfig

    log = logging.getLogger(__name__)
    try:
        config = siteconfig.normalize(getattr(tenant, "site_config", None) or {})
    except Exception:  # noqa: BLE001 — колонка не роняет список страниц
        log.warning("pages list: blocks column, normalize failed", exc_info=True)
        config = {}
    for row in rows:
        row.blocks, row.schema_url, row.host = "", "", ""
        if row.kind == "legal":
            continue
        slug = row.key.split(":", 1)[1]
        host, code = (
            schema_ref(slug, tenant)
            if row.kind == "system"
            else (
                f"seite:{slug}",
                f"{site_schema.TEXT}@seite:{slug}",
            )
        )
        row.host = host
        row.schema_url = f"{reverse('site-schema')}?seite={code}"
        try:
            blocks = site_schema.blocks_for(config, code, host=host, summaries=False, tenant=tenant)
        except Exception:  # noqa: BLE001 — колонка пуста, но ошибку видно в журнале
            log.warning("pages list: blocks column failed for %s", code, exc_info=True)
            continue
        # FB-32 S6a: строка самого текста страницы — не «блок на странице»
        labels = [
            str(b["label"])
            for b in blocks
            if b["enabled"] and not b["main"] and not (b["key"] == "pagetext" and not b["cblock"])
        ]
        if labels:
            row.blocks = labels[0] + (f" + {len(labels) - 1}" if len(labels) > 1 else "")


# --- FB-27 R6: блок «Textseite einbinden» -------------------------------------------------

#: Сколько знаков текста показывает блок в режиме «Anfang + Weiterlesen».
TEASER_CHARS = 300
#: Хост блоков системной страницы → slug страницы, чей текст на ней выводится.
_SYSTEM_HOSTS = {"info": "ueber-uns", "versand": "versand"}


def embeds_itself(slug: str, host: str) -> bool:
    """Стоит ли блок с этой страницей на ней же самой (`host` — хост блоков страницы)."""
    if not slug or not host:
        return False
    return host == f"seite:{slug}" or _SYSTEM_HOSTS.get(host) == slug


def embed_choices(host: str = "") -> list[tuple[str, str]]:
    """Страницы, которые блок может показать: [(uuid, название)] — без той, на которой
    он стоит. Неопубликованные видны с пометкой: блок появится на сайте вместе с ними."""
    from apps.core.models import ContentPage

    draft = _("Entwurf")
    out = []
    for page in ContentPage.objects.order_by("sort_order", "title")[:200]:
        if embeds_itself(page.slug, host):
            continue
        out.append((str(page.pk), page.title if page.is_published else f"{page.title} ({draft})"))
    return out


def embedded(data, host: str = "", tenant=None) -> dict | None:
    """Что блок «Textseite» выводит на сайте: {title, body | teaser, url} либо None
    (страницы нет, она не опубликована или блок стоит на ней самой). Ошибки БД не
    роняют страницу, на которой стоит блок."""
    from django.core.exceptions import ValidationError
    from django.db import DatabaseError

    from apps.core.models import ContentPage
    from apps.core.richtext import to_plain

    pk = (data or {}).get("page") if isinstance(data, dict) else None
    if not pk:
        return None
    try:
        with transaction.atomic():
            page = ContentPage.objects.filter(pk=pk, is_published=True).first()
    except (DatabaseError, ValidationError, ValueError):
        return None
    if page is None or embeds_itself(page.slug, host):
        return None
    out = {"title": page.title_localized(), "url": page_url(page, tenant)}
    out["is_teaser"] = data.get("mode") == "teaser"
    if out["is_teaser"]:
        # Начало — обычным текстом (шаблон его экранирует): чистить разметку 200 КБ ради
        # трёхсот знаков незачем.
        plain = " ".join(to_plain(page.body_localized()).split())
        cut = plain[:TEASER_CHARS].rsplit(" ", 1)[0] if len(plain) > TEASER_CHARS else plain
        out["teaser"] = cut + ("…" if len(plain) > len(cut) else "")
    else:
        # Заголовок блока — h2, поэтому заголовки самого текста уходят на уровень ниже:
        # иначе разделы страницы читались бы соседями её названия.
        body = sanitize_page(page.body_localized())
        for src, dst in (("h3", "h4"), ("h2", "h3")):
            body = re.sub(rf"<(/?){src}(?=[\s>])", rf"<\1{dst}", body)
        out["body"] = body
    return out
