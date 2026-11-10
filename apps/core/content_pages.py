"""M21.6: свои страницы сайта (`core.ContentPage`) — единственное место правил.

- адрес страницы — ``/seite/<slug>/``;
- slug из ``SYSTEM_PAGES`` — текст СИСТЕМНОЙ страницы (``versand`` → ``/versand/``,
  ``ueber-uns`` → ``/ueber-uns/``): одна страница — один адрес, второй адрес даёт 301;
- неопубликованная страница видна только члену команды (предпросмотр).

План — ``docs/m21-6-content-pages-plan-2026-11-10.md``.
"""

from __future__ import annotations

import re

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
        taken = taken.exclude(pk=exclude_pk)
    if taken.exists():
        raise PageError(_("Diese Adresse ist schon vergeben."))
    return slug


def save_page(page, *, title: str, slug: str, body: str, is_published: bool):
    """Единственный писатель полей страницы из кабинета (HTML — через санитайзер)."""
    title = (title or "").strip()[:200]
    if not title:
        raise PageError(_("Bitte einen Titel angeben."))
    page.title = title
    page.slug = clean_slug(slug or title, exclude_pk=page.pk if page.pk else None)
    page.body = sanitize_page(body or "")
    page.is_published = bool(is_published)
    page.save()
    return page


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
    """Опубликованная страница по slug или None (ошибки БД не роняют чужую страницу)."""
    from apps.core.models import ContentPage

    try:
        return ContentPage.objects.filter(slug=slug, is_published=True).first()
    except Exception:  # noqa: BLE001 — системная страница живёт и без своего текста
        return None


def system_body(slug: str) -> str:
    """Текст своей страницы для системной (уже санитайзнутый), «» — нет такой."""
    page = published(slug)
    return sanitize_page(page.body_localized()) if page else ""
