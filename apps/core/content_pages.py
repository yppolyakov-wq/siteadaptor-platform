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


def move_page_blocks(old: str, new: str | None) -> bool:
    """M21.11: блоки своей страницы живут в ``page_blocks["seite:<slug>"]``. Смена адреса
    переносит их, удаление страницы — убирает (иначе хост-призрак занимал бы место в
    общем потолке хостов). Переводы блоков переезжают вместе с хостом."""
    from apps.tenants.models import Tenant

    tenant = getattr(connection, "tenant", None)
    if tenant is None or not getattr(tenant, "pk", None) or not old:
        return False
    src, dst = f"seite:{old}", f"seite:{new}" if new else None
    with transaction.atomic():
        fresh = Tenant.objects.select_for_update().filter(pk=tenant.pk).first()
        if fresh is None:
            return False
        config = copy.deepcopy(fresh.site_config or {})
        blocks = config.get("page_blocks") or {}
        if src not in blocks:
            return False
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
    return rows
