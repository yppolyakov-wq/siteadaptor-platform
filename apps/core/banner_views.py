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

    place_kinds = banners.place_kinds()
    kind = request.GET.get("art") or ""
    if kind not in {k["key"] for k in place_kinds}:
        kind = ""
    checked = request.POST.getlist("b_show_add") if request.method == "POST" else []
    query = request.GET.get("wo") or ""
    if kind or query:
        groups = banners.place_search(query, exclude=banner.show_on if banner else (), kind=kind)
    elif checked:
        # после ошибки отмеченные страницы остаются в форме отмеченными (R4)
        labels = banners.place_labels(checked)
        groups = [
            {
                "label": _("Ausgewählt"),
                "items": [{"value": v, "label": labels[v]} for v in checked if v in labels],
            }
        ]
    else:
        groups = []

    return render(
        request,
        "tenant/banner_form.html",
        {
            "nav": "site-banners",
            "banner": banner,
            "h": values,
            "preview_image": _preview_image(values),
            "error": error,
            "menu_target_options": menu.target_options(request.tenant),
            "places": banners.places(request.tenant, banner) if banner else [],
            # FB-29.2c: «Wo zeigen» — страницы, где баннер показывается сам
            "show_on": banners.show_on_rows(request.tenant, banner) if banner else [],
            # R1: поиск страниц (GET `wo`) — по всем записям, выбранные не предлагаются
            # R4: после ошибки отмеченные страницы остаются отмеченными
            "show_checked": checked,
            "show_query": (request.GET.get("wo") or "").strip()[:80],
            # FB-30.7: «＋ Ort hinzufügen» — сначала вид страницы (`art`), потом список
            # этого вида; поиск без вида ищет по всем
            "place_kinds": place_kinds,
            "place_kind": kind,
            "show_groups": groups,
            "home_on": banners.on_home(request.tenant, banner) if banner else False,
            "status": banners.status(request.tenant, banner) if banner else [],
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


def _preview_image(values: dict) -> str:
    return banners.safe_image_url(values.get("image"))


def _save(request, banner):
    try:
        raw = _raw(request, banner)
    except ValidationError as exc:
        values = _typed({**{f: request.POST.get(n, "") for n, f in _FORM_FIELDS.items()}})
        return _form(request, banner, values, "; ".join(exc.messages))
    want_home = bool(request.POST.get("b_home_present") and request.POST.get("b_home"))
    if want_home and banners.home_full(request.tenant, banner):
        # проверка ДО записи: иначе баннер сохранился бы, а форма показала бы ошибку, и
        # повторная отправка новой формы завела бы второй такой же баннер (ревью FB-30.7)
        error = _("Auf der Startseite sind schon %(n)s Banner – erst einen dort abwählen.") % {
            "n": banners.MAX_SLIDES
        }
        return _form(request, banner, _typed(raw), error)
    try:
        if banner is None:
            banner = banners.create(raw)
        else:
            banners.update(banner, raw)
        if request.POST.get("b_show_present"):
            # FB-29.2c: места показа — по сентинелу (W0); новое место — только из списка
            banners.set_show_on(
                banner,
                keep=request.POST.getlist("b_show_keep"),
                add=request.POST.getlist("b_show_add"),
            )
        if request.POST.get("b_home_present"):
            # FB-30.7: «Startseite» — выбор главной пишется сразу (решение владельца)
            banners.set_home(request.tenant, banner, bool(request.POST.get("b_home")))
    except ValueError as exc:
        if str(exc) == "full" and banner is not None and banner.pk:
            # гонка: главную заполнили между проверкой и записью — баннер уже сохранён
            messages.warning(
                request,
                _("Banner gespeichert, aber die Startseite ist voll – erst einen dort abwählen."),
            )
            return redirect("site-banner-edit", pk=banner.pk)
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
