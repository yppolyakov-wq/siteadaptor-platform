"""AIS-7: «✨ Text vorschlagen» — проверка «никаких новых фактов», факты, эндпоинты.

План — docs/ais-7-texts-from-facts-plan-2026-11-06.md.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache.backends.locmem import LocMemCache
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.core import i18n_translate, ratelimit, tasks, text_draft, text_facts, translate_views
from apps.core.models import Membership
from apps.inbox.ai_facts import Facts
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

GOOD = (
    "Unser Roggenbrot wird jeden Morgen frisch gebacken. Die kräftige Kruste und die "
    "saftige Krume passen zum Frühstück und zum Abendbrot."
)


def _facts(**kw):
    f = Facts(lines=["Item: Roggenbrot", "- Content: 500 g", "- Duration: 60 min"])
    f.name_text = "Roggenbrot"
    f.claims_text = "Roggenbrot"
    for k, v in kw.items():
        setattr(f, k, v)
    return f


def _check(text, facts=None, kind="product", field="description", locale="de"):
    return text_draft.check_draft(
        text, facts=facts or _facts(), kind=kind, field=field, locale=locale
    )


# --- проверка ------------------------------------------------------------------------


def test_guard_accepts_plain_text_from_facts():
    out, code = _check(GOOD)
    assert code == "" and out == GOOD


def test_guard_accepts_numbers_from_facts():
    out, code = _check(GOOD + " Ein Laib wiegt 500 g.")
    assert code == ""


@pytest.mark.parametrize(
    "extra,code",
    [
        (" Heute nur 3,99 €.", "price"),
        (" Jetzt 20 % günstiger.", "percent"),
        (" Großer Rabatt für Stammkunden.", "discount"),
        (" Seit 1987 in Familienhand.", "number"),
        (" Mehr auf www.krume.de lesen.", "link"),
        (" Fragen an info@krume.de schicken.", "link"),
        (" Ganz bio und vegan gebacken.", "claim"),
        (" Das beste Brot der Stadt.", "claim"),
    ],
)
def test_guard_rejects_new_facts(extra, code):
    assert _check(GOOD + extra) == (None, code)


def test_guard_rejects_any_price_even_if_in_facts():
    facts = _facts(lines=["Item: Brot", "- Price: 3,99 €"])
    assert _check(GOOD + " Für 3,99 € zu haben.", facts)[1] == "price"


def test_guard_accepts_vegan_when_diet_set():
    facts = _facts(claims_text="Roggenbrot vegan Vegan")
    assert _check(GOOD + " Das Brot ist vegan.", facts)[1] == ""


def test_guard_rejects_allergen_without_declaration():
    assert _check(GOOD + " Es enthält Sesam.")[1] == "allergen"


def test_guard_length_bounds_per_field():
    assert _check("Zu kurz.")[1] == "length"
    assert _check("x" * 950)[1] == "length"
    assert _check("Frisch aus dem Ofen", kind="hero", field="hero_title")[1] == ""


def test_guard_strips_html_and_keeps_paragraphs():
    out, code = _check("<p>" + GOOD + "</p>\n\n<b>Zweiter</b> Absatz über unser Brot.")
    assert code == "" and "<" not in out and "\n\n" in out


def test_guard_language_mismatch():
    assert _check(GOOD, locale="ru")[1] == "language"


# --- факты -------------------------------------------------------------------------


def test_facts_from_saved_product_exclude_prices():
    product = Product.objects.create(
        name={"de": "Roggenbrot"},
        base_price=Decimal("3.99"),
        ingredients="Roggenmehl, Wasser, Salz",
        allergens=["gluten"],
    )
    facts = text_facts.product_facts(product)
    assert "Roggenbrot" in facts.text and "Roggenmehl" in facts.text
    assert "3,99" not in facts.text and "3.99" not in facts.text
    assert facts.allergens_declared


def test_facts_tenant_about():
    tenant = TenantFactory.build(name="Backhaus Krume", city="Hilden", business_type="bakery")
    facts = text_facts.business_facts(tenant)
    assert "Backhaus Krume" in facts.text and "Hilden" in facts.text


# --- эндпоинты ---------------------------------------------------------------------


@pytest.fixture
def jobs_cache(monkeypatch):
    store = LocMemCache(f"ai-draft-{uuid.uuid4().hex}", {})
    monkeypatch.setattr(text_draft, "cache", store)
    return store


@pytest.fixture
def no_limit(monkeypatch):
    monkeypatch.setattr(ratelimit, "hit", lambda *a, **k: False)
    monkeypatch.setattr(ratelimit, "refund", lambda *a, **k: None)


@pytest.fixture
def owner():
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(username=f"d-{tag}", password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


@pytest.fixture
def ai_on(monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)
    calls = []

    def fake(task, prompt, **kw):
        calls.append((task, prompt))
        return SimpleNamespace(data={"fields": {"description": GOOD}})

    monkeypatch.setattr(api, "generate", fake)
    return calls


@pytest.fixture
def product():
    return Product.objects.create(name={"de": "Roggenbrot"}, base_price=Decimal("3.99"))


def _post(user, *, pk, kind="product", screen="catalog:product-edit", signed=True, extra=None):
    from django.db import connection

    token = i18n_translate.sign_screen(connection.schema_name, screen) if signed else screen
    data = {"screen": token, "kind": kind, "pk": str(pk)}
    data.update(extra or {})
    request = RequestFactory().post("/dashboard/text-vorschlagen/", data)
    request.user = user
    request.tenant = TenantFactory.build(schema_name="public", business_type="bakery")
    return translate_views.text_draft_start(request)


def _get(user, job):
    request = RequestFactory().get(f"/dashboard/text-vorschlagen/{job}/")
    request.user = user
    return translate_views.text_draft_result(request, job)


def _json(resp):
    return json.loads(resp.content)


def _inline():
    return mock.patch.object(
        tasks.text_draft_job, "delay", side_effect=lambda **kw: tasks.text_draft_job(**kw)
    )


def test_start_requires_login():
    request = RequestFactory().post("/dashboard/text-vorschlagen/")
    request.user = AnonymousUser()
    assert translate_views.text_draft_start(request).status_code == 302


def test_start_disabled_returns_code(owner, product):
    assert _json(_post(owner, pk=product.pk)) == {"code": "disabled"}


def test_start_kind_must_match_screen(owner, product, ai_on, jobs_cache, no_limit):
    assert _json(_post(owner, pk=product.pk, kind="service")) == {"code": "forbidden"}
    assert _json(_post(owner, pk=product.pk, signed=False)) == {"code": "forbidden"}
    assert ai_on == []


def test_start_forbidden_without_post_perm(owner, product, ai_on, jobs_cache, monkeypatch):
    from apps.core import view_perms

    monkeypatch.setattr(view_perms, "allowed", lambda user, name, method: False)
    assert _json(_post(owner, pk=product.pk)) == {"code": "forbidden"}


def test_start_unknown_pk_is_gone(owner, ai_on, jobs_cache, no_limit):
    assert _json(_post(owner, pk=uuid.uuid4())) == {"code": "gone"}
    assert _json(_post(owner, pk="junk")) == {"code": "gone"}


def test_round_trip_facts_from_db_not_post_and_nothing_written(
    owner, product, ai_on, jobs_cache, no_limit
):
    with _inline():
        job = _json(
            _post(owner, pk=product.pk, extra={"name_de": "Bio Brot -50 %", "facts": "vegan"})
        )["job"]
    state = _json(_get(owner, job))
    assert state == {"state": "done", "fields": {"description": GOOD}, "rejected": []}
    (_task, prompt) = ai_on[-1]
    assert "Roggenbrot" in prompt and "Bio Brot" not in prompt and "vegan" not in prompt
    assert "3,99" not in prompt
    product.refresh_from_db()
    assert product.description == {}


def test_rejected_field_is_reported(owner, product, ai_on, jobs_cache, no_limit, monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(
        api,
        "generate",
        lambda *a, **k: SimpleNamespace(data={"fields": {"description": GOOD + " Nur 2,99 €!"}}),
    )
    with _inline():
        job = _json(_post(owner, pk=product.pk))["job"]
    assert _json(_get(owner, job)) == {"state": "done", "fields": {}, "rejected": ["description"]}


def test_cache_hit_skips_model(owner, product, ai_on, jobs_cache, no_limit):
    with _inline():
        _post(owner, pk=product.pk)
    calls = len(ai_on)
    assert _json(_post(owner, pk=product.pk))["state"] == "done"
    assert len(ai_on) == calls


def test_busy_and_refund(owner, product, ai_on, jobs_cache, monkeypatch):
    refunds = []
    monkeypatch.setattr(ratelimit, "hit", lambda *a, **k: False)
    monkeypatch.setattr(ratelimit, "refund", lambda scope, ident: refunds.append(scope))
    with mock.patch.object(tasks.text_draft_job, "delay"):
        assert "job" in _json(_post(owner, pk=product.pk))
        assert _json(_post(owner, pk=product.pk)) == {"code": "busy"}
    assert set(refunds) == {"ai-draft-user", "ai-draft"}


def test_result_foreign_job_404(owner, product, ai_on, jobs_cache, no_limit):
    with _inline():
        job = _json(_post(owner, pk=product.pk))["job"]
    other = get_user_model().objects.create_user(username="other-d", password="pw12345678")
    with pytest.raises(Http404):
        _get(other, job)


def test_task_registered_and_described():
    from apps.ai import disclosure, registry

    assert registry.get(text_draft.TASK).tier == "strong"
    assert text_draft.TASK in disclosure.TASK_DATA


# --- кнопка ------------------------------------------------------------------------


def _render_button(user, kind, obj, view_name):
    from django.template import Context, Template

    request = RequestFactory().get("/dashboard/x/")
    request.user = user
    request.resolver_match = SimpleNamespace(view_name=view_name)
    tpl = Template("{% load cabinet %}{% text_draft_button kind obj %}")
    return tpl.render(Context({"request": request, "kind": kind, "obj": obj}))


def test_button_only_with_ai_perm_and_saved_object(owner, product, monkeypatch):
    from apps.ai import api
    from apps.core import view_perms

    assert "data-ai-draft-box" not in _render_button(
        owner, "product", product, "catalog:product-edit"
    )
    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)
    html = _render_button(owner, "product", product, "catalog:product-edit")
    assert "data-ai-draft-box" in html and str(product.pk) in html
    assert "description_de" in html
    unsaved = _render_button(owner, "product", Product(), "catalog:product-edit")
    assert "data-ai-draft-unsaved" in unsaved and "data-ai-draft-box" not in unsaved
    assert "data-ai-draft-box" not in _render_button(
        owner, "service", product, "catalog:product-edit"
    )
    monkeypatch.setattr(view_perms, "allowed", lambda user, name, method: False)
    assert "data-ai-draft-box" not in _render_button(
        owner, "product", product, "catalog:product-edit"
    )


def test_create_screen_only_hints_and_post_is_forbidden(
    owner, product, ai_on, jobs_cache, no_limit
):
    assert _json(_post(owner, pk=product.pk, screen="catalog:product-create")) == {
        "code": "forbidden"
    }
    html = _render_button(owner, "product", Product(), "catalog:product-create")
    assert "data-ai-draft-unsaved" in html


def test_lite_session_rejects_full_cabinet_screen(owner, product, ai_on, jobs_cache, monkeypatch):
    from apps.core import tg_login

    monkeypatch.setattr(tg_login, "is_tg_session", lambda request: True)
    assert "site-home" not in tg_login.TG_LITE_VIEWS
    assert _json(_post(owner, pk="", kind="about", screen="site-home")) == {"code": "forbidden"}


def test_service_variants_reach_facts():
    from apps.booking.models import Service, ServiceVariant

    service = Service.objects.create(name="Haarschnitt", duration_minutes=30)
    ServiceVariant.objects.create(service=service, name="Langhaar")
    ServiceVariant.objects.create(service=service, name="Alt", is_active=False)
    facts = text_facts.service_facts(service)
    assert "Variant: Langhaar" in facts.text and "Alt" not in facts.text


def test_stale_job_does_not_release_current_busy(owner, product, ai_on, jobs_cache, no_limit):
    from django.db import connection

    schema = connection.schema_name
    with mock.patch.object(tasks.text_draft_job, "delay"):
        job = _json(_post(owner, pk=product.pk))["job"]
    text_draft.run_job(schema=schema, user_pk=owner.pk, job="f" * 32)  # чужая/старая задача
    assert jobs_cache.get(text_draft._busy_key(schema, owner.pk)) == job
