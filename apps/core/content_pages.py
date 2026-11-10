"""M21.6: свои страницы сайта (`core.ContentPage`) — единственное место правил.

- адрес страницы — ``/seite/<slug>/``;
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
SLUG_MAX = 80
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


def save_page(page, *, title: str, slug: str, body: str, is_published: bool):
    """Единственный писатель полей страницы из кабинета (HTML — через санитайзер)."""
    title = (title or "").strip()[:200]
    if not title:
        raise PageError(_("Bitte einen Titel angeben."))
    old_slug = "" if page._state.adding else page.slug
    new_slug = clean_slug(slug or old_slug or title, exclude_pk=page.pk)
    page.title = title
    page.slug = new_slug
    page.body = sanitize_page(body or "")
    page.is_published = bool(is_published)
    try:
        with transaction.atomic():
            page.save()
    except IntegrityError as exc:  # тот же адрес сохранили параллельно
        raise PageError(_("Diese Adresse ist schon vergeben.")) from exc
    if old_slug and old_slug != new_slug:
        retarget_menus(old_slug, new_slug)
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


def page_url(page, tenant=None) -> str:
    return system_url(page.slug, tenant) or reverse("storefront-content-page", args=[page.slug])


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
            out[slug] = system_url(slug, tenant) or reverse("storefront-content-page", args=[slug])
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
