"""SH-19 (фидбэк 2026-09-03 «на сайте в товаре выводить основной артикул»): витрина
печатала Art.-Nr. и раньше — но у ВСЕХ демо-товаров SKU был пуст, а в форме товара поле
пряталось в свёрнутом «Mehr anzeigen». Замки: демо-артикулы детерминированы и уникальны;
поле SKU в рейле цены на виду; артикул в корзине.

План — `docs/order-feedback-plan-2026-09-03.md` §3.
"""

from pathlib import Path

import pytest

from apps.catalog.models import Product, ProductVariant
from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def test_demo_kit_products_get_deterministic_unique_skus():
    tenant = TenantFactory(schema_name="public", slug="sh19", name="SH19", business_type="bakery")
    assert demo_kits.apply_kit(tenant, "bakery") is True
    skus = list(Product.objects.values_list("sku", flat=True))
    assert skus and all(skus), "у каждого демо-товара есть артикул"
    assert len(set(skus)) == len(skus), "артикулы уникальны"
    assert all(s.startswith("BAK-") for s in skus), skus[:3]
    vskus = list(ProductVariant.objects.values_list("sku", flat=True))
    assert all(vskus) and len(set(vskus)) == len(vskus)
    # детерминизм: артикул варианта = артикул товара + порядковый номер
    v = ProductVariant.objects.select_related("product").first()
    if v is not None:
        assert v.sku.startswith(v.product.sku + "-")


def test_explicit_spec_sku_wins_over_derived(monkeypatch):
    """Явный `sku` в спеке кита сильнее автогенерации (владелец может задать свои)."""
    import copy

    kit = demo_kits.KITS["bakery"]
    cats = copy.deepcopy(kit.categories)  # категория кита = кортеж (name, slug, items, …)
    first = list(cats[0])
    first[2][0]["sku"] = "EIGEN-1"
    cats[0] = tuple(first)
    monkeypatch.setattr(kit, "categories", cats)
    tenant = TenantFactory(schema_name="public", slug="sh19b", name="SH19B", business_type="bakery")
    assert demo_kits.apply_kit(tenant, "bakery") is True
    assert Product.objects.filter(sku="EIGEN-1").exists()


def test_product_form_shows_sku_outside_the_collapsed_block():
    """Поле Art.-Nr. стоит в рейле «Preis & Bestand» ДО свёрнутого «Mehr anzeigen» —
    иначе владелец его не находит (причина пустых артикулов)."""
    src = (TEMPLATES / "catalog" / "product_form.html").read_text(encoding="utf-8")
    rail = src[src.index("data-price-rail") :]
    details = rail.index("<details")
    assert "field.name == 'sku'" in rail[:details]
    assert "field.name == 'sku'" not in rail[details:]
