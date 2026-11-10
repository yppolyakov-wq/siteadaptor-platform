"""M21.6: свои страницы сайта — витрина ``/seite/<slug>/`` и кабинет «Website › Seiten».

Права кабинета — ``view_perms`` (чтение W, запись WE), правила — ``content_pages``.
"""

from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import content_pages
from apps.core.models import ContentPage
from apps.core.richtext import sanitize_page


def _is_team(request) -> bool:
    from apps.core.roles import has_cabinet_access

    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and has_cabinet_access(user))


def storefront_page(request, slug):
    page = ContentPage.objects.filter(slug=slug).first()
    if page is None or (not page.is_published and not _is_team(request)):
        raise Http404
    target = content_pages.system_url(page.slug, getattr(request, "tenant", None))
    if target and page.is_published:
        return redirect(target, permanent=True)
    return render(
        request,
        "storefront/content_page.html",
        {
            "page": page,
            "page_title": page.title_localized(),
            "page_body": sanitize_page(page.body_localized()),
            "is_draft": not page.is_published,
        },
    )


# --- кабинет ------------------------------------------------------------------------


@login_required
def pages_list(request):
    pages = list(ContentPage.objects.all())
    for page in pages:
        page.url = content_pages.page_url(page)
        page.system_label = content_pages.SYSTEM_LABELS.get(page.slug, "")
    return render(request, "tenant/content_pages.html", {"pages": pages, "nav": "content-pages"})


def _form(request, page, *, created: bool):
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
            )
        except content_pages.PageError as exc:
            messages.error(request, str(exc))
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
            "system_label": content_pages.SYSTEM_LABELS.get(saved_slug, ""),
            "nav": "content-pages",
        },
    )


@login_required
def page_new(request):
    return _form(request, ContentPage(is_published=True), created=True)


@login_required
def page_edit(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    return _form(request, page, created=False)


@login_required
@require_POST
def page_delete(request, pk):
    if ContentPage.objects.filter(pk=pk).delete()[0]:
        messages.success(request, _("Seite gelöscht."))
    return redirect("content-pages")
