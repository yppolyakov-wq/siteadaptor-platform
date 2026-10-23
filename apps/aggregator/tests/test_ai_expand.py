"""T-8.34d: ИИ-подстраховка поиска — замки плана docs/t8-34d-ai-query-expand-plan-2026-10-23.md.

Главное: словарь первым (ИИ не зовётся, если мост знает слово), модель отдаёт только
проверенные немецкие слова, карточки — из базы тем же пулом, в кэше нет текста запроса,
при выключенной задаче путь прежний."""

import uuid
from types import SimpleNamespace

import pytest
from django.core import signing
from django.core.cache.backends.locmem import LocMemCache

from apps.aggregator import ai_expand, ai_search
from apps.aggregator.tests.test_follow_query import CITY, _listing, _req, _tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def x_cache(monkeypatch):
    store = LocMemCache(f"ai-expand-test-{uuid.uuid4()}", {})
    monkeypatch.setattr(ai_expand, "cache", store)
    monkeypatch.setattr(ai_search, "cache", store)
    return store


@pytest.fixture
def x_on(settings, x_cache, isolated_ratelimit):
    settings.AI_ENABLED = True
    settings.AI_SEARCH_ENABLED = True
    settings.AI_TASKS_ENABLED = [ai_expand.TASK]  # подсказка фильтров D-2 выключена
    return settings


def _payload(q="пахлава", lang="ru", **kw):
    data = {
        "s": "entdecken",
        "h": "",
        "p": "/entdecken/",
        "pd": "",
        "q": q,
        "r": q,
        "c": CITY,
        "l": lang,
        "g": [("q", q), ("city", CITY)],
        "sg": 0,
        "x": 1,
    }
    data.update(kw)
    return data


def _token(payload):
    return signing.dumps(payload, salt=ai_search.TOKEN_SALT, compress=True)


def _get(payload):
    return ai_search.fragment(_req("get", "/x/", {"t": _token(payload)}), portal=None)


# --- проверка ответа ---------------------------------------------------------------------


def test_clean_terms_keeps_only_safe_german_words():
    data = {
        "terms": [
            "Gebäck",
            "kuchen",
            "kuchen",
            "12 euro",
            "https://x.de",
            "essen",
            "solingen",
            "torte",
            "süßwaren",
            "plätzchen",
        ]
    }
    assert ai_expand.clean_terms(data, q="пахлава") == [
        "gebäck",
        "kuchen",
        "torte",
        "süßwaren",
        "plätzchen",
    ]


@pytest.mark.parametrize("data", [None, "x", {}, {"terms": "kuchen"}, {"terms": [1, None]}])
def test_clean_terms_garbage_is_empty(data):
    assert ai_expand.clean_terms(data, q="x") == []


def test_clean_terms_drops_words_of_the_query_itself():
    assert ai_expand.clean_terms({"terms": ["pizza", "teig"]}, q="pizza") == ["teig"]


# --- когда зовём ИИ -----------------------------------------------------------------------


def test_dictionary_first_and_never_for_german():
    assert not ai_expand.needs_expansion("сладости", lang="ru")  # мост знает
    assert ai_expand.needs_expansion("пахлава", lang="ru")
    assert not ai_expand.needs_expansion("выпечка", lang="ru")  # «выпечк» есть в мосте
    assert ai_expand.needs_expansion("baklava", lang="tr")
    assert not ai_expand.needs_expansion("gebäck", lang="de")
    assert not ai_expand.needs_expansion("", lang="ru")


def test_cache_key_has_no_plaintext_and_normalises():
    key = ai_expand.cache_key("Пахлава  ", "ru")
    assert "пахлава" not in key.lower()
    assert key == ai_expand.cache_key("пахлава", "ru")
    assert key != ai_expand.cache_key("пахлава", "uk")


