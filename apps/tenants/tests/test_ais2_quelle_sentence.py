"""AIS-2b/2c: фраза «Beschreiben Sie Ihr Geschäft in einem Satz» в шаге quelle → строки
шага «Angebot prüfen» (план docs/ais-2-sentence-plan-2026-11-06.md).

Замки: поле только у v4 и с пометкой ИИ; POST хранит фразу и строки, в базу ничего; пустая
фраза ключи убирает; нормализация чистит мусор; устаревший save не стирает; забытое
согласие сайта фразу не теряет; неизменённая фраза ИИ не зовёт; фраза сама по себе
закрывает шаг; в «Prüfen» черновик сильнее фразы, фраза сильнее образцов, после первого
предложения — не подставляется.
"""

import pytest

from apps.catalog.models import Product
from apps.core import offer_sentence
from apps.tenants import onboarding
from apps.tenants.tests.factories import TenantFactory
from apps.tenants.tests.test_ais3_quelle import _offer_text, _quelle_owner, _v4
from apps.tenants.tests.test_wizard_v4_pruefen import V4, Owner

pytestmark = pytest.mark.django_db

SENTENCE = "Bäckerei: Brötchen 0,50 €, Brezel 0,80 €"


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _field(html: str) -> bool:
    return 'name="sentence"' in html


def test_field_rendered_with_label_hint_and_ai_notice(monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)
    _tenant, owner = _quelle_owner()
    html = owner().content.decode()
    assert _field(html) and 'for="id_sentence"' in html
    assert 'aria-describedby="sentence-hint"' in html and 'maxlength="400"' in html
    assert "data-quelle-sentence" in html


def test_v3_has_no_sentence_field():
    tenant = TenantFactory(schema_name="public", slug="q3s", business_type="bakery")
    assert "quelle" not in onboarding.visible_keys(tenant)


def test_post_stores_sentence_and_lines_creates_nothing():
    tenant, owner = _quelle_owner()
    owner("post", {"sentence": SENTENCE})
    tenant.refresh_from_db()
    assert onboarding.sentence(tenant) == SENTENCE
    assert [x["t"] for x in onboarding.sentence_lines(tenant)] == [
        "Brötchen — 0,50 €",
        "Brezel — 0,80 €",
    ]
    assert Product.objects.count() == 0
    assert onboarding.get_state(tenant)["step"] == "company"


def test_empty_sentence_removes_keys():
    tenant, owner = _quelle_owner()
    owner("post", {"sentence": SENTENCE})
    onboarding.goto(tenant, "quelle")
    owner("post", {"sentence": "  "})
    tenant.refresh_from_db()
    state = tenant.site_config["onboarding"]
    assert "sentence" not in state and "sentence_lines" not in state


def test_post_without_field_keeps_sentence():
    tenant, owner = _quelle_owner()
    onboarding.set_sentence(tenant, SENTENCE, [{"e": "product", "t": "Brezel — 0,80 €"}])
    owner("post", {"had": ["none"]})
    tenant.refresh_from_db()
    assert onboarding.sentence(tenant) == SENTENCE


def test_sentence_survives_state_normalization_garbage_dropped():
    t = TenantFactory.build(
        site_config={
            "onboarding": {
                "v": 2,
                "flow": "v4",
                "sentence": "x" * 900,
                "sentence_lines": [{"e": "product", "t": "A"}, {"e": "evil", "t": "B"}, 5],
            }
        }
    )
    state = onboarding.get_state(t)
    assert len(state["sentence"]) == onboarding.SENTENCE_MAX
    assert state["sentence_lines"] == [{"e": "product", "t": "A"}]
    bad = TenantFactory.build(site_config={"onboarding": {"v": 2, "sentence": 7}})
    assert "sentence" not in onboarding.get_state(bad)


def test_stale_tenant_save_does_not_wipe_sentence():
    from apps.tenants.models import Tenant

    tenant = _v4()
    stale = Tenant.objects.get(pk=tenant.pk)
    onboarding.set_sentence(tenant, SENTENCE, [{"e": "product", "t": "Brezel — 0,80 €"}])
    onboarding.goto(stale, "company")
    fresh = Tenant.objects.get(pk=tenant.pk)
    assert onboarding.sentence(fresh) == SENTENCE
    assert onboarding.sentence_lines(fresh) == [{"e": "product", "t": "Brezel — 0,80 €"}]


