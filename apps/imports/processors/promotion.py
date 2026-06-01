"""Процессор импорта акций (promotions.Promotion)."""

from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.catalog.models import Product
from apps.promotions.models import Promotion

from .base import BaseProcessor
from .product import _parse_bool, _parse_decimal


def _parse_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _parse_dt(value):
    """ISO либо 'YYYY-MM-DD[ HH:MM]'. Возвращает aware-datetime или None."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    dt = parse_datetime(text)
    if dt is None:
        d = parse_date(text)
        if d is not None:
            dt = datetime(d.year, d.month, d.day)
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


class PromotionProcessor(BaseProcessor):
    model = Promotion

    def validate(self, data: dict) -> list[str]:
        errors: list[str] = []

        title_de = (data.get("title_de") or "").strip() if data.get("title_de") else ""
        if not title_de:
            errors.append("title_de is required")

        if (
            data.get("discount_percent") not in (None, "")
            and _parse_int(data.get("discount_percent")) is None
        ):
            errors.append("discount_percent is not a valid number")
        for key in ("price_override", "compare_at_price"):
            if data.get(key) not in (None, "") and _parse_decimal(data.get(key)) is None:
                errors.append(f"{key} is not a valid number")
        return errors

    def create_or_update(self, data: dict, *, update_existing: bool, match_field: str = "title_de"):
        title = {}
        if data.get("title_de"):
            title["de"] = str(data["title_de"]).strip()
        if data.get("title_en"):
            title["en"] = str(data["title_en"]).strip()

        description = {}
        if data.get("description_de"):
            description["de"] = str(data["description_de"]).strip()
        if data.get("description_en"):
            description["en"] = str(data["description_en"]).strip()

        product = None
        psku = (str(data["product_sku"]).strip() if data.get("product_sku") else "") or ""
        if psku:
            product = Product.objects.filter(sku=psku).first()

        promo_type = (
            str(data["promo_type"]).strip().lower() if data.get("promo_type") else ""
        ) or "reservation"
        if promo_type not in ("reservation", "discount"):
            promo_type = "reservation"

        fields = {
            "title": title,
            "description": description,
            "product": product,
            "promo_type": promo_type,
            "discount_percent": _parse_int(data.get("discount_percent")),
            "price_override": _parse_decimal(data.get("price_override")),
            "compare_at_price": _parse_decimal(data.get("compare_at_price")),
            "available_quantity": _parse_int(data.get("available_quantity")),
            "max_per_customer": _parse_int(data.get("max_per_customer")) or 1,
            "reservation_ttl_hours": _parse_int(data.get("reservation_ttl_hours")) or 24,
            "auto_confirm": _parse_bool(data.get("auto_confirm"), default=False),
            "starts_at": _parse_dt(data.get("starts_at")),
            "ends_at": _parse_dt(data.get("ends_at")),
        }

        if update_existing and match_field == "title_de" and title.get("de"):
            existing = Promotion.objects.filter(title__de=title["de"]).first()
            if existing is not None:
                for key, value in fields.items():
                    setattr(existing, key, value)
                existing.save()
                return existing

        # новые акции — в статусе draft, владелец активирует вручную
        return Promotion.objects.create(status="draft", **fields)
