"""STU-19c: "Was möchten Sie anlegen?" — the setup helper.

Locks:
* the rules planner understands the owner's phrase (entity, name, price, parent);
* every field the plan names exists on the real form (no invented fields);
* the AI answer is post-checked: unknown entity dropped, names only from the owner's
  words, a price only when it literally occurs in the phrase, empty AI → rules;
* only entities the user may create are offered; nothing is ever written;
* the prefilled link really prefills the create form (GET only).
"""

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.core import setup_assistant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    return TenantFactory(business_type="bakery")


ALL = [setup_assistant.ENTITY_CATEGORY, setup_assistant.ENTITY_PRODUCT]


def _rules(text, tenant, allowed=ALL):
    return setup_assistant.plan_from_rules(text, tenant, allowed)


def _field(step, name):
    return next(f for f in step.fields if f.name == name)


def test_category_and_product_from_one_phrase(tenant):
    plan = _rules("neue Kategorie Kuchen mit Fotos, Käsekuchen 3,20 €", tenant)
    assert [s.entity for s in plan.steps] == ["category", "product"]
    cat, prod = plan.steps
    assert _field(cat, "name_de").value == "Kuchen"
    assert _field(prod, "name_de").value == "Käsekuchen"
    assert _field(prod, "base_price").value == "3,20"
    assert _field(prod, "category").value == "Kuchen"
    assert "category_name=Kuchen" in prod.form_url
    assert cat.template is not None and cat.template.value == "kopfbild"
    assert "page_style=kopfbild" in cat.form_url


def test_missing_required_fields_are_flagged(tenant):
    (step,) = _rules("Produkt Roggenbrot", tenant).steps
    assert _field(step, "name_de").status == "found"
    assert _field(step, "base_price").status == "missing"


@pytest.mark.parametrize(
    "text,entity",
    [
        ("create category Bread", "category"),
        ("создай категорию Торты", "category"),
        ("yeni kategori Pasta", "category"),
        ("Produkt „Dinkel Spezial“ 4,50 €", "product"),
    ],
)
def test_keywords_in_cabinet_languages(tenant, text, entity):
    plan = _rules(text, tenant)
    assert plan.steps and plan.steps[0].entity == entity


def test_quoted_name_is_kept_whole(tenant):
    (step,) = _rules("Produkt „Dinkel Spezial“ 4,50 €", tenant).steps
    assert _field(step, "name_de").value == "Dinkel Spezial"


def test_entity_fields_exist_on_forms(tenant):
    """The plan must never name a field the real form does not have."""
    from apps.catalog.forms import CategoryForm, ProductForm

    forms = {"category": CategoryForm, "product": ProductForm}
    for entity, spec in setup_assistant.ENTITIES.items():
        if entity not in forms:  # STU-19g entities: test_stu19g_setup_v2
            continue
        names = set(forms[entity](tenant=tenant).fields)
        for fname, _label, _req in spec["fields"]:
            assert fname in names, (entity, fname)


def test_only_allowed_entities(tenant):
    plan = _rules("neue Kategorie Kuchen, Käsekuchen 3,20 €", tenant, ["product"])
    assert [s.entity for s in plan.steps] == ["product"]


def test_nothing_is_written(tenant):
    before = (Category.objects.count(), Product.objects.count(), dict(tenant.site_config or {}))
    _rules("neue Kategorie Kuchen, Käsekuchen 3,20 €", tenant)
    tenant.refresh_from_db()
    assert (Category.objects.count(), Product.objects.count(), tenant.site_config or {}) == before


# ── AI post-check ───────────────────────────────────────────────────────────────

TEXT = "neue Kategorie Kuchen, Käsekuchen 3,20 €"


def _ai(data, tenant, text=TEXT):
    return setup_assistant._from_ai(data, text, tenant, ALL)


def test_ai_invented_names_are_dropped(tenant):
    plan = _ai({"steps": [{"entity": "product", "name": "Schwarzwälder Torte"}]}, tenant)
    assert plan.steps == ()


def test_ai_price_only_from_the_phrase(tenant):
    plan = _ai(
        {"steps": [{"entity": "product", "name": "Käsekuchen", "price_text": "9,99 €"}]}, tenant
    )
    assert _field(plan.steps[0], "base_price").value == ""
    plan = _ai(
        {"steps": [{"entity": "product", "name": "Käsekuchen", "price_text": "3,20 €"}]}, tenant
    )
    assert _field(plan.steps[0], "base_price").value == "3,20"


