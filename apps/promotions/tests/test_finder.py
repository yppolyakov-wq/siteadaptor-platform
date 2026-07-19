"""FD-1: Finder «вопросы → 3 предложения» (план fd1-finder-plan-2026-07-18).

Движок — apps.core.finder (скоринг words/price по активным сущностям primary-
модуля); страница /finder/ — серверные шаги без JS; конфиг — site_config["finder"]
(presence-minimal в normalize). Finder — ОПЦИЯ: 404 пока не включён."""

from decimal import Decimal

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.core import finder
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _bakery(**kw):
    from apps.core import modules

    return TenantFactory(
        business_type="bakery",
        disabled_modules=modules.default_disabled_for("bakery"),  # primary = catalog
        **kw,
    )


def _product(name, price, active=True):
    return Product.objects.create(name={"de": name}, base_price=Decimal(price), is_active=active)


def _get(path="/finder/", a=""):
    request = RequestFactory().get(path, {"a": a} if a else {})
    return request


# --- конфиг / normalize -----------------------------------------------------------


def test_normalize_finder_presence_minimal():
    """Пустой/мусорный finder → ключ НЕ материализуется (golden-паритет)."""
    assert "finder" not in siteconfig.normalize({})
    assert "finder" not in siteconfig.normalize({"finder": {}})
    assert "finder" not in siteconfig.normalize({"finder": {"enabled": False, "questions": []}})
    out = siteconfig.normalize({"finder": {"enabled": True}})
    assert out["finder"] == {"enabled": True}


def test_normalize_finder_cleans_questions():
    raw = {
        "enabled": True,
        "questions": [
            {
                "key": "anlass",
                "label": "Was?",
                "chips": [
                    {"key": "a", "label": "A", "match": {"words": ["torte", ""], "junk": 1}},
                    {"key": "", "label": "drop"},  # без key — отброшен
                ],
            },
            "junk",
        ],
    }
    fnd = siteconfig.normalize_finder(raw)
    assert fnd["enabled"] is True
    assert len(fnd["questions"]) == 1
    chip = fnd["questions"][0]["chips"][0]
    assert chip["match"] == {"words": ["torte"]}  # junk-ключи и пустые слова отброшены


# --- движок -----------------------------------------------------------------------


def test_resolve_asks_questions_then_scores():
    tenant = _bakery()
    torte = _product("Schokotorte", "24.00")
    _product("Roggenbrot", "4.20")
    _product("Brezel", "1.10")

    # Без ответов → первый вопрос дерева пекарни.
    state = finder.resolve(tenant, {})
    assert state["question"]["key"] == "anlass" and state["step"] == 1

    # Ответы «день рождения + бюджет неважен» → торт побеждает и стоит В СЕРЕДИНЕ.
    state = finder.resolve(tenant, {"anlass": "geburtstag", "budget": "egal"})
    assert "results" in state and state["results"]
    picks = [r for r in state["results"] if r["pick"]]
    assert len(picks) == 1 and picks[0]["obj"].pk == torte.pk
    if len(state["results"]) == 3:
        assert state["results"][1]["pick"]  # лучший — посередине
    assert state["fallback"] is False


def test_resolve_price_filter_and_fallback():
    tenant = _bakery()
    _product("Hochzeitstorte", "89.00")
    _product("Brot", "4.00")

    # Бюджет до 10 € отфильтровывает торт (жёсткий фильтр).
    state = finder.resolve(tenant, {"anlass": "geburtstag", "budget": "klein"})
    names = [r["fields"]["name"] for r in state["results"]]
    assert "Hochzeitstorte" not in names
    # Совпадений по словам нет (Brot ≠ torte/kuchen) → честный fallback-флаг.
    assert state["fallback"] is True


def test_resolve_ignores_inactive():
    tenant = _bakery()
    _product("Torte alt", "20.00", active=False)
    fresh = _product("Torte neu", "22.00")
    state = finder.resolve(tenant, {"anlass": "geburtstag", "budget": "egal"})
    pks = {r["obj"].pk for r in state["results"]}
    assert fresh.pk in pks and len(pks) == len(state["results"])


