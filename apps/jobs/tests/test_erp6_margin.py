"""ERP-6: плановые часы × ставка на строке сметы → маржа Работы (кабинет).

Замки по плану `docs/erp57-plan-2026-08-21.md §ERP-6`: снимок EK детали при
пустой ставке, калькуляция по строкам с известной ставкой, и главный
инвариант — cost_rate НЕ течёт в публичную смету и PDF (интерн)."""

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.jobs import public_views, services, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/auftraege/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _job():
    return services.create_job(title="Bad streichen", name="Kunde")


def test_set_lines_stores_cost_rate_and_plan_calc():
    job = _job()
    services.set_lines(
        job,
        [
            {"text": "Arbeit", "qty": Decimal("3.5"), "unit_price": "60", "cost_rate": "40"},
            {"text": "Anfahrt", "qty": 1, "unit_price": "30"},  # ставка неизвестна
        ],
        vat_rate=Decimal("19.00"),
    )
    plan = job.plan_calc()
    assert plan["cost"] == Decimal("140.00")  # 3,5 × 40
    assert plan["margin"] == job.net - Decimal("140.00")
    assert plan["partial"] is True  # Anfahrt без ставки — итог честно помечен
    # Ни одной ставки → блока нет.
    services.set_lines(job, [{"text": "Arbeit", "qty": 1, "unit_price": "60"}])
    assert job.plan_calc() is None


def test_save_lines_snapshots_part_ek_when_cost_blank():
    product = ProductFactory(cost_price=Decimal("2.20"), base_price=Decimal("5.00"))
    job = _job()
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": f"p:{product.pk}",
                "line_qty_1": "4",
                "line_text_2": "Arbeitszeit",
                "line_qty_2": "2",
                "line_price_2": "55",
                "line_cost_2": "38,50",  # немецкая запятая
            },
        ),
        pk=job.pk,
    )
    lines = {ln.text: ln for ln in job.lines.all()}
    part = next(ln for ln in lines.values() if ln.product_id == product.pk)
    assert part.cost_rate == Decimal("2.20")  # снимок EK детали
    assert lines["Arbeitszeit"].cost_rate == Decimal("38.50")


def test_cabinet_shows_kalkulation_block():
    job = _job()
    services.set_lines(job, [{"text": "Arbeit", "qty": 2, "unit_price": "50", "cost_rate": "30"}])
    html = views.job_detail(_req(), pk=job.pk).content.decode()
    assert "Kalkulation (intern)" in html and "Plan-Marge" in html


def test_cost_rate_never_leaks_to_public_quote_or_pdf():
    job = _job()
    services.set_lines(
        job,
        [{"text": "Arbeit", "qty": 1, "unit_price": "100", "cost_rate": "77.77"}],
        vat_rate=Decimal("19.00"),
    )
    from apps.jobs.state_machine import JobSM

    JobSM().apply(job, "quoted")
    html = public_views.angebot(
        _req(path=f"/angebot/{job.public_token}/"), token=job.public_token
    ).content.decode()
    assert "77,77" not in html and "77.77" not in html
    assert "Kalkulation" not in html
    # PDF рендерит строки по явным полям — cost_rate в генераторе не упоминается
    # (скан-замок исходника: прецедент i18n-скана псевдонимов).
    src = Path("apps/jobs/pdf.py").read_text()
    assert "cost_rate" not in src
