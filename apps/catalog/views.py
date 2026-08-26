"""CRUD товаров в кабинете арендатора (HTMX).

Список с live-search и фильтрами; create/edit/delete; загрузка/удаление картинок.
Все вьюхи требуют логина владельца (логин на субдомене своей схемы).
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import vat
from apps.core.archetypes import FOOD_BUSINESS_TYPES as _FOOD_BUSINESS_TYPES
from apps.core.i18n_input import apply_i18n_overlay, extra_locales, i18n_inputs_for
from apps.inventory.services import log_catalog_change

from .forms import CategoryForm, ProductForm
from .images import delete_stored_image, save_product_image
from .models import (
    Category,
    Combo,
    ComboGroup,
    ComboOption,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductVariant,
)
from .option_styles import MODIFIER_STYLE_KEYS, MODIFIER_STYLES, VARIANT_STYLES

# W2: пищевая маркировка (аллергены/добавки/диеты/происхождение) осмысленна только у
# гастро/еды — секция формы товара показывается только этим архетипам (у прочих скрыта
# CSS-ом, поля остаются в форме → Save их не стирает). X4: источник переехал в
# apps/core/archetypes.py (его же читает навигация); имя здесь сохранено —
# на него ссылаются public_views/siteui/тесты.
FOOD_BUSINESS_TYPES = _FOOD_BUSINESS_TYPES
# M1 Boutique: типы с текстильной маркировкой (Textilkennzeichnung EU 1007/2011).
TEXTILE_BUSINESS_TYPES = frozenset({"clothing"})


def _product_form_flags(request):
    """W2: флаги вида формы товара — режим Простой/Эксперт (S5) + гейт пищевой секции.
    M1 Boutique: текстильная маркировка (material/care) — вкладка Kennzeichnung
    видна и одежде (W0-инвариант: поля всегда в DOM, скрытие CSS)."""
    tenant = getattr(request, "tenant", None)
    bt = getattr(tenant, "business_type", "") or ""
    show_food = bt in FOOD_BUSINESS_TYPES
    show_textile = bt in TEXTILE_BUSINESS_TYPES
    return {
        "show_food_labeling": show_food,
        "show_textile_labeling": show_textile,
        "show_labeling_tab": show_food or show_textile,
    }


def _i18n_ctx(form, request):
    """Ф1/Ф2: группы i18n-полей формы товара для переключателя языка. name/description —
    full-dict (i18n_groups в табе Basics); origin/ingredients — overlay (per-locale инпуты
    в табе Kennzeichnung, `origin_i18n_inputs`). Оба переключаются глобальным свитчером."""
    from apps.core.i18n_input import i18n_form_groups, i18n_inputs_for

    tenant = getattr(request, "tenant", None)
    ctx = i18n_form_groups(form, tenant, fields=("name", "description"))
    # Ф2: overlay-переводы origin/ingredients (extra-локали; база — плоское поле формы).
    ctx["origin_i18n_inputs"] = i18n_inputs_for(
        getattr(form, "instance", None), tenant, fields=("origin", "ingredients")
    )
    return ctx


def _save_product_overlays(product, request):
    """Ф2: записать overlay-переводы origin/ingredients из POST (`<field>_<loc>`)."""
    from apps.core.i18n_input import apply_i18n_overlay

    changed = apply_i18n_overlay(
        product, request.POST, getattr(request, "tenant", None), fields=("origin", "ingredients")
    )
    if changed:
        product.save(update_fields=changed)


def _parse_price(raw):
    """«4,90» / «4.90» / пусто → Decimal или None (пусто/мусор/отрицательное)."""
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return value if value >= 0 else None


def _parse_int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _handle_uploads(request, obj, *, folder="products") -> None:
    """Сохраняет загруженные файлы в obj.images (FileRef-envelope).

    FB-6: обобщено с товара на любую сущность с JSON-полем `images`
    (Product, Category); folder — подпапка storage."""
    files = request.FILES.getlist("images")
    if not files:
        return
    images = list(obj.images or [])
    has_primary = any(img.get("is_primary") for img in images)
    for f in files:
        try:
            ref = save_product_image(
                f, is_primary=not has_primary, sort_order=len(images), folder=folder
            )
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
            continue
        has_primary = True
        images.append(ref)
    obj.images = images
    obj.save(update_fields=["images", "updated_at"])


def _uploaded_variant_image(request, field="image") -> dict | None:
    """Одно фото варианта → FileRef (или None).

    Кривой файл не должен ронять сохранение варианта — цена/остаток важнее
    картинки, поэтому ошибку показываем сообщением и идём дальше."""
    uploaded = request.FILES.get(field)
    if not uploaded:
        return None
    try:
        return save_product_image(uploaded, is_primary=True, folder="variants")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return None


@login_required
def product_list(request):
    """SR-1: страница умерла — единственная поверхность ассортимента теперь
    `/dashboard/angebote/` (вид «Liste» несёт её инструменты). 302 с переносом
    GET на новые имена параметров (прецедент W10-6/X2b)."""
    from urllib.parse import urlencode

    from django.http import HttpResponseRedirect

    params = {}
    if request.GET.get("q"):
        params["q"] = request.GET["q"]
    if request.GET.get("category"):
        params["kategorie"] = request.GET["category"]
    if request.GET.get("active"):
        params["status"] = request.GET["active"]
    url = reverse("sellable-manage")
    if params:
        url += "?" + urlencode(params)
    return HttpResponseRedirect(url)


@login_required
def product_create(request):
    form = ProductForm(request.POST or None, tenant=getattr(request, "tenant", None))
    if request.method == "POST" and form.is_valid():
        product = form.save()
        _save_product_overlays(product, request)  # Ф2: переводы origin/ingredients
        # T1: стартовый остаток нового товара → в склад-леджер (реконсиляция).
        log_catalog_change(
            product=product,
            old=None,
            new=product.stock_quantity,
            actor=getattr(request.user, "username", ""),
        )
        _handle_uploads(request, product)
        return redirect("catalog:product-edit", pk=product.pk)
    return render(
        request,
        "catalog/product_form.html",
        {
            "form": form,
            "is_create": True,
            "nav": "catalog",
            **_product_form_flags(request),
            **_i18n_ctx(form, request),
        },
    )


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    old_stock = product.stock_quantity  # T1: до правки формы (для леджер-дельты)
    form = ProductForm(
        request.POST or None, instance=product, tenant=getattr(request, "tenant", None)
    )
    if request.method == "POST" and form.is_valid():
        product = form.save()
        _save_product_overlays(product, request)  # Ф2: переводы origin/ingredients
        # T1: правка остатка в каталоге пишет движение (не трогая счётчик) →
        # счётчик и леджер сходятся, реконсиляция не «расходится сама».
        log_catalog_change(
            product=product,
            old=old_stock,
            new=product.stock_quantity,
            actor=getattr(request.user, "username", ""),
        )
        _handle_uploads(request, product)
        return redirect("catalog:product-edit", pk=product.pk)
    return render(
        request,
        "catalog/product_form.html",
        {
            "form": form,
            "is_create": False,
            "product": product,
            "variants": product.variants.all(),
            "modifier_groups": product.modifier_groups.prefetch_related("options"),
            # O-2: реестры видов отображения (витрина и кабинет читают один список).
            "variant_styles": VARIANT_STYLES,
            "modifier_styles": MODIFIER_STYLES,
            "nav": "catalog",
            **_product_form_flags(request),
            **_i18n_ctx(form, request),
        },
    )


# ---------------------------------------------------------------------------
# Варианты товара (R1): чай 100/250 г, размеры — CRUD на странице товара
# ---------------------------------------------------------------------------


@login_required
@require_POST
def variant_add(request, pk):
    product = get_object_or_404(Product, pk=pk)
    label = (request.POST.get("label") or "").strip()
    # M4-A: варианты можно заводить осями (размер/цвет) — label тогда собирается
    # из них («S · Blau»). Прежний путь «только label» работает как раньше.
    size = (request.POST.get("size") or "").strip()
    color = (request.POST.get("color") or "").strip()
    if not label:
        label = " · ".join(part for part in (size, color) if part)
    if not label:
        messages.error(request, _("Variant label is required."))
    elif ProductVariant.objects.filter(product=product, label=label).exists():
        messages.error(request, _("A variant with this label already exists."))
    else:
        variant = ProductVariant.objects.create(
            product=product,
            label=label,
            size=size,
            color=color,
            sku=(request.POST.get("sku") or "").strip(),
            gtin=(request.POST.get("gtin") or "").strip(),
            price=_parse_price(request.POST.get("price")),
            content_amount=_parse_price(request.POST.get("content")),
            stock_quantity=_parse_int(request.POST.get("stock")),
            cost_price=_parse_price(request.POST.get("cost")),  # T5
            reorder_point=_parse_int(request.POST.get("reorder_point")),  # T5
            reorder_target=_parse_int(request.POST.get("reorder_target")),  # T5
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        new_image = _uploaded_variant_image(request)
        if new_image:
            variant.images = [new_image]
            variant.save(update_fields=["images", "updated_at"])
        # T1: стартовый остаток варианта → в склад-леджер.
        log_catalog_change(
            product=product,
            variant=variant,
            old=None,
            new=variant.stock_quantity,
            actor=getattr(request.user, "username", ""),
        )
        messages.success(request, _("Variant added."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def variant_update(request, pk, vid):
    variant = get_object_or_404(ProductVariant, pk=vid, product_id=pk)
    old_stock = variant.stock_quantity  # T1: до правки (для леджер-дельты)
    variant.price = _parse_price(request.POST.get("price"))
    variant.content_amount = _parse_price(request.POST.get("content"))
    variant.stock_quantity = _parse_int(request.POST.get("stock"))
    variant.cost_price = _parse_price(request.POST.get("cost"))  # T5
    variant.reorder_point = _parse_int(request.POST.get("reorder_point"))  # T5
    variant.reorder_target = _parse_int(request.POST.get("reorder_target"))  # T5
    variant.sort_order = _parse_int(request.POST.get("sort")) or 0
    # Фидбэк 2026-08-04: артикул варианта редактируется из кабинета (раньше —
    # только CSV-импортом; поле в модели было с M4-A).
    variant.sku = (request.POST.get("sku") or "").strip()
    variant.gtin = (request.POST.get("gtin") or "").strip()
    variant.is_active = bool(request.POST.get("is_active"))
    fields = []
    # M4-A: оси пишем ТОЛЬКО если форма их прислала (presence-guard, инвариант W0)
    # — иначе частичная форма стёрла бы размер/цвет.
    if request.POST.get("axes_present"):
        variant.size = (request.POST.get("size") or "").strip()
        variant.color = (request.POST.get("color") or "").strip()
        fields += ["size", "color"]
    # M4-A довод (2026-08-01): фото варианта. Поле завели в M4-A и витрина
    # подменяет им главное фото, но загрузить его было НЕЧЕМ — заполнял только
    # демо-кит. Одно фото на вариант: галерея товара остаётся у товара.
    new_image = _uploaded_variant_image(request)
    if new_image or request.POST.get("remove_image"):
        variant.images = [new_image] if new_image else []
        fields.append("images")
    # I18N-10: переводы МЕТОК (label/size/color) для витрины. Плоские поля выше
    # остаются ключами учёта; apply_i18n_overlay сам presence-guard'ит (поля нет
    # в POST → перевод не трогаем).
    fields += apply_i18n_overlay(
        variant, request.POST, getattr(request, "tenant", None), fields=("label", "size", "color")
    )
    variant.save(
        update_fields=fields
        + [
            "price",
            "content_amount",
            "stock_quantity",
            "cost_price",
            "reorder_point",
            "reorder_target",
            "sort_order",
            "sku",
            "gtin",
            "is_active",
            "updated_at",
        ]
    )
    # T1: правка остатка варианта в каталоге пишет движение (реконсиляция).
    log_catalog_change(
        product=variant.product,
        variant=variant,
        old=old_stock,
        new=variant.stock_quantity,
        actor=getattr(request.user, "username", ""),
    )
    messages.success(request, _("Variant updated."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def variant_delete(request, pk, vid):
    get_object_or_404(ProductVariant, pk=vid, product_id=pk).delete()
    messages.success(request, _("Variant removed."))
    return redirect("catalog:product-edit", pk=pk)


# ---------------------------------------------------------------------------
# Модификаторы / Extras блюда (A4 Gastro): группы + опции — CRUD на товаре
# ---------------------------------------------------------------------------


@login_required
@require_POST
def modifier_group_add(request, pk):
    product = get_object_or_404(Product, pk=pk)
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, _("Group name is required."))
    else:
        ModifierGroup.objects.create(
            product=product,
            name=name,
            min_select=_parse_int(request.POST.get("min")) or 0,
            max_select=_parse_int(request.POST.get("max")) or 0,
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Modifier group added."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_group_update(request, pk, gid):
    group = get_object_or_404(ModifierGroup, pk=gid, product_id=pk)
    group.name = (request.POST.get("name") or group.name).strip()
    group.min_select = _parse_int(request.POST.get("min")) or 0
    group.max_select = _parse_int(request.POST.get("max")) or 0
    group.sort_order = _parse_int(request.POST.get("sort")) or 0
    group.is_active = bool(request.POST.get("is_active"))
    fields = ["name", "min_select", "max_select", "sort_order", "is_active", "updated_at"]
    # O-2: вид выбора — под сентинелом (частичная форма не должна его сбрасывать).
    if request.POST.get("style_present"):
        style = (request.POST.get("display_style") or "").strip()
        group.display_style = style if style in MODIFIER_STYLE_KEYS else ""
        fields.append("display_style")
    # I18N-10: перевод названия группы («Teig» → «Тесто») для витрины.
    fields += apply_i18n_overlay(
        group, request.POST, getattr(request, "tenant", None), fields=("name",)
    )
    group.save(update_fields=fields)
    messages.success(request, _("Modifier group updated."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_group_delete(request, pk, gid):
    get_object_or_404(ModifierGroup, pk=gid, product_id=pk).delete()
    messages.success(request, _("Modifier group removed."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_option_add(request, pk, gid):
    group = get_object_or_404(ModifierGroup, pk=gid, product_id=pk)
    label = (request.POST.get("label") or "").strip()
    if not label:
        messages.error(request, _("Option label is required."))
    else:
        ModifierOption.objects.create(
            group=group,
            label=label,
            sku=(request.POST.get("sku") or "").strip(),  # фидбэк 2026-08-04
            price_delta=_parse_price(request.POST.get("delta")) or Decimal("0"),
            sort_order=_parse_int(request.POST.get("sort")) or 0,
            # O-2: фото опции (для видов «плитки»/«список с фото»).
            image=_uploaded_variant_image(request) or {},
        )
        messages.success(request, _("Option added."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_option_update(request, pk, gid, oid):
    option = get_object_or_404(ModifierOption, pk=oid, group_id=gid, group__product_id=pk)
    option.label = (request.POST.get("label") or option.label).strip()
    option.sku = (request.POST.get("sku") or "").strip()  # фидбэк 2026-08-04
    option.price_delta = _parse_price(request.POST.get("delta")) or Decimal("0")
    option.sort_order = _parse_int(request.POST.get("sort")) or 0
    option.is_active = bool(request.POST.get("is_active"))
    opt_fields = ["label", "sku", "price_delta", "sort_order", "is_active", "updated_at"]
    new_image = _uploaded_variant_image(request)
    if new_image or request.POST.get("remove_image"):
        option.image = new_image or {}
        opt_fields.append("image")
    # I18N-10: перевод метки опции; в заказ по-прежнему уходит плоский снимок.
    opt_fields += apply_i18n_overlay(
        option, request.POST, getattr(request, "tenant", None), fields=("label",)
    )
    option.save(update_fields=opt_fields)
    messages.success(request, _("Option updated."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_option_delete(request, pk, gid, oid):
    get_object_or_404(ModifierOption, pk=oid, group_id=gid, group__product_id=pk).delete()
    messages.success(request, _("Option removed."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()  # soft-delete
        return redirect("sellable-manage")
    return render(
        request,
        "catalog/product_confirm_delete.html",
        {"product": product, "nav": "catalog"},
    )


@login_required
def product_image_delete(request, pk, image_id):
    """Удаляет одну картинку товара (из списка и из storage)."""
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        images = list(product.images or [])
        kept, removed_primary = [], False
        for img in images:
            if img.get("id") == image_id:
                delete_stored_image(img)
                removed_primary = img.get("is_primary", False)
            else:
                kept.append(img)
        # если удалили главную — назначаем главной первую оставшуюся
        if removed_primary and kept:
            kept[0]["is_primary"] = True
        product.images = kept
        product.save(update_fields=["images", "updated_at"])
    return redirect("catalog:product-edit", pk=pk)


@login_required
def product_image_primary(request, pk, image_id):
    """Делает выбранную картинку главной."""
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        images = list(product.images or [])
        for img in images:
            img["is_primary"] = img.get("id") == image_id
        product.images = images
        product.save(update_fields=["images", "updated_at"])
    return redirect("catalog:product-edit", pk=pk)


# ---------------------------------------------------------------------------
# Категории (CRUD + иерархия)
# ---------------------------------------------------------------------------


def _category_tree() -> list:
    """Плоский список живых категорий в порядке дерева.

    Каждой записи проставляем .level (глубина) и .product_count. Категории,
    чей родитель удалён/отсутствует, показываем как корневые (не теряем их).
    """
    cats = list(Category.objects.all())
    alive_ids = {c.pk for c in cats}
    children_map: dict = {}
    for c in cats:
        key = c.parent_id if c.parent_id in alive_ids else None
        children_map.setdefault(key, []).append(c)

    counts = dict(
        Product.objects.values("category_id")
        .annotate(n=Count("id"))
        .values_list("category_id", "n")
    )

    rows: list = []

    def walk(parent_key, level):
        for c in sorted(children_map.get(parent_key, []), key=lambda x: (x.sort_order, x.slug)):
            c.level = level
            c.product_count = counts.get(c.pk, 0)
            rows.append(c)
            walk(c.pk, level + 1)

    walk(None, 0)
    return rows


def _descendants(category) -> list:
    """Все живые потомки категории (без неё самой)."""
    result: list = []
    stack = list(Category.objects.filter(parent=category))
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(Category.objects.filter(parent=node))
    return result


@login_required
def category_list(request):
    """SR-4 (канвас Kategorien): плитки с фото — фото и имя кликабельны →
    форма категории; подкатегории — чипами в плитке родителя."""
    tree = _category_tree()
    roots, cur = [], None
    for c in tree:
        if c.level == 0:
            cur = {"cat": c, "children": []}
            roots.append(cur)
        elif cur is not None:
            cur["children"].append(c)
    return render(
        request,
        "catalog/category_list.html",
        {"nav": "categories", "categories": tree, "roots": roots},
    )


@login_required
def category_create(request):
    form = CategoryForm(request.POST or None, tenant=getattr(request, "tenant", None))
    if request.method == "POST" and form.is_valid():
        category = form.save()
        _handle_uploads(request, category, folder="categories")  # FB-6: фото категории
        return redirect("catalog:category-list")
    return render(
        request,
        "catalog/category_form.html",
        {"form": form, "is_create": True, "nav": "categories", **_i18n_ctx(form, request)},
    )


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(
        request.POST or None, instance=category, tenant=getattr(request, "tenant", None)
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        _handle_uploads(request, category, folder="categories")  # FB-6: фото категории
        return redirect("catalog:category-list")
    return render(
        request,
        "catalog/category_form.html",
        {
            "form": form,
            "is_create": False,
            "category": category,
            "nav": "categories",
            **_i18n_ctx(form, request),
        },
    )


@login_required
@require_POST
def category_inline_edit(request):
    """SE-2c-3: инлайн-правка имени категории прямо на канве витрины (?preview=1).

    JSON {category_pk, value} → пишет Category.name['de'] живой категории (AliveManager
    исключает удалённые). Только владелец (login_required на субдомене схемы). 204/400.
    """
    import json

    from django.http import HttpResponse, HttpResponseBadRequest

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    pk = data.get("category_pk")
    value = data.get("value", "")
    value = value.strip() if isinstance(value, str) else ""
    if not pk or not value:
        return HttpResponseBadRequest()
    try:
        category = Category.objects.get(pk=pk)
    except (Category.DoesNotExist, ValidationError, ValueError):
        return HttpResponseBadRequest()
    name = dict(category.name or {})
    name["de"] = value
    category.name = name
    category.save(update_fields=["name", "updated_at"])
    return HttpResponse(status=204)


@login_required
@require_POST
def product_inline_edit(request):
    """Инлайн-правка товара на канве — тонкий алиас единого диспетчера (UC2-4).

    Контракт/URL прежние: JSON {pk, field, value}; вайтлист/семантика полей —
    декларация INLINE_REGISTRY["product"] (apps/core/inline_edit.py):
    name/description → i18n['de'] (имя пустым не сохраняем), base_price —
    Decimal, только без вариантов; bump кэша — только на цене (как раньше)."""
    from apps.core.inline_edit import dispatch

    return dispatch(request, "product")


@login_required
@require_POST
def product_photo_edit(request):
    """M4 / пер-слайд: править галерею товара прямо на канве витрины (multipart).

    POST: pk, op ∈ {replace, add, remove}, image_id (для replace/remove), image
    (файл для replace/add). replace заменяет КОНКРЕТНЫЙ слайд по id в месте (одиночное
    фото → честная замена без дубля); add — добавляет; remove — удаляет. Реюз
    catalog.images.apply_gallery_op (валидация Pillow + storage + корректный primary).
    Сброс кэша витрины. Только владелец (login_required). 204/400.
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.catalog.images import apply_gallery_op

    pk = request.POST.get("pk")
    op = request.POST.get("op", "replace")
    image_id = request.POST.get("image_id", "")
    uploaded = request.FILES.get("image")
    if not pk:
        return HttpResponseBadRequest()
    try:
        # Блокируем строку на время read-modify-write JSON-поля images — иначе две
        # параллельные правки (add+remove) затрут изменения друг друга (lost update).
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=pk)
            product.images = apply_gallery_op(
                product.images, op=op, image_id=image_id, uploaded=uploaded, folder="products"
            )
            product.save(update_fields=["images", "updated_at"])
    except (Product.DoesNotExist, ValueError):
        return HttpResponseBadRequest()
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)
    return HttpResponse(status=204)


