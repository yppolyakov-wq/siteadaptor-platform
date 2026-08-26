"""VAT-1: ставка НДС на позиции сметы (фидбэк владельца 2026-08-26).

Главный инвариант волны: смета БЕЗ ставок на строках считается ровно как раньше
(строка наследует ставку документа), а смешанные ставки дают честную разбивку,
которая сходится с итогом. Иначе клиент примет один итог, а получит другой.
"""

from decimal import Decimal

import pytest

from apps.core import vat
from apps.jobs import services
from apps.jobs.services import set_lines
from apps.jobs.totals import quote_totals

pytestmark = pytest.mark.django_db


def _job():
    return services.create_job(title="Catering", name="Anna Bauer", email="anna@example.de")


def test_mixed_rates_split_into_rows_and_add_up():
    """7 % + 19 % → две строки разбивки, сумма которых равна итогу."""
    lines = [
        {"text": "Speisen", "qty": 10, "unit_price": "10.00", "vat_rate": Decimal("7.00")},
        {"text": "Service", "qty": 1, "unit_price": "100.00", "vat_rate": Decimal("19.00")},
    ]
    totals = quote_totals(lines, Decimal("19.00"))

    rates = [r["rate"] for r in totals["rows"]]
    assert rates == [Decimal("19.00"), Decimal("7.00")]
    assert totals["net"] == Decimal("200.00")
    # 100 × 7 % = 7,00 · 100 × 19 % = 19,00
    assert totals["vat"] == Decimal("26.00")
    assert totals["gross"] == Decimal("226.00")
    assert sum(r["net"] for r in totals["rows"]) == totals["net"]
    assert sum(r["vat"] for r in totals["rows"]) == totals["vat"]


def test_line_without_own_rate_follows_the_document():
    """Пустая ставка строки — это «как весь документ», а не 0 %."""
    lines = [{"text": "Arbeit", "qty": 2, "unit_price": "50.00"}]

    totals = quote_totals(lines, Decimal("7.00"))

    assert [r["rate"] for r in totals["rows"]] == [Decimal("7.00")]
    assert totals["vat"] == Decimal("7.00")


def test_small_business_zeroes_every_rate():
    """§19: ставки строк не спасают — налога нет вовсе."""
    lines = [
        {"text": "Speisen", "qty": 1, "unit_price": "100.00", "vat_rate": Decimal("7.00")},
        {"text": "Service", "qty": 1, "unit_price": "100.00", "vat_rate": Decimal("19.00")},
    ]

    totals = quote_totals(lines, Decimal("19.00"), small_business=True)

    assert totals["vat"] == Decimal("0.00")
    assert totals["gross"] == totals["net"] == Decimal("200.00")
    assert [r["rate"] for r in totals["rows"]] == [Decimal("0")]


def test_set_lines_stores_the_rate_and_totals_match():
    job = _job()

    set_lines(
        job,
        [
            {"text": "Speisen", "qty": 1, "unit_price": "100.00", "vat_rate": Decimal("7.00")},
            {"text": "Personal", "qty": 1, "unit_price": "100.00"},
        ],
    )

    stored = list(job.lines.order_by("position").values_list("vat_rate", flat=True))
    assert stored == [Decimal("7.00"), None]
    job.refresh_from_db()
    assert job.net == Decimal("200.00")
    assert job.vat_amount == Decimal("26.00")  # 7,00 + 19,00
    assert job.gross == Decimal("226.00")


def test_quote_without_per_line_rates_is_unchanged():
    """Замок совместимости: смета старого вида считается как прежде."""
    job = _job()

    set_lines(job, [{"text": "Arbeit", "qty": 3, "unit_price": "100.00"}])

    job.refresh_from_db()
    assert job.net == Decimal("300.00")
    assert job.vat_amount == Decimal("57.00")
    assert job.gross == Decimal("357.00")
    assert list(job.lines.values_list("vat_rate", flat=True)) == [None]


def test_card_shows_the_split_by_rate():
    """Карточка сделки берёт разбивку из того же калькулятора, что и документ."""
    job = _job()
    set_lines(
        job,
        [
            {"text": "Speisen", "qty": 1, "unit_price": "100.00", "vat_rate": Decimal("7.00")},
            {"text": "Service", "qty": 1, "unit_price": "100.00", "vat_rate": Decimal("19.00")},
        ],
    )

    result = vat.deal_vat("job", job)

    assert [r["rate"] for r in result["rows"]] == [Decimal("19.00"), Decimal("7.00")]
    assert result["vat"] == Decimal("26.00")
    assert result["gross"] == job.gross


def test_rate_is_taken_from_the_catalog_card():
    """Строка, привязанная к товару, наследует ставку ЕГО карточки."""
    from apps.catalog.models import Category, Product

    category = Category.objects.create(name="Speisen")
    product = Product.objects.create(
        category=category,
        name="Suppe",
        base_price=Decimal("5.00"),
        vat_rate=Decimal("7.00"),
    )
    job = _job()

    set_lines(job, [{"text": "Suppe", "qty": 2, "unit_price": "5.00", "product": product}])

    assert job.lines.get().vat_rate == Decimal("7.00")
    job.refresh_from_db()
    assert job.vat_amount == Decimal("0.70")


def test_explicit_rate_wins_over_the_catalog():
    """Владелец правит ставку в строке — снимок держит его выбор, не каталог."""
    from apps.catalog.models import Category, Product

    category = Category.objects.create(name="Teile")
    product = Product.objects.create(
        category=category,
        name="Filter",
        base_price=Decimal("10.00"),
        vat_rate=Decimal("7.00"),
    )
    job = _job()

    set_lines(
        job,
        [
            {
                "text": "Filter",
                "qty": 1,
                "unit_price": "10.00",
                "product": product,
                "vat_rate": Decimal("19.00"),
            }
        ],
    )

    assert job.lines.get().vat_rate == Decimal("19.00")


def test_document_rate_survives_german_decimal_comma():
    """Баг стенда: в немецкой локали селект шлёт «7,00», а не «7.00».

    Сравнение со строкой «7.00» не совпадало никогда — выбор ставки документа
    молча сбрасывался в 19 %.
    """
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.jobs import views
    from apps.tenants.tests.factories import TenantFactory

    job = _job()
    request = RequestFactory().post(
        "/dashboard/auftraege/",
        {
            "action": "save_lines",
            "line_text_1": "Speisen",
            "line_qty_1": "1",
            "line_price_1": "100,00",
            "vat_rate": "7,00",
        },
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    request.tenant = TenantFactory.build()

    views.job_detail(request, pk=job.pk)

    job.refresh_from_db()
    assert job.vat_rate == Decimal("7.00")
    assert job.vat_amount == Decimal("7.00")
