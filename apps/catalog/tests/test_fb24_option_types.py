"""FB-24a: типы опций магазина — модели, реестр стандартных типов, оси варианта."""

import pytest

from apps.catalog import option_types
from apps.catalog.models import OptionType, OptionValue, ProductVariant, VariantOption
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


def test_standard_set_matches_owner_decision():
    assert list(option_types.STANDARD) == [
        "size", "color", "material", "volume", "weight", "flavor", "length", "pack",
    ]  # fmt: skip
    # размер и цвет живут в полях варианта — их не дублируем в таблицу связей
    assert option_types.FIELD_BACKED == ("size", "color")


def test_clean_axes_keeps_known_unique_and_caps():
    allowed = {"size", "color", "material", "stoff"}
    raw = ["material", "evil", "material", "size", "color", "stoff"]
    assert option_types.clean_axes(raw, allowed) == ["material", "size", "color"]
    assert option_types.clean_axes(None, allowed) == []


def test_variant_axes_reads_fields_and_links():
    product = ProductFactory()
    variant = ProductVariant.objects.create(product=product, size="M", color="Blau")
    stoff = OptionType.objects.create(code="material", standard="material")
    cotton = OptionValue.objects.create(option_type=stoff, value="Baumwolle")
    VariantOption.objects.create(variant=variant, option_type=stoff, value=cotton)
    variant = ProductVariant.objects.prefetch_related(
        "option_links__option_type", "option_links__value"
    ).get(pk=variant.pk)

    assert option_types.variant_axes(variant) == {
        "size": "M",
        "color": "Blau",
        "material": "Baumwolle",
    }
    ordered = option_types.variant_axes(variant, ["material", "size"])
    assert list(ordered) == ["material", "size"]
    assert option_types.axes_label(ordered) == "Baumwolle · M"


def test_one_value_per_type_and_variant():
    from django.db import IntegrityError, transaction

    product = ProductFactory()
    variant = ProductVariant.objects.create(product=product, label="A")
    t = OptionType.objects.create(code="flavor", standard="flavor")
    a = OptionValue.objects.create(option_type=t, value="Vanille")
    b = OptionValue.objects.create(option_type=t, value="Schoko")
    VariantOption.objects.create(variant=variant, option_type=t, value=a)
    with pytest.raises(IntegrityError), transaction.atomic():
        VariantOption.objects.create(variant=variant, option_type=t, value=b)


def test_type_label_prefers_own_name_then_standard():
    assert option_types.type_label(OptionType(code="material", standard="material")) == "Material"
    assert option_types.type_label(OptionType(code="stoffart", name="Stoffart")) == "Stoffart"


def test_product_option_axes_default_empty():
    assert ProductFactory().option_axes == []