@login_required
def category_image_delete(request, pk, image_id):
    """FB-6: удаляет одну картинку категории (из списка и из storage)."""
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        images = list(category.images or [])
        kept, removed_primary = [], False
        for img in images:
            if img.get("id") == image_id:
                delete_stored_image(img)
                removed_primary = img.get("is_primary", False)
            else:
                kept.append(img)
        if removed_primary and kept:
            kept[0]["is_primary"] = True
        category.images = kept
        category.save(update_fields=["images", "updated_at"])
    return redirect("catalog:category-edit", pk=pk)


@login_required
def category_image_primary(request, pk, image_id):
    """FB-6: делает выбранную картинку категории главной (плитка витрины)."""
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        images = list(category.images or [])
        for img in images:
            img["is_primary"] = img.get("id") == image_id
        category.images = images
        category.save(update_fields=["images", "updated_at"])
    return redirect("catalog:category-edit", pk=pk)


@login_required
def category_delete(request, pk):
    """Удаление категории (soft).

    Если есть подкатегории или товары — даём выбрать стратегию:
    reparent (перевесить детей на родителя, товары отвязать), cascade
    (удалить ветку целиком, товары отвязать) или cancel.
    """
    category = get_object_or_404(Category, pk=pk)
    children = list(Category.objects.filter(parent=category))
    product_count = Product.objects.filter(category=category).count()
    descendants = _descendants(category)
    branch = [category, *descendants]
    descendant_product_count = Product.objects.filter(category__in=branch).count()
    has_dependencies = bool(children) or product_count > 0

    if request.method == "POST":
        strategy = request.POST.get("strategy", "")

        if not has_dependencies:
            category.delete()
            messages.success(request, _("Category deleted."))
            return redirect("catalog:category-list")

        if strategy == "reparent":
            Category.objects.filter(parent=category).update(parent=category.parent)
            Product.objects.filter(category=category).update(category=None)
            category.delete()
            messages.success(
                request, _("Category deleted; subcategories moved up and products detached.")
            )
            return redirect("catalog:category-list")

        if strategy == "cascade":
            Product.objects.filter(category__in=branch).update(category=None)
            Category.objects.filter(pk__in=[c.pk for c in branch]).delete()  # bulk soft-delete
            messages.success(request, _("Category and its subcategories deleted."))
            return redirect("catalog:category-list")

        # cancel / неизвестная стратегия — ничего не делаем
        return redirect("catalog:category-list")

    return render(
        request,
        "catalog/category_confirm_delete.html",
        {
            "category": category,
            "children": children,
            "product_count": product_count,
            "descendant_count": len(descendants),
            "descendant_product_count": descendant_product_count,
            "has_dependencies": has_dependencies,
            "nav": "categories",
        },
    )