@pytest.mark.parametrize("fragment", ["20", "3", "0,20 €"])
def test_ai_price_substring_is_rejected(tenant, fragment):
    """'20' occurs in '3,20 €' as text, but it is not a price the owner wrote."""
    plan = _ai(
        {"steps": [{"entity": "product", "name": "Käsekuchen", "price_text": fragment}]}, tenant
    )
    assert _field(plan.steps[0], "base_price").value == ""


def test_build_plan_survives_unexpected_ai_error(tenant, monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: ALL)
    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)

    def boom(*a, **k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(api, "generate", boom)
    plan = setup_assistant.build_plan(TEXT, tenant, SimpleNamespace(pk=1))
    assert plan.source == "rules" and len(plan.steps) == 2


def test_ai_unknown_entity_is_dropped(tenant):
    plan = _ai({"steps": [{"entity": "promotion", "name": "Kuchen"}]}, tenant)
    assert plan.steps == ()


def test_build_plan_falls_back_to_rules_when_ai_is_off(tenant, monkeypatch):
    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: ALL)
    plan = setup_assistant.build_plan(TEXT, tenant, SimpleNamespace(pk=1))
    assert plan.source == "rules" and len(plan.steps) == 2


def test_build_plan_uses_ai_and_keeps_rules_on_empty_answer(tenant, monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: ALL)
    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)

    def fake(task, prompt, **kw):
        assert task == "setup_plan" and "Kuchen" in prompt
        return SimpleNamespace(data={"steps": [{"entity": "category", "name": "Kuchen"}]})

    monkeypatch.setattr(api, "generate", fake)
    plan = setup_assistant.build_plan(TEXT, tenant, SimpleNamespace(pk=1))
    assert plan.source == "ai" and [s.entity for s in plan.steps] == ["category"]

    monkeypatch.setattr(api, "generate", lambda *a, **k: SimpleNamespace(data={"steps": []}))
    assert setup_assistant.build_plan(TEXT, tenant, SimpleNamespace(pk=1)).source == "rules"


def test_no_permission_no_plan(tenant, monkeypatch):
    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: [])
    plan = setup_assistant.build_plan(TEXT, tenant, SimpleNamespace(pk=1))
    assert plan.steps == () and plan.note


def test_task_is_registered_and_disclosed():
    from apps.ai import disclosure, registry

    assert registry.get("setup_plan").tier == "fast"
    assert "setup_plan" in disclosure.TASK_DATA


# ── screens ──────────────────────────────────────────────────────────────────────


def _req(tenant, path, data=None):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return request


def test_tab_shows_plan_card(tenant, monkeypatch):
    # FB-16: the helper lives on its own screen (the Sortiment tab is gone)
    from apps.core import lite_cabinet

    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: ALL)
    body = lite_cabinet.setup_ask(
        _req(tenant, "/dashboard/anlegen/", {"frage": TEXT})
    ).content.decode()
    assert "Käsekuchen" in body and "catalog/products/new/" in body
    assert 'name="frage"' in body


def test_create_form_is_prefilled_from_link(tenant):
    from apps.catalog import views as catalog_views

    Category.objects.create(name={"de": "Kuchen"}, slug="kuchen", is_active=True)
    body = catalog_views.product_create(
        _req(
            tenant,
            "/catalog/products/new/",
            {"name_de": "Käsekuchen", "base_price": "3,20", "category_name": "Kuchen"},
        )
    ).content.decode()
    assert 'value="Käsekuchen"' in body
    assert 'value="3,20"' in body
    kuchen = Category.objects.get(slug="kuchen")
    assert f'value="{kuchen.pk}" selected' in body


@pytest.mark.parametrize("allowed", [True, False])
def test_sortiment_bar_needs_website_right(tenant, monkeypatch, allowed):
    """The bar submits to a website.view screen — without that right it must not show."""
    from apps.core import views

    monkeypatch.setattr(views, "has_perm", lambda user, key: allowed)
    body = views.sellable_manage(_req(tenant, "/dashboard/angebote/")).content.decode()
    assert ('name="frage"' in body) is allowed