def test_sentence_kept_when_website_consent_missing(monkeypatch):
    from apps.imports.site import service

    monkeypatch.setattr(service, "start_run", lambda **k: pytest.fail("no consent"))
    tenant, owner = _quelle_owner()
    owner("post", {"had": ["website"], "site_url": "https://k.example", "sentence": SENTENCE})
    tenant.refresh_from_db()
    assert onboarding.get_state(tenant)["step"] == "quelle"
    assert onboarding.sentence(tenant) == SENTENCE


def test_unchanged_sentence_does_not_call_planner_again(monkeypatch):
    tenant, owner = _quelle_owner()
    owner("post", {"sentence": SENTENCE})
    onboarding.goto(tenant, "quelle")
    monkeypatch.setattr(offer_sentence, "build", lambda *a, **k: pytest.fail("planner again"))
    owner("post", {"sentence": SENTENCE})
    tenant.refresh_from_db()
    assert onboarding.get_state(tenant)["step"] == "company"


def test_unchanged_sentence_with_empty_result_is_retried(monkeypatch):
    tenant, owner = _quelle_owner()
    onboarding.set_sentence(tenant, SENTENCE, [])  # прошлый раз: лимит или сбой ИИ
    owner("post", {"sentence": SENTENCE})
    tenant.refresh_from_db()
    assert onboarding.sentence_lines(tenant)


@pytest.mark.parametrize("action", ["back", "skip"])
def test_back_and_skip_do_not_run_the_planner(monkeypatch, action):
    monkeypatch.setattr(offer_sentence, "build", lambda *a, **k: pytest.fail("planner"))
    tenant, owner = _quelle_owner()
    owner("post", {"sentence": SENTENCE, "action": action})
    tenant.refresh_from_db()
    assert onboarding.sentence(tenant) == ""


def test_sentence_alone_marks_quelle_done():
    tenant = _v4()
    assert not onboarding._check_quelle(tenant)
    onboarding.set_sentence(tenant, SENTENCE, [])
    assert onboarding._check_quelle(tenant)


def test_typed_sentence_shown_again():
    tenant, owner = _quelle_owner()
    owner("post", {"sentence": SENTENCE})
    onboarding.goto(tenant, "quelle")
    assert "Brezel 0,80 €" in owner().content.decode()


# --- 2c: подхват в «Angebot prüfen» --------------------------------------------------


def _with_sentence(**kw):
    tenant = _v4(**kw)
    onboarding.set_sentence(
        tenant,
        SENTENCE,
        [{"e": "product", "t": "Brötchen — 0,50 €"}, {"e": "product", "t": "Brezel — 0,80 €"}],
    )
    onboarding.goto(tenant, "pruefen")
    return tenant


def test_pruefen_prefills_sentence_lines_for_kind():
    tenant = _with_sentence()
    response = Owner(tenant)()
    assert _offer_text(response).splitlines() == ["Brötchen — 0,50 €", "Brezel — 0,80 €"]
    assert "data-pruefen-from-sentence" in response.content.decode()
    assert Product.objects.count() == 0


def test_sentence_beats_none_examples():
    tenant = _with_sentence()
    onboarding.set_had(tenant, ["none"])
    text = _offer_text(Owner(tenant)())
    assert "Brezel" in text and "Roggenbrot" not in text


def test_draft_text_beats_sentence():
    from apps.core import offer_batch

    tenant = _with_sentence()
    owner = Owner(tenant)
    owner()
    owner.session[offer_batch.SESSION_KEY] = {"kind": "waren", "text": "Mein Kuchen — 3 €"}
    html = owner().content.decode()
    assert "Mein Kuchen" in html and "data-pruefen-from-sentence" not in html


def test_no_prefill_once_offer_exists(monkeypatch):
    from apps.core import setup_steps

    tenant = _with_sentence()
    monkeypatch.setattr(setup_steps, "_offer_items", lambda t: [{"name": "Schon da", "url": "/"}])
    assert _offer_text(Owner(tenant)()).strip() == ""


def test_v4_constant_is_shared():
    assert V4["onboarding"]["flow"] == "v4"