# --- Combo-наборы (A4 Gastro): кабинет CRUD ----------------------------------------


@login_required
def combo_list(request):
    combos = Combo.objects.prefetch_related("groups__options").order_by("sort_order", "created_at")
    return render(request, "catalog/combo_list.html", {"combos": combos, "nav": "combos"})


def _apply_combo_extras(combo, request) -> list[str]:
    """MEN-2: поля «набора меню» из POST (create+edit). Возвращает имена полей.

    Форма выводит все поля всегда (W0-инвариант) — presence-сентинелы не нужны.
    """
    raw_cat = (request.POST.get("category") or "").strip()
    category = None
    if raw_cat:
        try:
            category = Category.objects.filter(pk=raw_cat).first()
        except (ValueError, ValidationError):
            category = None
    combo.category = category
    combo.price_per_person = bool(request.POST.get("price_per_person"))
    # PositiveSmallIntegerField: кламп, чтобы кривой ввод не ронял save (DataError).
    combo.min_persons = min(_parse_int(request.POST.get("min_persons")) or 0, 5000)
    types: list[str] = []
    for part in (request.POST.get("event_types") or "").replace("\n", ",").split(","):
        p = part.strip()[:40]
        if p and p not in types:
            types.append(p)
    combo.event_types = types[:12]  # кап как у anfrage.event_types (AF-1)
    combo.free_pool = bool(request.POST.get("free_pool"))
    return ["category", "price_per_person", "min_persons", "event_types", "free_pool"]


