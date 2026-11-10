"""M21.7: мастер импорта, тип «Preisliste» — цены и фасовки по артикулам.

Правила — ``apps.catalog.price_list`` (те же, что у команды ``update_prices``). Новых
товаров тип не создаёт: строка либо меняет найденный товар, либо — ошибка в превью.
"""

from apps.catalog import price_list
from apps.catalog.models import Product

from .base import BaseProcessor


def _row(data: dict):
    return (
        str(data.get("sku") or ""),
        str(data.get("size") or ""),
        str(data.get("price") or ""),
        str(data.get("action") or ""),
    )


class PriceListProcessor(BaseProcessor):
    model = Product

    def validate(self, data: dict) -> list[str]:
        try:
            price_list.check_row(*_row(data))
        except price_list.PriceListError as exc:
            return [str(exc)]
        return []

    def create_or_update(self, data: dict, *, update_existing: bool, match_field: str = "sku"):
        return price_list.apply_row(*_row(data)).product
