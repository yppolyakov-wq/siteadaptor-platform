"""ST-6a: Marketing-центр — лендинг /dashboard/marketing/.

Замки: карточки в ROI-порядке и гейт по модулям, обзор напоминаний из матрицы
UD4-2 (read-only) + win-back-строка, панель результатов из готовых источников
(views акций/кампании; только чтение), хаб-плитка «Marketing» ведёт на центр.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import dashboard as dash
from apps.core import marketing_home as mh
from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant=None):
    req = RequestFactory().get("/dashboard/marketing/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    req.tenant = tenant
    return req


def test_landing_renders_cards_and_reminders():
    t = TenantFactory(slug="mh1", name="Mh1")
    body = core_views.marketing_home(_req(tenant=t)).content.decode()
    assert "Erinnerungen &amp; Care-Zyklus" in body or "Erinnerungen & Care-Zyklus" in body
    assert "Bewertungen" in body and "Kampagnen" in body
    # обзор авто-касаний: строки reminder-событий матрицы UD4-2 с индикаторами
    assert "Aktive Erinnerungen" in body and "Zahlungserinnerung" in body
    assert "E-Mail" in body and "Telegram" in body


def test_cards_gate_by_module():
    t = TenantFactory(slug="mh2", name="Mh2", disabled_modules=["loyalty", "reviews"])
    labels = [c["label"] for c in mh.cards(t)]
    assert not any("Treue" in str(lbl) for lbl in labels)
    assert not any("Bewertungen" in str(lbl) for lbl in labels)
    assert any("Erinnerungen" in str(lbl) for lbl in labels)  # всегда


def test_results_panel_reads_ready_sources():
    from apps.loyalty.models import Voucher
    from apps.promotions.models import CouponCampaign
    from apps.promotions.tests.factories import PromotionFactory

    t = TenantFactory(slug="mh3", name="Mh3")
    PromotionFactory(views=7)
    camp = CouponCampaign.objects.create(name="Stammkunden")
    Voucher.objects.create(code=f"C{uuid4().hex[:8]}", campaign=camp, used_count=2)

    metrics = mh.results_panel(t)
    by_label = {str(m["label"]): m for m in metrics}
    views = next(m for lbl, m in by_label.items() if "Aufrufe" in lbl)
    assert views["value"] == 7
    camp_m = next(m for lbl, m in by_label.items() if "Kampagnen" in lbl)
    assert camp_m["value"] == "1 · 2"


def test_reminder_overview_includes_winback_row():
    from apps.promotions.models import CouponCampaign

    t = TenantFactory(slug="mh4", name="Mh4")
    assert mh.reminder_overview(t)["winback"] is None
    CouponCampaign.objects.create(
        name="WB", kind=CouponCampaign.KIND_AUTO_WINBACK, status=CouponCampaign.STATUS_ACTIVE
    )
    wb = mh.reminder_overview(t)["winback"]
    assert wb is not None and wb["active"] is True


def test_hub_tile_marketing_points_to_center():
    t = TenantFactory(slug="mh5", name="Mh5")
    tile = next(x for x in dash.hub_tiles(t) if x["key"] == "marketing")
    assert tile["url_name"] == "marketing-home"
