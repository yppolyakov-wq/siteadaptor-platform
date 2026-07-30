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

from .models import Collection


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
        },
    )
