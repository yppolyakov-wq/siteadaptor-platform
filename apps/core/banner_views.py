"""FB-29.2 S2: кабинет «Website › Banner» — библиотека баннеров.

Список плитками, форма, удаление отдельным шагом с вопросом. Писатель один —
`apps/core/banners.py`; форма передаёт только свои поля (порядок и ключ переноса из неё
прислать нельзя). Права — `view_perms`: чтение `website.view`, запись `website.edit`.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.core import banners
from apps.core.models import Banner
from apps.core.view_perms import perm_required

#: поле формы → поле баннера (белый список; всё прочее из POST игнорируется)
_FORM_FIELDS = {
    "b_title": "title",
    "b_text": "text",
    "b_btn_label": "button_label",
    "b_btn_url": "button_url",
    "b_link": "link",
    "b_align": "align",
    "b_overlay": "overlay",
    "b_tone": "tone",
    "b_starts": "starts",
    "b_ends": "ends",
}


def _raw(request, banner=None) -> dict:
    """Поля формы → сырые значения для `banners.clean_fields`. Новое фото — файл или
    адрес; иначе остаётся прежнее. Ошибка файла — ValidationError."""
    post = request.POST
    raw = {field: post.get(name, "").strip() for name, field in _FORM_FIELDS.items()}
    raw["click_all"] = bool(post.get("b_click_all"))
    raw["is_active"] = bool(post.get("b_is_active"))
    raw["image"] = dict(banner.image or {}) if banner is not None else {}
    uploaded = request.FILES.get("b_image")
    url = post.get("b_image_url", "").strip()
    if uploaded:
        from apps.catalog.images import save_product_image

        raw["image"] = save_product_image(
            uploaded, folder="hero"
        )  # папка баннеров главной — уже в классификаторе
    elif url and url != raw["image"].get("url"):
        raw["image"] = {"url": url}
    return raw


def _form(request, banner, values, error=""):
    from apps.tenants import menu

    return render(
        request,
        "tenant/banner_form.html",
        {
            "nav": "site-banners",
            "banner": banner,
            "h": values,
            "error": error,
            "menu_target_options": menu.target_options(request.tenant),
            "places": banners.places(request.tenant, banner) if banner else [],
        },
    )


def _values(banner) -> dict:
    """Запись → значения полей формы (те же имена, что у слайда)."""
    return {
        "title": banner.title,
        "text": banner.text,
        "button_label": banner.button_label,
        "button_url": banner.button_url,
        "link": banner.link,
        "align": banner.align,
        "overlay": banner.overlay,
        "tone": banner.tone,
        "starts": banner.starts.isoformat() if banner.starts else "",
        "ends": banner.ends.isoformat() if banner.ends else "",
        "click_all": banner.click_all,
        "is_active": banner.is_active,
        "image": (banner.image or {}).get("url", ""),
    }


def _typed(raw: dict) -> dict:
    """Набранное владельцем — обратно в форму после ошибки (ничего не теряется)."""
    return {**raw, "image": (raw.get("image") or {}).get("url", "")}


def _save(request, banner):
    try:
        raw = _raw(request, banner)
    except ValidationError as exc:
        values = _typed({**{f: request.POST.get(n, "") for n, f in _FORM_FIELDS.items()}})
        return _form(request, banner, values, "; ".join(exc.messages))
    try:
        if banner is None:
            banners.create(raw)
        else:
            banners.update(banner, raw)
    except ValueError as exc:
        error = (
            _("Bitte ein gültiges Datum eingeben.")
            if str(exc) == "date"
            else _("Ein Banner braucht ein Foto, eine Überschrift oder einen Text.")
        )
        return _form(request, banner, _typed(raw), error)
    messages.success(request, _("Banner gespeichert."))
    return redirect("site-banners")


@login_required
def banner_list(request):
    query = request.GET.get("q", "").strip()
    rows = Banner.objects.all()
    if query:
        rows = rows.filter(Q(title__icontains=query) | Q(text__icontains=query))
    return render(
        request,
        "tenant/banners.html",
        {"nav": "site-banners", "banners": list(rows[:200]), "q": query},
    )


@login_required
def banner_new(request):
    if request.method == "POST":
        return _write_new(request)
    return _form(request, None, {"is_active": True})


@perm_required("website.edit")
def _write_new(request):
    return _save(request, None)


@login_required
def banner_edit(request, pk):
    banner = get_object_or_404(Banner, pk=pk)
    if request.method == "POST":
        return _write_edit(request, banner)
    return _form(request, banner, _values(banner))


@perm_required("website.edit")
def _write_edit(request, banner):
    return _save(request, banner)


@login_required
def banner_delete(request, pk):
    banner = get_object_or_404(Banner, pk=pk)
    if request.method == "POST":
        return _write_delete(request, banner)
    return render(
        request,
        "tenant/banner_delete.html",
        {"nav": "site-banners", "banner": banner, "places": banners.places(request.tenant, banner)},
    )


@perm_required("website.edit")
def _write_delete(request, banner):
    banners.delete(request.tenant, banner)
    messages.success(request, _("Banner gelöscht."))
    return redirect("site-banners")
