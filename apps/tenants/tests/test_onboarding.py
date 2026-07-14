"""Тесты онбординга бизнеса: создание Tenant + Domain + первого User в схеме."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.utils import tenant_context

from apps.tenants.forms import BusinessSignupForm
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business


def _cleanup(tenant):
    with connection.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE')
    Domain.objects.filter(tenant=tenant).delete()
    Tenant.objects.filter(pk=tenant.pk).delete()


@pytest.mark.django_db(transaction=True)
def test_create_business_creates_tenant_domain_and_owner():
    tenant, login_url = create_business(
        business_name="Bäckerei Müller",
        slug="mueller",
        business_type="bakery",
        city="Hilden",
        email="owner@mueller.test",
        password="s3cretpass",
    )
    try:
        assert tenant.schema_name == "mueller"
        assert tenant.subscription_status == "trial"
        # D0b: стартовый набор блоков по вертикали — ровно формула реестра
        # (точные наборы по вертикалям проверяет apps/core/tests/test_modules.py).
        from apps.core import modules

        assert sorted(tenant.disabled_modules) == sorted(modules.default_disabled_for("bakery"))
        assert "promotions" not in tenant.disabled_modules  # рекомендованное включено
        assert Domain.objects.filter(tenant=tenant, is_primary=True).exists()
        assert "mueller." in login_url and login_url.endswith("/accounts/login/")

        # Владелец создан ВНУТРИ схемы арендатора.
        User = get_user_model()
        with tenant_context(tenant):
            u = User.objects.get(email="owner@mueller.test")
            assert u.check_password("s3cretpass")
    finally:
        _cleanup(tenant)


@pytest.mark.django_db
def test_signup_form_rejects_reserved_and_bad_slug():
    base = {
        "business_name": "X",
        "business_type": "bakery",
        "city": "Y",
        "email": "a@b.test",
        "password1": "longenough1",
        "password2": "longenough1",
    }
    assert not BusinessSignupForm({**base, "slug": "admin"}).is_valid()  # reserved
    assert not BusinessSignupForm({**base, "slug": "Bad_Slug"}).is_valid()  # invalid chars


@pytest.mark.django_db
def test_signup_form_password_mismatch():
    form = BusinessSignupForm(
        {
            "business_name": "X",
            "slug": "shop",
            "business_type": "bakery",
            "city": "Y",
            "email": "a@b.test",
            "password1": "longenough1",
            "password2": "different2",
        }
    )
    assert not form.is_valid()
    assert "password2" in form.errors


@pytest.mark.django_db
def test_signup_renders_business_type_as_cards(rf, settings):
    """AB3/AB5: тип бизнеса на регистрации — визуальные карточки (иконка + язык
    задач), не сухой <select>; выбор переживает ошибку валидации (checked)."""
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.tenants.views import BusinessSignupView

    settings.ROOT_URLCONF = "config.urls_public"
    html = BusinessSignupView().get(rf.get("/create/")).content.decode()
    assert 'type="radio" name="business_type"' in html  # карточки-радио, не dropdown
    assert 'value="friseur"' in html and 'value="handwerker"' in html
    assert "💇" in html and "🔧" in html  # эмодзи новых архетипов + blurb'ы
    assert "Salon" in html  # blurb карточки friseur

    # POST с одним типом (прочее пусто) → форма невалидна → повторный рендер карточками,
    # выбранный тип остаётся отмеченным (checked).
    req = rf.post("/create/", {"business_type": "friseur"})
    SessionMiddleware(lambda r: None).process_request(req)
    body = BusinessSignupView().post(req).content.decode()
    assert 'type="radio" name="business_type"' in body  # снова карточки
    assert "checked" in body  # выбор friseur сохранён


def test_signup_preselected_type_shows_compact_form_not_picker(rf, settings):
    """Фидбэк владельца: переход с Branchen-страницы (?type=restaurant) → отрасль уже
    выбрана → компактный баннер + форма (а НЕ весь пикер), «должна просто открываться
    форма регистрации»."""
    from apps.tenants.views import BusinessSignupView

    settings.ROOT_URLCONF = "config.urls_public"
    html = BusinessSignupView().get(rf.get("/registrieren/?type=restaurant")).content.decode()
    assert 'type="hidden" name="business_type" value="restaurant"' in html  # тип зафиксирован
    assert 'type="radio" name="business_type"' not in html  # без грид-пикера
    assert "Ändern" in html  # можно сменить отрасль → /registrieren/


def test_signup_invalid_type_falls_back_to_full_picker(rf, settings):
    """Неизвестный ?type= → полный пикер (не компактный баннер)."""
    from apps.tenants.views import BusinessSignupView

    settings.ROOT_URLCONF = "config.urls_public"
    html = BusinessSignupView().get(rf.get("/registrieren/?type=nonsense")).content.decode()
    assert 'type="radio" name="business_type"' in html


# --- AB4: чек-лист готовности сайта ------------------------------------------------
@pytest.mark.django_db
def test_completeness_empty_tenant_low_and_structured():
    from apps.tenants import onboarding
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(address="", opening_hours="", site_config={})
    r = onboarding.completeness(tenant)
    assert r["total"] == 5
    keys = {i["key"] for i in r["items"]}
    assert keys == {"banner", "hours", "contact", "offer", "legal"}
    assert {i["key"]: i["done"] for i in r["items"]}["hours"] is False
    assert r["percent"] <= 40  # почти ничего не заполнено


@pytest.mark.django_db
def test_completeness_marks_filled_items_done():
    from apps.tenants import onboarding
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(
        address="Hauptstr. 1, Hilden",
        opening_hours="Mo–Fr 9–18",
        site_config={"hero_image": "/m/banner.jpg"},
    )
    done = {i["key"]: i["done"] for i in onboarding.completeness(tenant)["items"]}
    assert done["banner"] and done["hours"] and done["contact"] and done["legal"]
    # offer зависит от каталога (в пустой схеме — нет)
    assert done["offer"] is False


@pytest.mark.django_db
def test_completeness_offer_is_archetype_aware(settings):
    """AB4: пункт «первый товар» говорит на языке архетипа и ведёт в нужный список
    кабинета (отель → номер/stays:units, события → событие/events:list)."""
    from django.urls import reverse

    from apps.tenants import onboarding
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"

    def _offer(root):
        t = TenantFactory.build(disabled_modules=[], site_config={"storefront_root": root})
        return next(i for i in onboarding.completeness(t)["items"] if i["key"] == "offer")

    hotel = _offer("stays")
    assert hotel["url_name"] == "stays:units" and "room" in str(hotel["label"]).lower()
    assert reverse(hotel["url_name"])  # резолвится в urls_tenant → нет NoReverseMatch

    ev = _offer("events")
    assert ev["url_name"] == "events:list" and reverse(ev["url_name"])

    svc = _offer("booking")
    assert svc["url_name"] == "booking:services" and reverse(svc["url_name"])


def test_completeness_offer_safe_for_jobs_primary(settings):
    """W3: у Handwerker (jobs primary, booking выкл) пункт «offer» ведёт в БЕЗОПАСНЫЙ
    список (catalog — core, всегда активен), а НЕ в /dashboard/booking/ (Http404-гейт
    при выключенном booking). jobs — CTA-архетип без «добавь товар»-флоу → generic-фолбэк."""
    from django.urls import reverse

    from apps.core import modules
    from apps.tenants import onboarding
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    t = TenantFactory.build(
        business_type="handwerker",
        disabled_modules=modules.default_disabled_for("handwerker"),
    )
    from apps.core import archetypes

    assert archetypes.primary_module(t) == "jobs"  # jobs primary, не catalog
    offer = next(i for i in onboarding.completeness(t)["items"] if i["key"] == "offer")
    assert offer["url_name"] == "catalog:product-list"  # core → без Http404
    assert reverse(offer["url_name"])
