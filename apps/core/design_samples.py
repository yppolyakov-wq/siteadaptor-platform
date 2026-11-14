"""FB-29.8b: товары-примеры для предпросмотра дизайна на пустом магазине.

Владелец выбирает дизайн раньше, чем заводит товары — без карточек предпросмотр пуст
и дизайн не оценить. В предпросмотре дизайна (`?preview=1` вместе с `look` или
`bundle`) пустой список товаров показывает примеры: объекты `Product` в памяти, в базу
ничего не пишется, на живом сайте их нет.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

#: (название, цена, ключ демо-фото)
_SAMPLES = (
    ("Beispielprodukt 1", "9.90", "tea"),
    ("Beispielprodukt 2", "14.50", "coffee"),
    ("Beispielprodukt 3", "24.00", "chocolate"),
    ("Beispielprodukt 4", "6.80", "bakery"),
)


def wanted(request) -> bool:
    """Идёт ли предпросмотр ДИЗАЙНА (а не обычное превью страницы)."""
    get = getattr(request, "GET", None) or {}
    return get.get("preview") == "1" and bool(get.get("look") or get.get("bundle"))


def products() -> list:
    """Четыре товара-примера: несохранённые `Product`, ссылки никуда не ведут."""
    from apps.catalog.models import Product
    from apps.tenants.demo_images import demo_image_url

    out = []
    for i, (name, price, keyword) in enumerate(_SAMPLES):
        item = Product(
            pk=uuid.UUID(int=i + 1),
            name={"de": name, "en": name},
            base_price=Decimal(price),
            images=[
                {
                    "id": f"sample-{i}",
                    "url": demo_image_url(keyword, w=800, h=800, lock=700 + i),
                    "alt": name,
                    "is_primary": True,
                }
            ],
        )
        item.is_sample = True
        item.get_absolute_url = lambda: "#"
        out.append(item)
    return out


def for_empty_shop(request) -> list:
    """Примеры — только в предпросмотре дизайна и только пока своих товаров нет."""
    if not wanted(request):
        return []
    from apps.catalog.models import Product

    if Product.objects.filter(is_active=True).exists():
        return []
    return products()
