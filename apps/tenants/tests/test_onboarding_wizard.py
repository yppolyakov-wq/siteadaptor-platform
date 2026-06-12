"""Track D / D0c: Onboarding-Wizard — прохождение/пропуск/возобновление,
дефолты по типу, плашка Setup-Fortschritt, сохранность состояния в site_config."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import modules
from apps.core import views as core_views
from apps.tenants import onboarding, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/setup/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


# --- состояние ----------------------------------------------------------------


def test_get_state_defaults_on_garbage():
    tenant = TenantFactory.build(
        site_config={"onboarding": {"step": 99, "skipped": ["x", 2, 7], "completed": "nope"}}
    )
    state = onboarding.get_state(tenant)
    assert state == {"step": 1, "skipped": [2], "completed": True}
    assert onboarding.get_state(TenantFactory.build()) == {
        "step": 1,
        "skipped": [],
        "completed": False,
    }


def test_normalize_preserves_onboarding():
    config = siteconfig.normalize({"onboarding": {"step": 3, "skipped": [], "completed": False}})
    assert config["onboarding"]["step"] == 3


# --- прохождение мастера --------------------------------------------------------


def test_full_walkthrough_sets_fields_and_completes():
    # Новый тенант: create_business ставит пресет вертикали (D0b) — мастер
    # вправе пересчитать его при смене типа на шаге 1.
    tenant = TenantFactory(
        business_type="other", disabled_modules=modules.default_disabled_for("other")
    )
    # Шаг 1: тип бизнеса → предвыбор блоков.
    response = core_views.setup_view(_req("post", {"business_type": "cafe"}, tenant))
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.business_type == "cafe"
    assert set(tenant.disabled_modules) == set(modules.default_disabled_for("cafe"))
    assert onboarding.get_state(tenant)["step"] == 2
    # Шаг 2: владелец оставил только акции.
    core_views.setup_view(_req("post", {"modules": ["promotions"]}, tenant))
    tenant.refresh_from_db()
    assert "loyalty" in tenant.disabled_modules and "promotions" not in tenant.disabled_modules
    # Шаг 3: basics.
    core_views.setup_view(
        _req(
            "post",
            {"address": "Hauptstr. 1", "opening_hours": "Mo–Fr 8–18", "contact_phone": "0211/1"},
            tenant,
        )
    )
    tenant.refresh_from_db()
    assert tenant.address == "Hauptstr. 1" and tenant.opening_hours == "Mo–Fr 8–18"
    assert onboarding.get_state(tenant)["step"] == 4
    # Шаг 4: «Weiter» → финал, мастер завершён.
    core_views.setup_view(_req("post", {}, tenant))
    tenant.refresh_from_db()
    state = onboarding.get_state(tenant)
    assert state["step"] == 5 and state["completed"]
    assert onboarding.progress(tenant) == (5, 5)


def test_skip_advances_without_changes():
    tenant = TenantFactory(business_type="bakery")
    core_views.setup_view(_req("post", {"action": "skip", "business_type": "hotel"}, tenant))
    tenant.refresh_from_db()
    assert tenant.business_type == "bakery"  # skip ничего не пишет
    state = onboarding.get_state(tenant)
    assert state["step"] == 2 and state["skipped"] == [1]


def test_resume_renders_current_step():
    tenant = TenantFactory()
    onboarding.save_state(tenant, {"step": 3, "skipped": [], "completed": False})
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Basics" in html and "Öffnungszeiten" in html
    onboarding.save_state(tenant, {"step": 5, "skipped": [], "completed": True})
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Geschafft" in html


def test_step4_shows_vertical_presets():
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(tenant, {"step": 4, "skipped": [], "completed": False})
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "preset=feierabend" in html and "Produkt anlegen" in html


# --- плашка на дашборде + сохранность состояния ---------------------------------


def test_dashboard_shows_progress_until_completed():
    tenant = TenantFactory()
    onboarding.save_state(tenant, {"step": 3, "skipped": [1], "completed": False})
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Setup-Fortschritt: 2/5" in html
    onboarding.save_state(tenant, {"step": 5, "skipped": [], "completed": True})
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Setup-Fortschritt" not in html


def test_site_view_save_keeps_wizard_state():
    tenant = TenantFactory()
    onboarding.save_state(tenant, {"step": 2, "skipped": [], "completed": False})
    response = core_views.site_view(_req("post", {"hero_title": "Hallo"}, tenant))
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Hallo"
    assert onboarding.get_state(tenant)["step"] == 2


def test_step1_keeps_custom_modules_of_existing_tenant():
    """Hotfix: мастер не сбрасывает модули у действующих/настроенных компаний.

    Легаси-тенант (disabled_modules=[] = всё включено) проходит шаг 1 —
    разделы кабинета (CRM/Analytics/Channels) не должны «пропасть».
    """
    tenant = TenantFactory(business_type="bakery", disabled_modules=[])
    core_views.setup_view(_req("post", {"business_type": "bakery"}, tenant))
    tenant.refresh_from_db()
    assert tenant.disabled_modules == []  # конфигурация не тронута

    # Ручная конфигурация (отличается от пресета) тоже переживает смену типа.
    tenant2 = TenantFactory(business_type="bakery", disabled_modules=["crm"])
    core_views.setup_view(_req("post", {"business_type": "cafe"}, tenant2))
    tenant2.refresh_from_db()
    assert tenant2.business_type == "cafe"
    assert tenant2.disabled_modules == ["crm"]


def test_step1_reapplies_untouched_preset_on_type_change():
    """Новый тенант ещё на пресете → смена типа на шаге 1 пересчитывает пресет."""
    preset = modules.default_disabled_for("bakery")
    tenant = TenantFactory(business_type="bakery", disabled_modules=preset)
    core_views.setup_view(_req("post", {"business_type": "cafe"}, tenant))
    tenant.refresh_from_db()
    assert sorted(tenant.disabled_modules) == sorted(modules.default_disabled_for("cafe"))


def test_back_button_steps_back_and_unskips():
    tenant = TenantFactory()
    onboarding.save_state(tenant, {"step": 3, "skipped": [2], "completed": False})
    core_views.setup_view(_req("post", {"action": "back"}, tenant))
    assert onboarding.get_state(tenant) == {"step": 2, "skipped": [], "completed": False}
    # с первого шага назад некуда
    onboarding.save_state(tenant, {"step": 1, "skipped": [], "completed": False})
    core_views.setup_view(_req("post", {"action": "back"}, tenant))
    assert onboarding.get_state(tenant)["step"] == 1
    # «Zurück» с финального экрана не раз-завершает мастер
    onboarding.save_state(tenant, {"step": 5, "skipped": [], "completed": True})
    core_views.setup_view(_req("post", {"action": "back"}, tenant))
    state = onboarding.get_state(tenant)
    assert state["step"] == 4 and state["completed"] is True
