"""FB-24e: демо-носитель опций — Wohnwerk, наволочка «Farbe × Material»."""

import pytest

from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_wohnwerk_cushion_has_material_axis():
    from apps.catalog import option_types, options
    from apps.catalog.models import Product

    tenant = TenantFactory(schema_name="public", slug="ww", name="Wohnwerk", business_type="retail")
    assert demo_kits.apply_kit(tenant, "wohnwerk") is True
    p = Product.objects.get(name__de="Kissenbezug Leinen")
    assert options.product_axes(p) == ["color", "material"]
    variants = p.variants.prefetch_related("option_links__option_type", "option_links__value")
    combos = {tuple(option_types.variant_axes(v, ["color", "material"]).values()) for v in variants}
    assert combos == {
        ("Sand", "Leinen"),
        ("Sand", "Baumwolle"),
        ("Grau", "Leinen"),
        ("Grau", "Baumwolle"),
    }
