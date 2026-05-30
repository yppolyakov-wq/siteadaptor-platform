"""Реестр процессоров импорта по resource_type."""

from .base import BaseProcessor
from .product import ProductProcessor

PROCESSORS = {
    "product": ProductProcessor,
}


def get_processor(resource_type: str) -> BaseProcessor:
    """Вернуть экземпляр процессора для resource_type."""
    try:
        return PROCESSORS[resource_type]()
    except KeyError as exc:
        raise ValueError(f"Unknown resource_type: {resource_type!r}") from exc
