"""G11 / G11a: расходники сметы (Teile) → каталог + списание остатка при erledigt.

Списываем склад один раз, на переходе accepted→done; только по строкам с
привязкой к товару/варианту и учётом остатка (stock_quantity не null); работа
выполнена → не блокируем, клампим в 0; идемпотентно (job.stock_committed)."""

import pytest

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.jobs import services
from apps.jobs.state_machine import JobSM

pytestmark = pytest.mark.django_db


def _job(**kwargs):
    kwargs.setdefault("title", "Reparatur")
    kwargs.setdefault("name", "Kunde")
    return services.create_job(**kwargs)


def _to_done(job):
    sm = JobSM()
    for dst in ("quoted", "accepted", "done"):
        job = sm.apply(job, dst)
    return job


# --- привязка строки к каталогу ----------------------------------------------------


def test_set_lines_links_product_and_variant():
    job = _job()
    product = ProductFactory(base_price="49.00")
    variant = ProductVariant.objects.create(product=product, label="5W-30")
    services.set_lines(
        job,
        [
            {"text": "Arbeitszeit", "qty": 1, "unit_price": "60.00"},  # без привязки
            {"text": "Öl", "qty": 1, "unit_price": "49.00", "product": product},
            {"text": "Filter", "qty": 1, "unit_price": "12.00", "variant": variant},
        ],
    )
    lines = list(job.lines.all())
    assert lines[0].product_id is None and lines[0].variant_id is None
    assert lines[1].product_id == product.id
    assert lines[2].variant_id == variant.id


# --- списание остатка при erledigt -------------------------------------------------


def test_done_decrements_tracked_product_stock():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    services.set_lines(job, [{"text": "Teil", "qty": 3, "unit_price": "5.00", "product": product}])
    job = _to_done(job)
    product.refresh_from_db()
    assert product.stock_quantity == 7
    assert job.stock_committed is True


def test_done_decrements_variant_stock():
    job = _job()
    product = ProductFactory(stock_quantity=None)
    variant = ProductVariant.objects.create(product=product, label="M", stock_quantity=5)
    services.set_lines(
        job, [{"text": "Teil M", "qty": 2, "unit_price": "5.00", "variant": variant}]
    )
    _to_done(job)
    variant.refresh_from_db()
    assert variant.stock_quantity == 3


def test_untracked_stock_not_touched():
    job = _job()
    product = ProductFactory(stock_quantity=None)  # null = без учёта
    services.set_lines(job, [{"text": "Teil", "qty": 4, "unit_price": "5.00", "product": product}])
    _to_done(job)
    product.refresh_from_db()
    assert product.stock_quantity is None


def test_labor_line_no_stock_effect():
    job = _job()
    services.set_lines(job, [{"text": "Nur Arbeit", "qty": 8, "unit_price": "55.00"}])
    job = _to_done(job)  # без привязок — не падает
    assert job.stock_committed is True


def test_decrement_clamps_at_zero_not_blocked():
    """Работа выполнена → не блокируем при нехватке, остаток клампится в 0."""
    job = _job()
    product = ProductFactory(stock_quantity=2)
    services.set_lines(job, [{"text": "Teil", "qty": 5, "unit_price": "5.00", "product": product}])
    job = _to_done(job)  # перехода не блокирует
    product.refresh_from_db()
    assert product.stock_quantity == 0 and job.status == "done"


def test_commit_stock_idempotent():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    services.set_lines(job, [{"text": "Teil", "qty": 3, "unit_price": "5.00", "product": product}])
    _to_done(job)  # списал 3 → 7
    services.commit_stock(job)  # повтор — гард stock_committed, без двойного списания
    product.refresh_from_db()
    assert product.stock_quantity == 7
