"""AIS-2a: фраза владельца → строки «Angebot prüfen» (адаптер поверх setup_plan).

Замки:
* без ИИ работает на правилах; в базу ничего;
* строки состоят только из слов, цен и длительностей фразы (никаких новых фактов);
* категории/акции строками не становятся; вступление до «:» — не позиция;
* выдумка ИИ отбрасывается, ошибка ИИ и лимит → правила (ИИ при лимите не зовётся);
* без прав — пусто; товарные строки подходят любому виду.
"""

import re
import uuid
from types import SimpleNamespace

import pytest

from apps.catalog.models import Product
from apps.core import offer_lines, offer_sentence, ratelimit, setup_assistant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALL = [
    setup_assistant.ENTITY_CATEGORY,
    setup_assistant.ENTITY_PRODUCT,
    setup_assistant.ENTITY_SERVICE,
    setup_assistant.ENTITY_PROMO,
]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    return TenantFactory(business_type="bakery")


@pytest.fixture
def user():
    return SimpleNamespace(pk=uuid.uuid4().int % 10**9)


@pytest.fixture
def allowed(monkeypatch):
    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: ALL)


def _texts(result):
    return [x["t"] for x in result.lines]


def test_rules_sentence_becomes_offer_lines_without_ai(tenant, user, allowed):
    res = offer_sentence.build(tenant, user, "Bäckerei: Brötchen 0,50 €, Brezel 0,80 €")
    assert _texts(res) == ["Brötchen — 0,50 €", "Brezel — 0,80 €"]
    assert Product.objects.count() == 0


def test_lines_parse_back_in_pruefen(tenant, user, allowed):
    res = offer_sentence.build(tenant, user, "Brötchen 0,50 €, Brezel 0,80 €")
    parsed = offer_lines.parse_lines(offer_sentence.lines_for_kind(res.lines, "waren"), "waren")
    assert [(x.name, str(x.price)) for x in parsed.lines] == [
        ("Brötchen", "0.50"),
        ("Brezel", "0.80"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Brötchen 0,50 €, Brezel 0,80 €",
        "Bread 2 €, Croissant 1,20 €",
        "Хлеб 3 €, Пирог 4,50 €",
        "Хліб 3 €, Пиріг 4,50 €",
        "Ekmek 3 €, Simit 1 €",
    ],
)
def test_lines_only_use_words_and_prices_from_the_sentence(tenant, user, allowed, text):
    res = offer_sentence.build(tenant, user, text)
    assert res.lines
    words = set(re.findall(r"\w+", text.lower())) | {"min"}
    for line in _texts(res):
        for w in re.findall(r"\w+", line.lower()):
            assert w in words or w.isdigit() or w == "00", (w, line)


def test_no_price_written_means_line_without_price(tenant, user, allowed):
    res = offer_sentence.build(tenant, user, "Produkt Roggenbrot")
    assert _texts(res) == ["Roggenbrot"]


def test_service_line_carries_written_duration(tenant, user, allowed):
    res = offer_sentence.build(tenant, user, "Leistung Herrenhaarschnitt 25 € 30 min")
    assert res.lines == [{"e": "service", "t": "Herrenhaarschnitt — 25,00 € — 30 min"}]
    parsed = offer_lines.parse_lines(res.lines[0]["t"], "termine")
    (line,) = parsed.lines
    assert line.name == "Herrenhaarschnitt" and str(line.price) == "25.00"


def test_categories_and_promotions_are_not_lines(tenant, user, allowed):
    res = offer_sentence.build(tenant, user, "neue Kategorie Kuchen, Käsekuchen 3,20 €")
    assert _texts(res) == ["Käsekuchen — 3,20 €"]
    assert "später" in str(res.note)


def test_intro_before_colon_is_not_a_name(tenant, user, allowed):
    res = offer_sentence.build(tenant, user, "Unsere kleine Bäckerei: Brezel 0,80 €")
    assert _texts(res) == ["Brezel — 0,80 €"]
    # «Brötchen: 0,50 €» — имя с ценой, не вступление
    res = offer_sentence.build(tenant, user, "Brötchen: 0,50 €")
    assert _texts(res) == ["Brötchen — 0,50 €"]


def test_ai_invented_name_or_price_is_dropped(tenant, user, allowed, monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)
    monkeypatch.setattr(
        api,
        "generate",
        lambda *a, **k: SimpleNamespace(
            data={
                "steps": [
                    {"entity": "product", "name": "Schwarzwälder Torte", "price_text": "9 €"},
                    {"entity": "product", "name": "Brezel", "price_text": "9,99 €"},
                ]
            }
        ),
    )
    res = offer_sentence.build(tenant, user, "Brezel 0,80 €")
    assert _texts(res) == ["Brezel"]


def test_ai_error_falls_back_to_rules(tenant, user, allowed, monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)

    def boom(*a, **k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(api, "generate", boom)
    res = offer_sentence.build(tenant, user, "Brezel 0,80 €")
    assert _texts(res) == ["Brezel — 0,80 €"]


def test_rate_limited_uses_rules_without_calling_ai(tenant, user, allowed, monkeypatch):
    from apps.ai import api

    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)
    called = []
    monkeypatch.setattr(api, "generate", lambda *a, **k: called.append(1))
    monkeypatch.setattr(ratelimit, "hit", lambda *a, **k: True)
    res = offer_sentence.build(tenant, user, "Brezel 0,80 €")
    assert _texts(res) == ["Brezel — 0,80 €"] and called == []


def test_user_without_sortiment_rights_gets_no_lines(tenant, user, monkeypatch):
    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: [])
    res = offer_sentence.build(tenant, user, "Brezel 0,80 €")
    assert res.lines == [] and res.note


def test_nothing_recognised_has_a_note(tenant, user, allowed):
    res = offer_sentence.build(tenant, user, "neue Kategorie Kuchen")
    assert res.lines == [] and "Keine Angebote" in str(res.note)


def test_product_lines_join_any_paid_kind():
    lines = [
        {"e": "product", "t": "Herrenhaarschnitt — 25,00 €"},
        {"e": "service", "t": "Färben — 60,00 € — 90 min"},
        {"e": "room", "t": "Doppelzimmer — 90,00 €"},
    ]
    assert offer_sentence.lines_for_kind(lines, "termine").splitlines() == [
        "Herrenhaarschnitt — 25,00 €",
        "Färben — 60,00 € — 90 min",
    ]
    assert offer_sentence.lines_for_kind(lines, "zimmer").splitlines() == [
        "Herrenhaarschnitt — 25,00 €",
        "Doppelzimmer — 90,00 €",
    ]
    assert offer_sentence.lines_for_kind(lines, "nope") == ""


def test_clean_lines_drops_garbage():
    raw = [{"e": "category", "t": "x"}, {"e": "product", "t": " A "}, "junk", {"e": "room"}]
    assert offer_sentence.clean_lines(raw) == [{"e": "product", "t": "A"}]
    assert offer_sentence.clean_lines("junk") == []
