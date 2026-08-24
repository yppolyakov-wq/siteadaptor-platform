"""X5 (план x5-settings-plan-2026-08-19): настройки без скролла и телепортов.

R7-1 (2026-08-24): таб-бары со страниц сняты целиком — состав настроек живёт
подменю раздела «Einstellungen» в сайдбаре. Замки рядов табов переписаны
осознанно на новую поверхность (смысл сохранён: все экраны настроек видимы
и достижимы, скролла/телепортов нет).

- состав настроек виден целиком в подменю раздела;
- «Google Bewertungen» ушёл из табов, но остался достижим (карточка + Ctrl+K);
- «Abläufe» — одна страница: заход из «Verkäufe» держит контекст продаж;
- «Mein Geschäft» — секции с якорями, все поля в DOM (инвариант W0).
"""

from uuid import uuid4

import pytest

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


def _settings_submenu(tenant):
    """R7-1: подписи подпунктов раздела «Einstellungen» в сайдбаре."""
    items = modules.sidebar_nav(tenant)
    section = next(it for it in items if it["nav_key"] == "settings")
    return [str(c["label"]) for c in section["children"]]


def test_settings_screens_all_visible_in_submenu():
    """X5-1 (переписан под R7-1): девять вкладок уезжали в скролл, «Abo &
    Rechnung»/«Team» не были видны. Теперь весь состав — вертикальным подменю
    раздела, ничего не прячется."""
    kids = _settings_submenu(_tenant("friseur"))
    for lbl in ("Mein Geschäft", "Sprachen", "Abo & Rechnung", "Team & Zugriff"):
        assert lbl in kids, lbl


def test_google_reviews_stays_reachable_without_own_menu_entry():
    """X5-2: экран остаётся, входов два (карточка Integrationen + Ctrl+K)."""
    assert "Google Bewertungen" not in _settings_submenu(_tenant("friseur"))
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
    # R7-1: ссылка на продажи есть и в подменю сайдбара — крошку ищем по её
    # собственной разметке («← Verkäufe» перед заголовком страницы).
    crumb = "← Verkäufe"
    assert crumb in html
    plain = RequestFactory().get("/dashboard/ablaeufe/")
    plain.tenant, plain.user = t, user
    html2 = core_views.ablaeufe_view(plain).content.decode()
    assert crumb not in html2  # заход из настроек контекст продаж не подменяет


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