def _combo_form_ctx(request):
    """MEN-2: категории для привязки + подсказки поводов из словаря AF-1."""
    site = getattr(getattr(request, "tenant", None), "site_config", None) or {}
    anfrage = site.get("anfrage") if isinstance(site.get("anfrage"), dict) else {}
    raw_types = anfrage.get("event_types")
    suggestions = (
        [s for s in raw_types if isinstance(s, str)] if isinstance(raw_types, list) else []
    )
    return {
        "categories": Category.objects.order_by("sort_order", "slug"),
        "event_type_suggestions": suggestions,
    }


@login_required
def combo_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        price = _parse_price(request.POST.get("price"))
        if not name or price is None:
            messages.error(request, _("Name and price are required."))
        else:
            combo = Combo(
                name=name,
                description=(request.POST.get("description") or "").strip(),
                price=price,
                sort_order=_parse_int(request.POST.get("sort")) or 0,
                is_active=bool(request.POST.get("is_active")),
                # VAT-2: ставка набора (по ней считается позиция заказа).
                vat_rate=vat.parse_rate(request.POST.get("vat_rate"), Decimal("19.00")),
            )
            apply_i18n_overlay(combo, request.POST, getattr(request, "tenant", None))  # L3d
            _apply_combo_extras(combo, request)  # MEN-2
            combo.save()
            _handle_uploads(request, combo, folder="combos")  # MEN-2: галерея набора
            return redirect("catalog:combo-edit", pk=combo.pk)
    return render(
        request,
        "catalog/combo_form.html",
        {
            "combo": None,
            "nav": "combos",
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
            **_combo_form_ctx(request),
        },
    )


