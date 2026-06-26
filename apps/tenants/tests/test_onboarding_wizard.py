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
    # вправе пересчитать его при смене типа на шаге 1. B.4: линейный 7-шаговый флоу.
    tenant = TenantFactory(
        schema_name="public",
        slug="walk",
        name="Walk",
        business_type="other",
        disabled_modules=modules.default_disabled_for("other"),
    )
    # Шаг 1: тип бизнеса → предвыбор блоков.
    response = core_views.setup_view(_req("post", {"business_type": "cafe"}, tenant))
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.business_type == "cafe"
    assert set(tenant.disabled_modules) == set(modules.default_disabled_for("cafe"))
    assert onboarding.get_state(tenant)["step"] == 2
    # Шаг 2 (B.2): выбор шаблона витрины.
    core_views.setup_view(_req("post", {"template": "gastro"}, tenant))
    assert onboarding.get_state(tenant)["step"] == 3
    # Шаг 3: владелец оставил только акции.
    core_views.setup_view(_req("post", {"modules": ["promotions"]}, tenant))
    tenant.refresh_from_db()
    assert "loyalty" in tenant.disabled_modules and "promotions" not in tenant.disabled_modules
    # Шаг 4: basics.
    core_views.setup_view(
        _req(
            "post",
            {"address": "Hauptstr. 1", "opening_hours": "Mo–Fr 8–18", "contact_phone": "0211/1"},
            tenant,
        )
    )
    tenant.refresh_from_db()
    assert tenant.address == "Hauptstr. 1" and tenant.opening_hours == "Mo–Fr 8–18"
    assert onboarding.get_state(tenant)["step"] == 5
    # Шаг 5 (B.3): баннер (hero-тексты).
    core_views.setup_view(_req("post", {"hero_title": "Hallo", "hero_text": "Schön"}, tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Hallo"
    assert onboarding.get_state(tenant)["step"] == 6
    # Шаг 6: «Weiter» → шаг 7.
    core_views.setup_view(_req("post", {}, tenant))
    # Шаг 7: финал, мастер завершён.
    core_views.setup_view(_req("post", {}, tenant))
    tenant.refresh_from_db()
    state = onboarding.get_state(tenant)
    assert state["step"] == 7 and state["completed"]
    assert onboarding.progress(tenant) == (7, 7)


def test_skip_advances_without_changes():
    tenant = TenantFactory(business_type="bakery")
    core_views.setup_view(_req("post", {"action": "skip", "business_type": "hotel"}, tenant))
    tenant.refresh_from_db()
    assert tenant.business_type == "bakery"  # skip ничего не пишет
    state = onboarding.get_state(tenant)
    assert state["step"] == 2 and state["skipped"] == [1]


def test_resume_renders_current_step():
    tenant = TenantFactory()
    onboarding.save_state(tenant, {"step": 4, "skipped": [], "completed": False})
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Basics" in html and "Öffnungszeiten" in html
    onboarding.save_state(tenant, {"step": 7, "skipped": [], "completed": True})
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Geschafft" in html


def test_step2_shows_theme_picker():
    """B.2: шаг 2 — выбор шаблона витрины (визуальные карточки)."""
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(tenant, {"step": 2, "skipped": [], "completed": False})
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Stil" in html and 'name="template"' in html


def test_step5_banner_saves_hero_texts():
    """B.3: шаг 5 — баннер (hero-тексты сохраняются в site_config)."""
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(tenant, {"step": 5, "skipped": [], "completed": False})
    core_views.setup_view(_req("post", {"hero_title": "Moin", "hero_text": "Frisch"}, tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Moin"
    assert tenant.site_config["hero_text"] == "Frisch"
    assert onboarding.get_state(tenant)["step"] == 6


def test_step6_shows_vertical_presets():
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(tenant, {"step": 6, "skipped": [], "completed": False})
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "preset=feierabend" in html and "Produkt anlegen" in html


def test_step6_loads_and_clears_demo_content():
    """B.1 (анти-Битрикс): демо-контент грузится прямо из мастера, остаёмся на шаге 6."""
    from apps.tenants import demo

    # schema_name=public → catalog/promotions доступны (как в test_demo).
    tenant = TenantFactory(
        schema_name="public", slug="wiz-demo", name="WizDemo", business_type="bakery"
    )
    onboarding.save_state(tenant, {"step": 6, "skipped": [], "completed": False})
    # GET: предложение загрузить демо.
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Beispiel-Inhalte laden" in html
    # POST load_demo → демо загружено, шаг не сменился.
    response = core_views.setup_view(_req("post", {"action": "load_demo"}, tenant))
    assert response.status_code == 302
    assert demo.has_demo(tenant) is True
    assert onboarding.get_state(tenant)["step"] == 6
    # Теперь предлагается убрать; clear_demo очищает.
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "entfernen" in html
    core_views.setup_view(_req("post", {"action": "clear_demo"}, tenant))
    assert demo.has_demo(tenant) is False


# --- плашка на дашборде + сохранность состояния ---------------------------------


def test_dashboard_shows_progress_until_completed():
    tenant = TenantFactory()
    onboarding.save_state(tenant, {"step": 3, "skipped": [1], "completed": False})
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Setup-Fortschritt: 2/7" in html
    onboarding.save_state(tenant, {"step": 5, "skipped": [], "completed": True})
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Setup-Fortschritt" not in html


def test_dashboard_redirects_fresh_owner_to_wizard():
    """AB5: нетронутый мастер (свежая регистрация) → дашборд уводит в Wizard."""
    tenant = TenantFactory()  # дефолтный site_config → нетронутое состояние
    response = core_views.dashboard(_req(tenant=tenant))
    assert response.status_code == 302
    assert response.url == "/dashboard/setup/"


def test_dashboard_renders_once_wizard_touched():
    """AB5: после любого действия в мастере дашборд больше не гейтит."""
    tenant = TenantFactory()
    # один «Weiter»/skip → шаг 2 → больше не нетронуто.
    onboarding.save_state(tenant, {"step": 2, "skipped": [], "completed": False})
    assert core_views.dashboard(_req(tenant=tenant)).status_code == 200
    # пропуск первого шага (skipped=[1]) тоже снимает гейт, даже если step вернули на 1.
    onboarding.save_state(tenant, {"step": 1, "skipped": [1], "completed": False})
    assert core_views.dashboard(_req(tenant=tenant)).status_code == 200
    # завершённый мастер → дашборд рендерится.
    onboarding.save_state(tenant, {"step": 7, "skipped": [], "completed": True})
    assert core_views.dashboard(_req(tenant=tenant)).status_code == 200


def test_site_view_save_keeps_wizard_state():
    tenant = TenantFactory()
    onboarding.save_state(tenant, {"step": 2, "skipped": [], "completed": False})
    response = core_views.site_view(_req("post", {"hero_title": "Hallo"}, tenant))
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Hallo"
    assert onboarding.get_state(tenant)["step"] == 2


def test_step1_keeps_custom_modules_of_existing_tenant():
    """Hotfix: тот же тип на шаге 1 не сбрасывает модули настроенных компаний.

    Легаси-тенант (disabled_modules=[] = всё включено) подтверждает свой тип —
    разделы кабинета (CRM/Analytics/Channels) не должны «пропасть». Смена типа
    — другое дело (гибрид): набор подстраивается, см. тест ниже.
    """
    tenant = TenantFactory(business_type="bakery", disabled_modules=[])
    core_views.setup_view(_req("post", {"business_type": "bakery"}, tenant))
    tenant.refresh_from_db()
    assert tenant.disabled_modules == []  # конфигурация не тронута


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


def test_step1_type_change_reapplies_preset_even_for_custom_config():
    """Гибрид: смена типа на шаге 1 = «я такой бизнес» → набор подстраивается
    под тип даже у настроенного тенанта (магазину Booking выключится)."""
    tenant = TenantFactory(business_type="cafe", disabled_modules=["crm"])  # ручной набор
    core_views.setup_view(_req("post", {"business_type": "retail"}, tenant))
    tenant.refresh_from_db()
    assert sorted(tenant.disabled_modules) == sorted(modules.default_disabled_for("retail"))
    # тот же тип без изменений — ручной набор не трогаем
    tenant2 = TenantFactory(business_type="bakery", disabled_modules=["crm"])
    core_views.setup_view(_req("post", {"business_type": "bakery"}, tenant2))
    tenant2.refresh_from_db()
    assert tenant2.disabled_modules == ["crm"]


# --- AB3: живое превью на шагах мастера --------------------------------------------
def test_setup_shows_live_preview_iframe_on_content_steps(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="public",
        slug="prev",
        name="Prev",
        business_type="cafe",
        site_config={"onboarding": {"step": 2, "skipped": [], "completed": False}},
    )
    html = core_views.setup_view(_req("get", tenant=tenant)).content.decode()
    assert "Live preview" in html
    assert '<iframe src="/"' in html  # превью витрины


def test_setup_no_preview_on_first_step(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="public",
        slug="prev1",
        name="Prev1",
        business_type="cafe",
        site_config={"onboarding": {"step": 1, "skipped": [], "completed": False}},
    )
    html = core_views.setup_view(_req("get", tenant=tenant)).content.decode()
    assert "Live preview" not in html  # на выборе типа превью не нужно
