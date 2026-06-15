"""Процессоры импорта товаров (catalog.Product) и их вариантов (ProductVariant)."""

from decimal import Decimal, InvalidOperation

from apps.catalog.models import Category, Product, ProductVariant

from .base import BaseProcessor

_TRUE = {"1", "true", "yes", "y", "ja", "wahr", "on"}
_FALSE = {"0", "false", "no", "n", "nein", "falsch", "off"}


def _parse_bool(value, default=True):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def _parse_decimal(value):
    """Вернуть Decimal или None если распарсить нельзя."""
    if value is None or value == "":
        return None
    text = str(value).strip().replace(" ", "")
    # допускаем запятую как десятичный разделитель (de-формат)
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


class ProductProcessor(BaseProcessor):
    model = Product

    def validate(self, data: dict) -> list[str]:
        errors: list[str] = []

        name_de = (data.get("name_de") or "").strip() if data.get("name_de") else ""
        if not name_de:
            errors.append("name_de is required")

        raw_price = data.get("base_price")
        if raw_price is None or str(raw_price).strip() == "":
            errors.append("base_price is required")
        else:
            price = _parse_decimal(raw_price)
            if price is None:
                errors.append("base_price is not a valid number")
            elif price < 0:
                errors.append("base_price must be >= 0")

        return errors

    def create_or_update(self, data: dict, *, update_existing: bool, match_field: str = "sku"):
        name = {}
        if data.get("name_de"):
            name["de"] = str(data["name_de"]).strip()
        if data.get("name_en"):
            name["en"] = str(data["name_en"]).strip()

        description = {}
        if data.get("description_de"):
            description["de"] = str(data["description_de"]).strip()
        if data.get("description_en"):
            description["en"] = str(data["description_en"]).strip()

        sku = (str(data["sku"]).strip() if data.get("sku") else "") or ""
        base_price = _parse_decimal(data.get("base_price")) or Decimal("0")
        currency = (str(data["currency"]).strip() if data.get("currency") else "") or "EUR"

        stock_quantity = None
        raw_stock = data.get("stock_quantity")
        if raw_stock is not None and str(raw_stock).strip() != "":
            try:
                stock_quantity = int(str(raw_stock).strip())
            except (ValueError, TypeError):
                stock_quantity = None

        is_active = _parse_bool(data.get("is_active"), default=True)

        category = None
        slug = (str(data["category_slug"]).strip() if data.get("category_slug") else "") or ""
        if slug:
            # связываем с существующей категорией; не создаём новую
            category = Category.objects.filter(slug=slug).first()

        fields = {
            "name": name,
            "description": description,
            "base_price": base_price,
            "currency": currency,
            "stock_quantity": stock_quantity,
            "is_active": is_active,
            "category": category,
        }

        if update_existing:
            # Поле синхронизации: по нему ищем существующий товар.
            existing = None
            if match_field == "name_de" and name.get("de"):
                existing = Product.objects.filter(name__de=name["de"]).first()
            elif sku:  # по умолчанию — sku
                existing = Product.objects.filter(sku=sku).first()
            if existing is not None:
                for key, value in fields.items():
                    setattr(existing, key, value)
                existing.sku = sku or existing.sku
                existing.save()
                return existing

        return Product.objects.create(sku=sku, **fields)


def _parse_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _find_parent_product(data: dict):
    """Найти родительский товар по product_sku или product_name_de (sku в приоритете)."""
    psku = (str(data["product_sku"]).strip() if data.get("product_sku") else "") or ""
    if psku:
        product = Product.objects.filter(sku=psku).first()
        if product is not None:
            return product
    pname = (str(data["product_name_de"]).strip() if data.get("product_name_de") else "") or ""
    if pname:
        return Product.objects.filter(name__de=pname).first()
    return None


class ProductVariantProcessor(BaseProcessor):
    """Массовый импорт вариантов товара (R1, A1): чай 100/250 г, размеры одежды.

    Родитель ищется по product_sku или product_name_de; вариант уникален в
    пределах товара по label (variant_product_label_uniq) — повтор label
    обновляет существующий вариант (upsert), что и нужно для массовой правки
    цен/остатков. Пустая цена варианта → берётся Product.base_price (R1).
    """

    model = ProductVariant

    def validate(self, data: dict) -> list[str]:
        errors: list[str] = []
        if not (
            (data.get("product_sku") or "").strip() or (data.get("product_name_de") or "").strip()
        ):
            errors.append("product_sku or product_name_de is required")
        elif _find_parent_product(data) is None:
            errors.append("parent product not found")
        if not (data.get("label") or "").strip():
            errors.append("label is required")
        raw_price = data.get("price")
        if raw_price not in (None, "") and _parse_decimal(raw_price) is None:
            errors.append("price is not a valid number")
        return errors

    def create_or_update(self, data: dict, *, update_existing: bool, match_field: str = "label"):
        product = _find_parent_product(data)
        if product is None:  # validate уже отсеял; страховка на гонку
            raise ValueError("parent product not found")
        label = str(data["label"]).strip()

        fields = {
            "sku": (str(data["sku"]).strip() if data.get("sku") else "") or "",
            "gtin": (str(data["gtin"]).strip() if data.get("gtin") else "") or "",
            "price": _parse_decimal(data.get("price")),  # None → наследует base_price
            "content_amount": _parse_decimal(data.get("content_amount")),
            "stock_quantity": _parse_int(data.get("stock_quantity")),
            "is_active": _parse_bool(data.get("is_active"), default=True),
        }
        # Вариант уникален по (product, label) — upsert по этой паре всегда
        # (label — естественный ключ варианта; не плодим дубли при повторном импорте).
        variant, _created = ProductVariant.objects.get_or_create(product=product, label=label)
        for key, value in fields.items():
            setattr(variant, key, value)
        variant.save()
        return variant
