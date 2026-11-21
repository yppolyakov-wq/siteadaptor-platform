"""FB-33 M3-5c C1: ядро переводов текстов блока — единственный писатель `block_i18n`.

L3 сохранённые переводы окна строки по id блока (позиция — нормализованная, как у витрины);
L4 запись переводов блока, «Seitentitel», «Was passiert jetzt», подписи плашки ("" — снять;
пустые узлы не хранятся; плашка — только при своей немецкой подписи); L5 `faq_content.put
(explicit=)` — ключ индекс источника, перевод едет за вопросом и переживает правку немецкого,
при сопоставлении по тексту — не применяется; L6 `object_faq.put(explicit=)` — то же у своих
вопросов объекта.
"""

import copy

import pytest

pytestmark = pytest.mark.django_db


def _bi():
    from apps.core import block_i18n

    return block_i18n


SECTIONS = [
    {"key": "hero"},
    {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Hallo", "body": "Welt"}},
    {"key": "text", "id": "t2", "enabled": True, "data": {"title": "Zwei", "body": "B"}},
    {"key": "quick_links", "id": "ql", "enabled": True, "data": {"set": "visit"}},
]


def _cfg(**extra):
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize({"sections": copy.deepcopy(SECTIONS), **extra})
    return cfg


def _idx(cfg, ref):
    return next(i for i, r in enumerate(cfg["sections"]) if r.get("id") == ref)


def _page(cfg, home=True, host=""):
    from apps.core import aufbau_draft

    return {**aufbau_draft._saved_state(cfg, home, host), "home": home, "host": host}


@pytest.mark.xfail(strict=True, reason="M3-5c C1: block_i18n ещё нет")
def test_saved_translations_by_block_id():
    cfg = _cfg()
    i = _idx(cfg, "t2")
    cfg["i18n"] = {"ru": {"sections": [{}] * i + [{"data": {"title": "Два"}}]}}
    page = _page(cfg)
    assert _bi().kinds(page, "t2") == ("block",)
    assert _bi().saved_for(cfg, page, "t2") == {"ru": {"title": "Два"}}
    assert _bi().saved_for(cfg, page, "t1") == {}
    assert _bi().german(cfg, page, "t2") == {"title": "Zwei", "body": "B"}


@pytest.mark.xfail(strict=True, reason="M3-5c C1: block_i18n ещё нет")
def test_apply_writes_and_removes_block_translations():
    cfg = _cfg()
    draft = {**_page(cfg), "btr": {"t2": {"ru": {"title": "Два", "body": ""}}}}
    _bi().apply(cfg, draft, True, "")
    i = _idx(cfg, "t2")
    assert cfg["i18n"]["ru"]["sections"][i] == {"data": {"title": "Два"}}
    draft["btr"] = {"t2": {"ru": {"title": ""}}}
    _bi().apply(cfg, draft, True, "")
    assert "i18n" not in cfg or "ru" not in cfg["i18n"]  # пустые узлы не хранятся


@pytest.mark.xfail(strict=True, reason="M3-5c C1: block_i18n ещё нет")
def test_apply_title_next_and_tiles():
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize({"page_titles": {"services": {"title": "Leistungen"}}})
    draft = {**_page(cfg, False, "services"), "btr": {"__title": {"en": {"title": "Services"}}}}
    _bi().apply(cfg, draft, False, "services")
    assert cfg["i18n"]["en"]["page_titles"] == {"services": {"title": "Services"}}

    cfg = siteconfig.normalize({"confirmation_next": "Wir melden uns."})
    draft = {**_page(cfg, False, "confirmation"), "btr": {"next": {"ru": {"text": "Позвоним."}}}}
    _bi().apply(cfg, draft, False, "confirmation")
    assert cfg["i18n"]["ru"]["confirmation_next"] == "Позвоним."

    cfg = _cfg()
    row = next(r for r in cfg["sections"] if r.get("id") == "ql")
    row["data"] = {"set": "visit", "labels": {next(iter(_tile_keys())): "Meine"}}
    key = next(iter(_tile_keys()))
    other = list(_tile_keys())[1]
    draft = {**_page(cfg), "btr": {"ql": {"ru": {f"label.{key}": "Моя", f"label.{other}": "X"}}}}
    _bi().apply(cfg, draft, True, "")
    data = cfg["i18n"]["ru"]["sections"][_idx(cfg, "ql")]["data"]
    assert data == {"labels": {key: "Моя"}}  # чужая (стандартная) подпись не переводится


def _tile_keys():
    from apps.core import hero_tiles

    return hero_tiles.tile_keys("visit")


@pytest.mark.xfail(strict=True, reason="M3-5c C1: explicit ещё нет")
def test_faq_put_explicit_follows_the_question_and_survives_german_edit():
    from apps.core import faq_content

    cfg = {"faq": [{"q": "A?", "a": "1"}, {"q": "B?", "a": "2"}], "i18n": {}}
    # B? встал первым и изменён; перевод введён тут же — остаётся; у A? — новый перевод
    faq_content.put(
        cfg,
        [{"q": "B2?", "a": "2"}, {"q": "A?", "a": "1"}],
        [1, 0],
        explicit={"ru": {1: {"q": "Б2?"}, 0: {"a": "один"}}},
    )
    assert cfg["i18n"]["ru"]["faq"] == [{"q": "Б2?"}, {"a": "один"}]
    # по тексту (сохранённое изменили) — номера источника ничего не значат
    cfg2 = {"faq": [{"q": "A?", "a": "1"}], "i18n": {"ru": {"faq": [{"q": "А?"}]}}}
    faq_content.put(
        cfg2, [{"q": "A?", "a": "1"}], [0], base_fp="x", explicit={"ru": {0: {"q": "Z"}}}
    )
    assert cfg2["i18n"]["ru"]["faq"] == [{"q": "А?"}]
    # "" — снять перевод
    faq_content.put(cfg2, [{"q": "A?", "a": "1"}], [0], explicit={"ru": {0: {"q": ""}}})
    assert "faq" not in cfg2["i18n"]["ru"]


@pytest.mark.xfail(strict=True, reason="M3-5c C1: explicit ещё нет")
def test_object_faq_put_explicit():
    from types import SimpleNamespace

    from apps.core import object_faq

    obj = SimpleNamespace(
        pk="x", faq=[{"q": "A?", "a": "1"}, {"q": "B?", "a": "2"}], faq_i18n={"ru": [{"q": "А?"}]}
    )
    changed = object_faq.put(
        obj, "service", obj.faq, [0, 1], explicit={"en": {1: {"a": "two"}}, "ru": {0: {"q": ""}}}
    )
    assert "faq_i18n" in changed
    assert obj.faq_i18n == {"en": [{}, {"a": "two"}]}
