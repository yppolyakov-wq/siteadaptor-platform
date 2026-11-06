"""AIS-3 «Was haben Sie schon?» — первый шаг мастера v4 (план docs/ais-3-quelle-plan-2026-11-06.md).

Замки среза 1: шаг первым у v4, у v3 его нет; выбор хранится presence-minimal и переживает
нормализацию; «none» побеждает; карточек без ключа нет; POST не пишет бизнес-данные.
"""

import pytest

from apps.tenants import onboarding
from apps.tenants.tests.factories import TenantFactory
from apps.tenants.tests.test_wizard_v4_pruefen import V4, Owner

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _v4(**kw):
    kw.setdefault("schema_name", "public")
    kw.setdefault("slug", "q4")
    kw.setdefault("business_type", "bakery")
    kw.setdefault("site_config", dict(V4))
    return TenantFactory(published_at=None, **kw)


def test_v4_starts_with_quelle_and_v3_does_not_have_it():
    v4 = TenantFactory.build(business_type="bakery", site_config=dict(V4), published_at=None)
    assert onboarding.visible_keys(v4)[0] == "quelle"
    v3 = TenantFactory.build(business_type="bakery")
    assert "quelle" not in onboarding.visible_keys(v3)


def test_choice_is_stored_clean_and_none_wins():
    assert onboarding.clean_had(["google", "x", "website"]) == ["website", "google"]
    assert onboarding.clean_had(["google", "none"]) == ["none"]
    tenant = _v4()
    onboarding.set_had(tenant, ["google", "evil"])
    assert tenant.site_config["onboarding"]["had"] == ["google"]
    onboarding.set_had(tenant, [])
    assert "had" not in tenant.site_config["onboarding"]


def test_choice_survives_state_normalization():
    t = TenantFactory.build(site_config={"onboarding": {"v": 2, "flow": "v4", "had": ["photo", 1]}})
    assert onboarding.get_state(t).get("had") == ["photo"]


def test_post_writes_only_the_choice(monkeypatch):
    from apps.catalog.models import Product
    from apps.core import offer_photo, setup_google

    monkeypatch.setattr(setup_google, "enabled", lambda t: True)
    monkeypatch.setattr(offer_photo, "enabled", lambda: True)
    tenant = _v4()
    onboarding.goto(tenant, "quelle")
    before = (tenant.name, tenant.address, tenant.city)
    owner = Owner(tenant)
    owner("post", {"had": ["website", "google", "photo"]})
    tenant.refresh_from_db()
    assert onboarding.had(tenant) == ["website", "google", "photo"]
    assert (tenant.name, tenant.address, tenant.city) == before
    assert Product.objects.count() == 0
    assert onboarding.get_state(tenant)["step"] == "company"  # «Weiter» ведёт дальше


def test_options_without_keys_are_not_rendered_and_not_accepted(monkeypatch):
    from apps.core import offer_photo, setup_google

    monkeypatch.setattr(setup_google, "enabled", lambda t: False)
    monkeypatch.setattr(offer_photo, "enabled", lambda: False)
    tenant = _v4()
    onboarding.goto(tenant, "quelle")
    owner = Owner(tenant)
    html = owner().content.decode()
    assert 'data-quelle-option="website"' in html and 'data-quelle-option="none"' in html
    assert 'data-quelle-option="google"' not in html and 'data-quelle-option="photo"' not in html
    owner("post", {"had": ["google", "photo", "website"]})
    tenant.refresh_from_db()
    assert onboarding.had(tenant) == ["website"]


def test_skip_marks_the_step_skipped():
    tenant = _v4()
    onboarding.goto(tenant, "quelle")
    Owner(tenant)("post", {"action": "skip"})
    tenant.refresh_from_db()
    state = onboarding.get_state(tenant)
    assert "quelle" in state["skipped"] and state["step"] == "company"


# --- срез 2: передача выбора в следующие шаги ---------------------------------------------


def _offer_text(response) -> str:
    import re

    m = re.search(
        r'<textarea id="id_pruefen_text"[^>]*>(.*?)</textarea>', response.content.decode(), re.S
    )
    return m.group(1) if m else ""


def test_none_prefills_examples_without_creating_anything():
    from apps.catalog.models import Product

    tenant = _v4()
    onboarding.set_had(tenant, ["none"])
    onboarding.goto(tenant, "pruefen")
    assert "Roggenbrot" in _offer_text(Owner(tenant)()) and Product.objects.count() == 0


def test_without_none_the_offer_field_stays_empty():
    tenant = _v4()
    onboarding.goto(tenant, "pruefen")
    assert _offer_text(Owner(tenant)()).strip() == ""


def test_google_choice_shows_hint_and_calls_nothing(monkeypatch):
    from apps.core import setup_google
    from apps.tenants import google_places

    monkeypatch.setattr(setup_google, "enabled", lambda t: True)
    monkeypatch.setattr(google_places, "search_places", lambda *a, **k: pytest.fail("API"))
    tenant = _v4()
    onboarding.set_had(tenant, ["google"])
    onboarding.goto(tenant, "company")
    html = Owner(tenant)().content.decode()
    assert 'data-quelle-hint="google"' in html


def test_photo_choice_shows_hint_on_offer_step(monkeypatch):
    from apps.core import offer_photo

    monkeypatch.setattr(offer_photo, "enabled", lambda: True)
    tenant = _v4()
    onboarding.set_had(tenant, ["photo"])
    onboarding.goto(tenant, "pruefen")
    html = Owner(tenant)().content.decode()
    assert 'data-quelle-hint="photo"' in html
