"""M21.7: update_prices — цены фасовок, «только одна фасовка», удаление по артикулу."""

import contextlib
import io
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalog.models import Product, ProductVariant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(monkeypatch):
    TenantFactory(schema_name="teeladen")
    monkeypatch.setattr(
        "apps.imports.management.commands.update_prices.schema_context",
        lambda _s: contextlib.nullcontext(),
    )


def _tea(sku="HT515", prices=("9.00", "20.95")):
    p = Product.objects.create(name={"de": "Silver"}, sku=sku, base_price=Decimal(prices[0]))
    for i, (label, price) in enumerate(zip(("100 g", "250 g", "500 g"), prices, strict=False)):
        ProductVariant.objects.create(
            product=p,
            label=label,
            sku=sku if i == 0 else f"{sku}.{i}",
            price=Decimal(price),
            content_amount=Decimal(label.split()[0]),
            sort_order=i,
        )
    return p


def _run(tmp_path, text, apply=False):
    f = tmp_path / "preise.csv"
    f.write_text(text, encoding="utf-8")
    out = io.StringIO()
    call_command("update_prices", schema="teeladen", file=str(f), apply=apply, stdout=out)
    return out.getvalue()


def test_dry_run_changes_nothing_apply_sets_prices(shop, tmp_path):
    tea = _tea()
    text = "artikel;groesse;preis;aktion\nht515;100 g;9,30\nHT515;250g;22,10\n"
    out = _run(tmp_path, text)
    assert "9,00 → 9,30" in out and "dry-run" in out
    assert ProductVariant.objects.get(sku="HT515").price == Decimal("9.00")
    _run(tmp_path, text, apply=True)
    assert ProductVariant.objects.get(sku="HT515").price == Decimal("9.30")
    assert ProductVariant.objects.get(sku="HT515.1").price == Decimal("22.10")
    tea.refresh_from_db()
    assert tea.base_price == Decimal("9.30")  # цена в списках = первая фасовка


def test_only_one_pack_and_hidden_herb_becomes_visible(shop, tmp_path):
    tea = _tea("HT630")
    herb = Product.objects.create(
        name={"de": "Nanaminze"},
        sku="HT90644",
        base_price=Decimal("0"),
        is_active=False,
        primary_action="request",
    )
    _run(tmp_path, "HT630;100 g;12,20;nur\nHT90644;50 g;4,99;nur\n", apply=True)
    tea.refresh_from_db()
    herb.refresh_from_db()
    assert not tea.variants.filter(is_active=True).exists()
    assert tea.base_price == Decimal("12.20") and tea.content_amount == 100
    assert herb.is_active and herb.primary_action == "" and herb.base_price == Decimal("4.99")
    assert herb.content_amount == 50 and herb.unit == "g"


def test_delete_and_errors_do_not_stop_other_rows(shop, tmp_path):
    _tea("HT428")
    _tea("HT536")
    out = _run(
        tmp_path,
        "HT428;;;loeschen\nHT999;100 g;1,00\nHT536;333 g;1,00\nHT536;100 g;abc\nHT536;100 g;8,20\n",
        apply=True,
    )
    assert not Product.objects.filter(sku="HT428").exists()
    assert (
        "Artikel nicht gefunden" in out and "333 g gibt es nicht" in out and "nicht lesbar" in out
    )
    assert "errors: 3" in out
    assert ProductVariant.objects.get(sku="HT536").price == Decimal("8.20")


def test_marked_prices_survive_cscart_rerun(shop, tmp_path):
    from types import SimpleNamespace

    from apps.imports import cscart

    tea = _tea()
    _run(tmp_path, "HT515;100 g;9,30\n", apply=True)
    tea.refresh_from_db()
    assert tea.metadata.get(cscart.OWNER_PRICES_KEY) is True
    old_site = SimpleNamespace(
        sku="HT515",
        name="Silver",
        variants=[
            SimpleNamespace(
                sku="HT515",
                price=Decimal("9.00"),
                label="100 g",
                grams=100,
                in_stock=True,
                image_url="",
            ),
            SimpleNamespace(
                sku="HT515.1",
                price=Decimal("20.95"),
                label="250 g",
                grams=250,
                in_stock=True,
                image_url="",
            ),
        ],
    )
    cscart._save_variants(tea, old_site, None, cscart.ApplyStats())
    assert ProductVariant.objects.get(sku="HT515").price == Decimal("9.30")


# --- мастер импорта, тип «Preisliste» -------------------------------------------------


def test_wizard_price_list_validates_then_applies_same_rules():
    from apps.imports.processors import get_processor

    _tea()
    proc = get_processor("price_list")
    good = {"sku": "ht515", "size": "250g", "price": "22,10", "action": ""}
    assert proc.validate(good) == []
    assert proc.validate({**good, "size": "333 g"})  # нет такой фасовки
    assert proc.validate({**good, "sku": "HT999"})
    assert proc.validate({**good, "action": "irgendwas"})
    assert ProductVariant.objects.get(sku="HT515.1").price == Decimal("20.95")  # без записи
    obj = proc.create_or_update(good, update_existing=False)
    assert obj.sku == "HT515"
    assert ProductVariant.objects.get(sku="HT515.1").price == Decimal("22.10")
    assert proc.validate({"sku": "HT515", "action": "löschen"}) == []


def test_wizard_guesses_columns_of_the_price_file():
    from apps.imports.views import guess_column

    got = [guess_column("price_list", h) for h in ("artikel", "Groesse", "PREIS", "aktion", "x")]
    assert got == ["sku", "size", "price", "action", ""]
