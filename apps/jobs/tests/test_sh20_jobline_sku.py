"""SH-20: строка сметы держит СНИМОК Art.-Nr. детали (вариант сильнее товара) и печатает
его на карточке, в PDF и в снимке счёта."""

from decimal import Decimal

import pytest

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.jobs.pdf import build_quote_pdf
from apps.jobs.services import lines_snapshot, set_lines
from apps.jobs.tests.test_vat_per_line import _job

pytestmark = pytest.mark.django_db


def test_set_lines_snapshots_the_article_number():
    job = _job()
    product = ProductFactory(base_price=Decimal("10.00"), sku="TEIL-1", name={"de": "Dichtung"})
    variant = ProductVariant.objects.create(
        product=product, label="XL", price=Decimal("12.00"), sku="TEIL-1-XL"
    )
    set_lines(
        job,
        [
            {"text": "Dichtung", "qty": 1, "unit_price": "10.00", "product": product},
            {
                "text": "Dichtung XL",
                "qty": 1,
                "unit_price": "12.00",
                "product": product,
                "variant": variant,
            },
            {"text": "Arbeit", "qty": 2, "unit_price": "50.00"},
        ],
    )
    skus = [ln.sku for ln in job.lines.all()]
    assert skus == ["TEIL-1", "TEIL-1-XL", ""]
    assert [ln["sku"] for ln in lines_snapshot(job)] == ["TEIL-1", "TEIL-1-XL", ""]
    product.delete()  # SET_NULL у FK — снимок артикула переживает удаление детали
    assert [ln.sku for ln in job.lines.all()][:2] == ["TEIL-1", "TEIL-1-XL"]
    from apps.tenants.tests.factories import TenantFactory

    assert build_quote_pdf(job, TenantFactory.build())[:4] == b"%PDF"