@login_required
def combo_edit(request, pk):
    combo = get_object_or_404(Combo.objects.prefetch_related("groups__options"), pk=pk)
    if request.method == "POST":
        combo.name = (request.POST.get("name") or combo.name).strip()
        price = _parse_price(request.POST.get("price"))
        if price is not None:
            combo.price = price
        combo.description = (request.POST.get("description") or "").strip()
        combo.sort_order = _parse_int(request.POST.get("sort")) or 0
        combo.is_active = bool(request.POST.get("is_active"))
        # VAT-2: чужое значение оставляет прежнюю ставку (защита от подмены).
        combo.vat_rate = vat.parse_rate(request.POST.get("vat_rate"), combo.vat_rate)
        _uf = ["name", "price", "description", "sort_order", "is_active", "vat_rate", "updated_at"]
        _uf += _apply_combo_extras(combo, request)  # MEN-2
        _uf += apply_i18n_overlay(combo, request.POST, getattr(request, "tenant", None))  # L3d
        combo.save(update_fields=_uf)
        _handle_uploads(request, combo, folder="combos")  # MEN-2: галерея набора
        messages.success(request, _("Saved."))
        return redirect("catalog:combo-edit", pk=pk)
    products = Product.objects.filter(is_active=True).order_by("name")
    combo.i18n_inputs = i18n_inputs_for(combo, getattr(request, "tenant", None))  # L3d
    return render(
        request,
        "catalog/combo_form.html",
        {
            "combo": combo,
            "products": products,
            "nav": "combos",
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
            **_combo_form_ctx(request),
        },
    )


