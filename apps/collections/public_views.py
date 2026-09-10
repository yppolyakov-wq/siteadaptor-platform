"""M4-B Lookbook: публичная страница образа `/lookbook/<slug>/`.

Подборка товаров с фото («Herbst-Looks») получает свою страницу: галерея образа
+ грид товаров, из которых он собран. Без фото подборка остаётся обычным
фасет-чипом каталога — страницы у неё нет (404), чтобы в выдачу/меню не попадали
пустые «луки».
"""

from django.http import Http404
from django.shortcuts import render
from django.utils.translation import get_language

from apps.catalog.models import Product
from apps.tenants import siteconfig

from .models import Collection


def _cover_composition(tenant, surface: str) -> dict:
    """STU-18d: композиция листинга без под-сущностей — только «С обложкой».

    Под-сущностей (подборок, тем, направлений) у страницы нет, поэтому из реестра
    доступна одна композиция; без фото сайта она честно проваливается в обычную
    сетку (гейт `NEEDS_PHOTO`).
    """
    from apps.core import listing_composition

    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    return listing_composition.context(
        cfg,
        surface,
        hero=lambda: listing_composition.hero_from_tenant(tenant, cfg),
    )


def lookbook(request, slug):
    collection = Collection.objects.filter(slug=slug, is_active=True).first()
    if collection is None or not collection.images:
        raise Http404
    products = list(
        Product.objects.filter(is_active=True, collections=collection).order_by("name")[:60]
    )
    locale = get_language()
    return render(
        request,
        "storefront/lookbook.html",
        {
            "collection": collection,
            "collection_name": collection.name_localized(locale),
            "collection_description": collection.description_localized(locale),
            "products": products,
            # LAY-3a-2: раскладка сетки товаров образа (пусто → прежние классы).
            **siteconfig.page_layout_ctx(
                siteconfig.normalize(request.tenant.site_config), "lookbook_layout", "lookbook"
            ),
            **_cover_composition(request.tenant, "lookbook"),
        },
    )
