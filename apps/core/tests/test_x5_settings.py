"""X5 (план x5-settings-plan-2026-08-19): настройки без скролла и телепортов.

- таб-бар настроек = два подписанных ряда (Basis/Verwaltung), прочие хабы плоские;
- «Google Bewertungen» ушёл из табов, но остался достижим (карточка + Ctrl+K);
- «Abläufe» — одна страница: заход из «Verkäufe» держит контекст продаж;
- «Mein Geschäft» — секции с якорями, все поля в DOM (инвариант W0).
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.template import Context, Template

from apps.core import modules, nav_registry
from apps.core.modules import default_disabled_for
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type):
    return TenantFactory(
        slug=f"x5-{business_type[:8]}-{uuid4().hex[:4]}",
        name="X5",
        business_type=business_type,
        disabled_modules=default_disabled_for(business_type),
    )


def _settings_tabs_html(tenant=None, nav="settings"):
    ctx = {"nav": nav}
    if tenant is not None:
        ctx["request"] = SimpleNamespace(tenant=tenant, user=None)
    return Template('{% load cabinet %}{% hub_tabs "settings" %}').render(Context(ctx))


def test_settings_tabs_render_two_labelled_rows():
    """X5-1: девять вкладок в одну строку уезжали в горизонтальный скролл —
    «Abo & Rechnung»/«Team» не были видны. Теперь два подписанных ряда."""
    html = _settings_tabs_html(_tenant("friseur"))
    assert "Basis" in html and "Verwaltung" in html
    # ряды — не скролл-контейнер прежнего вида
    assert "overflow-x-auto" not in html
    for lbl in ("Mein Geschäft", "Sprachen", "Abo &amp; Rechnung", "Team &amp; Zugriff"):
        assert lbl in html, lbl


def test_other_hubs_keep_flat_tab_bar():
    """Хабы без групп рендерятся прежней плоской строкой (разметка не тронута)."""
    html = Template('{% load cabinet %}{% hub_tabs "catalog" %}').render(
        Context({"nav": "catalog", "request": SimpleNamespace(tenant=_tenant("shop"), user=None)})
    )
    assert "overflow-x-auto" in html
    assert "Basis" not in html


def test_google_reviews_leaves_settings_tabbar_but_stays_reachable():
    """X5-2: экран остаётся, входов два (карточка Integrationen + Ctrl+K)."""
    html = _settings_tabs_html(_tenant("friseur"))
    assert "Google Bewertungen" not in html
    assert "google-reviews-settings" in {e["url_name"] for e in nav_registry.palette_entries()}


def test_ablaeufe_from_board_keeps_sales_context():
    """X5-3: заход из подпункта «Verkäufe» не телепортирует в настройки."""
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory

    from apps.core import views as core_views

    t = _tenant("friseur")
    user = get_user_model().objects.create_user(
        username=f"ab-{uuid4().hex[:8]}", email=f"ab-{uuid4().hex[:8]}@t.de", password="pw12345678"
    )
    req = RequestFactory().get("/dashboard/ablaeufe/", {"from": "board"})
    req.tenant, req.user = t, user
    html = core_views.ablaeufe_view(req).content.decode()
    assert "/dashboard/verkaeufe/" in html  # хлебная крошка назад
    assert "Basis" not in html  # таб-бар настроек не рисуется

    plain = RequestFactory().get("/dashboard/ablaeufe/")
    plain.tenant, plain.user = t, user
    html2 = core_views.ablaeufe_view(plain).content.decode()
    assert "Basis" in html2  # прежний вид из настроек


def test_ablaeufe_sidebar_child_carries_from_board():
    child = next(
        c
        for it in modules.sidebar_nav(_tenant("friseur"))
        if it["url_name"] == "verkaeufe"
        for c in it["children"]
        if c["url_name"] == "ablaeufe"
    )
    assert child["query"] == "?from=board"


def test_settings_form_keeps_every_field_in_dom():
    """Инвариант W0 (регресс-класс, стоивший 6 полей на Save): перестройка
    страницы по секциям не убирает поля из DOM — гейты только CSS."""
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views

    t = _tenant("friseur")
    req = RequestFactory().get("/dashboard/settings/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    req.user = get_user_model().objects.create_user(
        username=f"s-{uuid4().hex[:8]}", email=f"s-{uuid4().hex[:8]}@t.de", password="pw12345678"
    )
    html = core_views.settings_view(req).content.decode()
    for name in (
        "name",
        "address",
        "city",
        "contact_email",
        "contact_phone",
        "whatsapp_number",
        "website_url",
        "map_url",
        "instagram",
        "facebook",
        "linkedin",
        "tiktok",
        "youtube",
        "opening_hours",
        "service_area_plz",
        "service_area_note",
        "owner_digest_enabled",
        "auto_redeem_on_scan",
        "voucher_max_percent",
    ):
        assert f'name="{name}"' in html, name
    # секции получили якоря — чипы навигации ведут в живые id
    for anchor in ("sec-kontakt", "sec-zeiten", "sec-social", "sec-betrieb"):
        assert f'id="{anchor}"' in html, anchor