@login_required
def combo_image_delete(request, pk, image_id):
    """MEN-2: удаляет одно фото набора (из списка и из storage) — как у категории."""
    combo = get_object_or_404(Combo, pk=pk)
    if request.method == "POST":
        kept, removed_primary = [], False
        for img in list(combo.images or []):
            if img.get("id") == image_id:
                delete_stored_image(img)
                removed_primary = img.get("is_primary", False)
            else:
                kept.append(img)
        if removed_primary and kept:
            kept[0]["is_primary"] = True
        combo.images = kept
        combo.save(update_fields=["images", "updated_at"])
    return redirect("catalog:combo-edit", pk=pk)


@login_required
def combo_image_primary(request, pk, image_id):
    """MEN-2: делает фото набора главным (карточка/агрегатор)."""
    combo = get_object_or_404(Combo, pk=pk)
    if request.method == "POST":
        images = list(combo.images or [])
        for img in images:
            img["is_primary"] = img.get("id") == image_id
        combo.images = images
        combo.save(update_fields=["images", "updated_at"])
    return redirect("catalog:combo-edit", pk=pk)


@login_required
def combo_delete(request, pk):
    combo = get_object_or_404(Combo, pk=pk)
    if request.method == "POST":
        combo.delete()  # soft-delete
        return redirect("catalog:combo-list")
    return render(request, "catalog/combo_confirm_delete.html", {"combo": combo, "nav": "combos"})