def test_custom_tree_overrides_preset():
    tenant = _bakery(
        site_config={
            "finder": {
                "enabled": True,
                "questions": [
                    {
                        "key": "q1",
                        "label": "Custom?",
                        "chips": [{"key": "x", "label": "X", "match": {}}],
                    }
                ],
            }
        }
    )
    assert finder.tree_for(tenant)[0]["key"] == "q1"
    assert finder.resolve(tenant, {})["question"]["label"] == "Custom?"


# --- страница ---------------------------------------------------------------------


def test_page_404_until_enabled():
    tenant = _bakery()
    request = _get()
    request.tenant = tenant
    with pytest.raises(Http404):
        public_views.finder_page(request)


def test_page_steps_and_results_flow():
    tenant = _bakery(site_config={"finder": {"enabled": True}})
    torte = _product("Schokotorte", "24.00")
    _product("Brot", "4.00")

    request = _get()
    request.tenant = tenant
    html = public_views.finder_page(request).content.decode()
    assert "Frage 1 von" in html and "?a=anlass.geburtstag" in html

    request = _get(a="anlass.geburtstag")
    request.tenant = tenant
    html = public_views.finder_page(request).content.decode()
    assert "Frage 2 von" in html and "?a=anlass.geburtstag,budget.egal" in html

    request = _get(a="anlass.geburtstag,budget.egal")
    request.tenant = tenant
    html = public_views.finder_page(request).content.decode()
    assert "Unser Vorschlag" in html and "Schokotorte" in html
    assert "Noch mal suchen" in html
    assert f"/sortiment/{torte.pk}/" in html  # карточка ведёт на деталь


def test_page_garbage_answers_restart_question():
    """Мусор в ?a= не роняет страницу — неотвеченные вопросы задаются заново."""
    tenant = _bakery(site_config={"finder": {"enabled": True}})
    request = _get(a="nope.nope,,broken")
    request.tenant = tenant
    assert "Frage 1 von" in public_views.finder_page(request).content.decode()


# --- FD-3-lite: кабинет (тумблер + превью дерева) ---------------------------------


def _cab_req(method="get", data=None, tenant=None):
    from uuid import uuid4

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    request = getattr(RequestFactory(), method)("/dashboard/finder/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    o = uuid4().hex[:8]
    from django.contrib.auth import get_user_model as gum

    request.user = gum().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    return request


def test_cabinet_toggle_enables_and_disables():
    from apps.core import views as core_views

    tenant = _bakery(schema_name="public", slug="fnd", name="Fnd")
    # Включаем: POST с enabled → страница /finder/ оживает.
    resp = core_views.finder_settings(_cab_req("post", {"enabled": "1"}, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert finder.enabled(tenant) is True
    # Выключаем: POST без enabled → ключ finder исчезает целиком (presence-minimal).
    core_views.finder_settings(_cab_req("post", {}, tenant))
    tenant.refresh_from_db()
    assert finder.enabled(tenant) is False
    assert "finder" not in tenant.site_config


def test_cabinet_toggle_preserves_custom_questions():
    from apps.core import views as core_views

    tenant = _bakery(
        schema_name="public",
        slug="fndq",
        name="FndQ",
        site_config={
            "finder": {
                "questions": [
                    {"key": "q1", "label": "Custom?", "chips": [{"key": "x", "label": "X"}]}
                ]
            }
        },
    )
    core_views.finder_settings(_cab_req("post", {"enabled": "1"}, tenant))
    tenant.refresh_from_db()
    assert finder.enabled(tenant) is True
    assert tenant.site_config["finder"]["questions"][0]["key"] == "q1"  # кастом цел


def test_cabinet_page_renders_tree_preview():
    from apps.core import views as core_views

    tenant = _bakery(schema_name="public", slug="fndr", name="FndR")
    html = core_views.finder_settings(_cab_req(tenant=tenant)).content.decode()
    assert 'name="enabled"' in html
    assert "Was suchst du?" in html  # превью пресета пекарни