def test_slot_carries_expand_flag_only_when_needed(x_on):
    x_on.ROOT_URLCONF = "config.urls_public"
    req = _req("get", "/entdecken/", {"q": "пахлава", "city": CITY})
    slot = ai_search.slot_context(
        req,
        surface="entdecken",
        q="пахлава",
        q_eff="пахлава",
        city=CITY,
        lang="ru",
        results=0,
        fuzzy=True,
    )
    payload = signing.loads(slot["url"].split("?t=", 1)[1], salt=ai_search.TOKEN_SALT)
    assert payload["x"] == 1 and payload["sg"] == 0
    for q, lang in (("сладости", "ru"), ("gebäck", "de"), ("ruf mich an 0171 1234567", "ru")):
        req = _req("get", "/entdecken/", {"q": q, "city": CITY})
        assert (
            ai_search.slot_context(
                req,
                surface="entdecken",
                q=q,
                q_eff=q,
                city=CITY,
                lang=lang,
                results=0,
                fuzzy=True,
            )
            is None
        ), q


def test_off_when_task_not_enabled(settings, x_cache, isolated_ratelimit):
    settings.AI_ENABLED = True
    settings.AI_SEARCH_ENABLED = True
    settings.AI_TASKS_ENABLED = []
    assert not ai_expand.enabled()
    req = _req("get", "/entdecken/", {"q": "пахлава", "city": CITY})
    assert (
        ai_search.slot_context(
            req,
            surface="entdecken",
            q="пахлава",
            q_eff="пахлава",
            city=CITY,
            lang="ru",
            results=0,
            fuzzy=True,
        )
        is None
    )
    assert _get(_payload()).status_code == 204


# --- эндпоинт ------------------------------------------------------------------------------


def _delay_spy(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.aggregator.tasks.ai_search_expand.delay", lambda **kw: calls.append(kw)
    )
    return calls


def test_miss_enqueues_once_and_pending_polls(x_on, monkeypatch):
    calls = _delay_spy(monkeypatch)
    assert _get(_payload()).status_code == 202
    assert _get(_payload()).status_code == 202
    assert len(calls) == 1 and calls[0]["dedupe_key"] == calls[0]["key"]
    assert "пахлава" not in calls[0]["key"]


def test_daily_cap_means_no_call(x_on, monkeypatch):
    x_on.AI_SEARCH_DAILY = 0
    calls = _delay_spy(monkeypatch)
    assert _get(_payload()).status_code == 204 and calls == []


def test_done_renders_terms_and_cards_from_db_only(x_on, x_cache):
    x_on.ROOT_URLCONF = "config.urls_public"
    tenant = _tenant()
    _listing(tenant, title={"de": "Käsekuchen vom Blech"})
    _listing(tenant, title={"de": "Bohrmaschine"})
    payload = _payload()
    x_cache.set(ai_expand.cache_key("пахлава", "ru"), {"state": "done", "terms": ["kuchen"]}, 60)
    resp = _get(payload)
    html = resp.content.decode()
    assert resp.status_code == 200 and "data-ki-expand" in html
    assert "Käsekuchen vom Blech" in html and "Bohrmaschine" not in html
    assert "q=kuchen" in html and resp["Cache-Control"] == "private, no-store"


def test_done_without_matches_is_204(x_on, x_cache):
    x_on.ROOT_URLCONF = "config.urls_public"
    _listing(_tenant(), title={"de": "Bohrmaschine"})
    x_cache.set(ai_expand.cache_key("пахлава", "ru"), {"state": "done", "terms": ["kuchen"]}, 60)
    assert _get(_payload()).status_code == 204


def test_run_caches_only_clean_terms(x_on, x_cache, monkeypatch):
    seen = []

    def gen(task, prompt, **kw):
        seen.append((task, prompt))
        return SimpleNamespace(data={"terms": ["Kuchen", "http://evil", "10 €"]})

    monkeypatch.setattr(ai_expand, "generate", gen)
    key = ai_expand.cache_key("пахлава", "ru")
    ai_expand.run("пахлава", "ru", key)
    assert x_cache.get(key) == {"state": "done", "terms": ["kuchen"]}
    assert seen[0][0] == ai_expand.TASK and "пахлава" in seen[0][1]


def test_short_and_numeric_terms_are_dropped():
    data = {"terms": ["ab", "brot2", "x" * 30, "honig"]}
    assert ai_expand.clean_terms(data, q="мёд") == ["honig"]