@login_required
@require_POST
def combo_group_add(request, pk):
    combo = get_object_or_404(Combo, pk=pk)
    label = (request.POST.get("label") or "").strip()
    if not label:
        messages.error(request, _("Group name is required."))
    else:
        ComboGroup.objects.create(
            combo=combo,
            label=label,
            included=bool(request.POST.get("included")),  # MEN-2
            min_select=_parse_int(request.POST.get("min")) or 0,
            max_select=_parse_int(request.POST.get("max")) or 0,
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Group added."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_group_update(request, pk, gid):
    group = get_object_or_404(ComboGroup, pk=gid, combo_id=pk)
    group.label = (request.POST.get("label") or group.label).strip()
    group.included = bool(request.POST.get("included"))  # MEN-2
    group.min_select = _parse_int(request.POST.get("min")) or 0
    group.max_select = _parse_int(request.POST.get("max")) or 0
    group.sort_order = _parse_int(request.POST.get("sort")) or 0
    group.is_active = bool(request.POST.get("is_active"))
    group.save(
        update_fields=[
            "label",
            "included",
            "min_select",
            "max_select",
            "sort_order",
            "is_active",
            "updated_at",
        ]
    )
    messages.success(request, _("Group updated."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_group_delete(request, pk, gid):
    get_object_or_404(ComboGroup, pk=gid, combo_id=pk).delete()
    messages.success(request, _("Group removed."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_option_add(request, pk, gid):
    group = get_object_or_404(ComboGroup, pk=gid, combo_id=pk)
    product = Product.objects.filter(pk=request.POST.get("product"), is_active=True).first()
    if product is None:
        messages.error(request, _("Please choose a product."))
    else:
        ComboOption.objects.create(
            group=group,
            product=product,
            price_delta=_parse_price(request.POST.get("delta")) or Decimal("0"),
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Option added."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_option_update(request, pk, gid, oid):
    option = get_object_or_404(ComboOption, pk=oid, group_id=gid, group__combo_id=pk)
    option.price_delta = _parse_price(request.POST.get("delta")) or Decimal("0")
    option.sort_order = _parse_int(request.POST.get("sort")) or 0
    option.is_active = bool(request.POST.get("is_active"))
    option.save(update_fields=["price_delta", "sort_order", "is_active", "updated_at"])
    messages.success(request, _("Option updated."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_option_delete(request, pk, gid, oid):
    get_object_or_404(ComboOption, pk=oid, group_id=gid, group__combo_id=pk).delete()
    messages.success(request, _("Option removed."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
def products_merge(request):
    """Фидбэк 2026-08-04 «Zusammenführen»: объединить отдельные товары в ОДНУ
    карточку с вариантами. Шаг 1 (POST ids из списка товаров) — подтверждение
    с выбором главного; шаг 2 (POST ids+main) — merge.merge_products и редирект
    в форму главного товара (варианты уже на вкладке)."""
    if request.method != "POST":
        return redirect("sellable-manage")
    products = list(Product.objects.filter(pk__in=request.POST.getlist("ids")))
    if len(products) < 2:
        messages.error(request, _("Select at least two products to merge."))
        return redirect("sellable-manage")
    main_id = request.POST.get("main", "")
    if not main_id:
        return render(request, "catalog/merge_confirm.html", {"products": products})
    main = next((p for p in products if str(p.pk) == main_id), None)
    if main is None:
        messages.error(request, _("Select at least two products to merge."))
        return redirect("sellable-manage")
    from .merge import merge_products

    merged, refused = merge_products(
        main,
        [p for p in products if p.pk != main.pk],
        actor=getattr(request.user, "username", ""),
    )
    if merged:
        messages.success(request, _("%(n)s products merged as variants.") % {"n": merged})
    for name in refused:
        messages.error(
            request,
            _("“%(name)s” already has variants or extras — skipped.") % {"name": name},
        )
    return redirect("catalog:product-edit", pk=main.pk)


@login_required
def combo_feature(request, pk):
    """MEN-5: продвижение набора меню в агрегаторе (generic self-serve featured —
    зеркало unit_feature/event_feature, apps.aggregator.featuring)."""
    from apps.aggregator import featuring
    from apps.aggregator.models import AggregatorListing

    combo = get_object_or_404(Combo, pk=pk)
    return featuring.render_feature_page(
        request,
        obj_title=combo.name,
        kind=AggregatorListing.KIND_MENU,
        source_ref=str(combo.pk),
        listable=combo.is_active,
        not_listed_hint=(
            "Nur aktive Menü-Sets erscheinen im Verzeichnis und können beworben "
            "werden. Aktivieren Sie das Set zuerst."
        ),
        back_url=reverse("catalog:combo-list"),
        checkout_url=reverse("catalog:combo-feature-checkout", args=[combo.pk]),
        nav="combos",
    )


@login_required
@require_POST
def combo_feature_checkout(request, pk):
    """MEN-5: разовый Stripe-Checkout за продвижение набора → редирект на оплату."""
    from apps.aggregator import featuring
    from apps.aggregator.models import AggregatorListing
    from apps.aggregator.tasks import sync_menu_listing

    combo = get_object_or_404(Combo, pk=pk)
    return featuring.start_feature_checkout(
        request,
        kind=AggregatorListing.KIND_MENU,
        source_ref=str(combo.pk),
        title=combo.name,
        listable=combo.is_active,
        not_listable_msg="Nur aktive Menü-Sets können beworben werden.",
        sync=sync_menu_listing,
        feature_page_url=reverse("catalog:combo-feature", args=[combo.pk]),
    )
