"""M21.6: свои страницы сайта — витрина ``/seite/<slug>/`` и кабинет «Website › Seiten».

Права кабинета — ``view_perms`` (чтение W, запись WE), правила — ``content_pages``.
"""

from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import content_pages, page_starters
from apps.core.models import ContentPage
from apps.core.richtext import sanitize_page
from apps.core.view_perms import perm_required


def _can_preview(request) -> bool:
    """Черновик видит тот, кто может открыть «Website › Seiten» (ревью: не любой
    сотрудник кабинета)."""
    from apps.core import view_perms
    from apps.core.roles import has_cabinet_access

    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and has_cabinet_access(user)):
        return False
    return view_perms.allowed(user, "content-pages", "GET")


def storefront_page(request, slug):
    page = ContentPage.objects.filter(slug=slug).first()
    if page is None or (not page.is_published and not _can_preview(request)):
        raise Http404
    target = content_pages.system_url(page.slug, getattr(request, "tenant", None))
    if target and page.is_published:
        return redirect(target, permanent=True)
    response = render(
        request,
        "storefront/content_page.html",
        {
            "page": page,
            "page_title": page.title_localized(),
            "page_body": sanitize_page(page.body_localized()),
            "is_draft": not page.is_published,
        },
    )
    if not page.is_published:
        response["Cache-Control"] = "private, no-store"  # черновик не кэшируется
    return response


def storefront_page_legacy(request, slug):
    """M21.11: старый адрес /seite/<slug>/ — 301 на короткий /<slug>/ (ссылки из писем,
    поисковиков и меню не ломаются). Короткий занят системной страницей — отдаём
    страницу здесь же."""
    if content_pages.short_url_free(slug) and ContentPage.objects.filter(slug=slug).exists():
        target = reverse("storefront-content-page", args=[slug])
        query = request.META.get("QUERY_STRING", "")
        return redirect(f"{target}?{query}" if query else target, permanent=True)
    return storefront_page(request, slug)


# --- кабинет ------------------------------------------------------------------------


@login_required
def pages_list(request):
    """M21.11: ОДИН список всех текстовых страниц сайта — системные (Über uns, Versand),
    правовые и свои вперемешку, без групп (решение владельца)."""
    return render(
        request,
        "tenant/content_pages.html",
        {
            "rows": content_pages.all_rows(getattr(request, "tenant", None)),
            "starters": page_starters.STARTERS,
            "nav": "content-pages",
        },
    )


def _form(request, page, *, created: bool):
    """Форма страницы. Системная (Über uns/Versand) — с закреплённым адресом."""
    # UUID-pk есть и у несохранённой страницы — признак записи в БД только _state.
    saved_slug = "" if page._state.adding else page.slug
    if request.method == "POST":
        try:
            content_pages.save_page(
                page,
                title=request.POST.get("title", ""),
                slug=request.POST.get("slug", ""),
                body=request.POST.get("body", ""),
                is_published=request.POST.get("is_published") == "1",
                # M21.9: галочка есть только у «Versand» — без сентинела поле не трогаем.
                show_shipping_methods=(request.POST.get("show_shipping_methods") == "1")
                if request.POST.get("shipping_present")
                else None,
            )
        except content_pages.PageError as exc:
            messages.error(request, str(exc))
            # Ввод не теряем: форма показывает то, что набрал владелец.
            page.title = request.POST.get("title", "")[:200]
            if page.slug not in content_pages.SYSTEM_PAGES:  # адрес системной закреплён
                page.slug = request.POST.get("slug", "")[: content_pages.SLUG_MAX]
            page.body = sanitize_page(request.POST.get("body", ""))
        else:
            messages.success(request, _("Seite angelegt.") if created else _("Seite gespeichert."))
            return redirect("content-page-edit", pk=page.pk)
    return render(
        request,
        "tenant/content_page_form.html",
        {
            "page": page,
            "created": created,
            "page_url": content_pages.page_url(
                SimpleNamespace(slug=saved_slug), getattr(request, "tenant", None)
            )
            if saved_slug
            else "",
            "is_saved": bool(saved_slug),
            "saved_slug": saved_slug,
            "system_label": content_pages.SYSTEM_LABELS.get(saved_slug or page.slug, ""),
            "is_system": (saved_slug or page.slug) in content_pages.SYSTEM_PAGES,
            "nav": "content-pages",
        },
    )


@login_required
@perm_required("seiten.edit")
def page_new(request):
    """M21.11 P4: «＋ Neue Seite» — пустая или заготовка (`?vorlage=`). GET ничего не
    пишет: заготовка только заполняет форму, страница появится по «Speichern»."""
    page = ContentPage(is_published=True)
    if request.method == "GET":
        page.title, page.body = page_starters.build(
            request.GET.get("vorlage", ""), getattr(request, "tenant", None)
        )
    return _form(request, page, created=True)


@login_required
@perm_required("seiten.edit")
def page_system(request, slug):
    """M21.10: «Bearbeiten» системной страницы (Über uns, Versand). Есть своя страница —
    открываем её; нет — форма с несохранённой заготовкой: GET ничего не пишет
    (security-review), страница появляется только по «Speichern» (POST + CSRF)."""
    tenant = getattr(request, "tenant", None)
    if not content_pages.system_available(slug, tenant):
        raise Http404
    page = ContentPage.objects.filter(slug=slug).first()
    if page is not None:
        return redirect("content-page-edit", pk=page.pk)
    return _form(request, content_pages.initial_system_page(slug, tenant), created=True)


@login_required
@perm_required("seiten.edit")
def page_edit(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    return _form(request, page, created=False)


@login_required
@perm_required("seiten.edit")
@require_POST
def page_delete(request, pk):
    page = ContentPage.objects.filter(pk=pk).first()
    if page is not None:
        refs = content_pages.menu_references(page.slug, getattr(request, "tenant", None))
        page.delete()
        messages.success(request, _("Seite gelöscht."))
        if refs:
            messages.warning(
                request,
                _(
                    "Der Menüpunkt zu dieser Seite wird nicht mehr angezeigt — bitte im Menü entfernen."
                ),
            )
    return redirect("content-pages")


@login_required
@perm_required("seiten.edit")
def page_media_list(request):
    """M21.11 P5: «🗂 Aus der Mediathek» — уже загруженные картинки бизнеса (JSON).

    Только чтение; только адреса нашей папки медиа (санитайзер страниц иных не
    пропустит). Подпись — описание картинки на языке бизнеса, если оно есть."""
    from django.conf import settings

    from apps.core import media_registry
    from apps.core.models import MediaAsset

    if not MediaAsset.objects.exists():
        media_registry.backfill(getattr(request, "tenant", None))
    media = (getattr(settings, "MEDIA_URL", "") or "/media/").strip()
    items = []
    assets = MediaAsset.objects.filter(mime_type__startswith="image/").order_by("-created_at")
    for a in assets[:120]:
        url = a.url or ""
        if not url.startswith(media) or media in ("", "/"):
            continue
        alt = a.alt.get("de", "") if isinstance(a.alt, dict) else ""
        items.append({"url": url, "alt": str(alt)[:300]})
        if len(items) >= 60:
            break
    return JsonResponse({"items": items})


@login_required
@perm_required("seiten.edit")
@require_POST
def page_image_upload(request):
    """M21.8 B4: «🖼 Bild» в редакторе своей страницы — файл с компьютера.

    Тот же путь, что фото товара (проверка формата/размера, реестр медиа) + снятие
    EXIF (SEC-G14);
    ответ — адрес картинки у нас (санитайзер страниц пропускает только /media/…)."""
    from django.core.exceptions import ValidationError

    from apps.catalog.images import (
        save_product_image,
        shrink_large_photo,
        strip_metadata,
        validate_image,
    )
    from apps.core import ratelimit

    tenant = getattr(request, "tenant", None)
    ident = f"{getattr(tenant, 'schema_name', '')}:{request.user.pk}"
    if ratelimit.hit("page-image", ident, limit=60, window=3600):
        return JsonResponse({"error": _("Zu viele Uploads. Bitte später erneut.")}, status=429)
    uploaded = request.FILES.get("image")
    if uploaded is None:
        return JsonResponse({"error": _("Bitte ein Bild wählen.")}, status=400)
    try:
        uploaded = shrink_large_photo(uploaded)
        # Картинка страницы публична — без EXIF (GPS-координаты, модель телефона).
        uploaded = strip_metadata(uploaded, validate_image(uploaded))
        ref = save_product_image(uploaded, folder="pages")
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    except ValueError:  # слишком большое изображение для перекодирования
        return JsonResponse({"error": _("Das Bild konnte nicht hochgeladen werden.")}, status=400)
    return JsonResponse({"url": ref["url"]})


# --- M21.10: правовые тексты прямо в «Seiten» ----------------------------------------


@login_required
@perm_required("seiten.edit")
def legal_page_edit(request, kind):
    """Правовой текст (Impressum/Datenschutz/Widerruf/AGB) по языкам — тот же редактор,
    что у страниц. Хранилище — ``LegalDoc``, писатель — ``legal.save_legal_doc``.
    Право — только владелец (``view_perms``: FLOOR на GET и POST, § 5 DDG)."""
    from django.conf import settings

    from apps.core import legal
    from apps.core.models import LegalDoc

    labels = dict(LegalDoc.KIND_CHOICES)
    if kind not in labels:
        raise Http404
    tenant = request.tenant
    locales = list(tenant.active_locales) or [settings.LANGUAGE_CODE]
    posted = {}
    if request.method == "POST":
        posted = {
            loc: request.POST.get(f"doc_{loc}")
            for loc in locales
            if request.POST.get(f"doc_{loc}") is not None  # presence-guard
        }
        if any(len(v) > legal.LEGAL_TEXT_MAX for v in posted.values()):
            messages.error(request, _("Der Text ist zu lang."))  # ничего не пишем, ввод цел
        else:
            for loc, value in posted.items():
                legal.save_legal_doc(kind, loc, value)
            messages.success(request, _("Gespeichert."))
            return redirect("legal-page-edit", kind=kind)
    docs = dict(LegalDoc.objects.filter(kind=kind).values_list("locale", "text"))
    docs.update({loc: sanitize_page(v) for loc, v in posted.items()})
    names = dict(settings.LANGUAGES)
    shown = settings.LANGUAGE_CODE if settings.LANGUAGE_CODE in locales else locales[0]
    cells = [
        {
            "locale": loc,
            "locale_label": str(names.get(loc, loc.upper())),
            "text": docs.get(loc, ""),
            # что покажет витрина при пустом поле — и чем можно заполнить поле
            "fallback": ""
            if kind == "agb"
            else legal.legal_text(tenant, kind, locale=loc)
            if not docs.get(loc)
            else "",
        }
        for loc in locales
    ]
    url_name = dict(content_pages.LEGAL_PAGES)[kind]
    from django.urls import reverse

    return render(
        request,
        "tenant/legal_page_form.html",
        {
            "kind": kind,
            "label": labels[kind],
            "cells": cells,
            "page_url": reverse(url_name),
            "legal_shown_locale": shown,
            "i18n_groups": [
                {"code": loc, "label": str(names.get(loc, loc.upper())), "is_base": loc == shown}
                for loc in locales
            ],
            "i18n_multi": len(locales) > 1,
            "nav": "content-pages",
        },
    )
