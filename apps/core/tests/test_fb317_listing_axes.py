"""FB-31.7 B1a: перенос кодов девяти листингов (`page_styles`) в строки-оси — вид прежний.

Проверка вида — та же функция, что эталоны P4 (`listing_composition.context`): для каждой
поверхности × кода × данных результат по перенесённому конфигу БЕЗ старого ключа совпадает
с прежним.
"""

import pytest

from apps.core import compositions, page_axes_migration
from apps.core.tests import test_fb31p4_listing_golden as g4

# FB-31.7 B3b: модуль проверяет отрисовку по старым кодам шаблонов (до B4) — см. conftest
LEGACY_CODES = True

CODES = g4.CODES


def _ctx(cfg, surface, entries, photo):
    return g4._ctx(surface, "", entries, photo, cfg=cfg)


def _without_old_key(cfg):
    out = dict(cfg)
    out.pop("page_styles", None)
    return out


@pytest.mark.parametrize("surface", sorted(compositions.LISTING_SURFACES))
def test_every_code_moves_to_rows_and_looks_the_same(surface):
    for code in [*CODES, "quatsch"]:
        cfg = {"page_styles": {surface: code}}
        new, report = page_axes_migration.migrate(cfg)
        assert report.mismatches == [], (surface, code)
        for entries in (True, False) if surface in g4.WITH_ENTRIES else (False,):
            for photo in (True, False):
                want = _ctx(cfg, surface, entries, photo)
                assert _ctx(_without_old_key(new), surface, entries, photo) == want, (
                    surface,
                    code,
                    entries,
                    photo,
                )
                assert _ctx(new, surface, entries, photo) == want  # пока старый ключ на месте


def test_own_blocks_stay_and_stay_below_the_list():
    text = {"key": "text", "id": "t1", "data": {"title": "Hallo", "body": "x"}}
    cfg = {"page_styles": {"services": "kopfbild"}, "page_blocks": {"services": [text]}}
    new, report = page_axes_migration.migrate(cfg)
    rows = new["page_blocks"]["services"]
    assert report.surfaces == {"services": "done"}
    ids = [r.get("id") for r in rows]
    assert "t1" in ids
    marker = next((i for i, r in enumerate(rows) if r.get("key") == "main"), None)
    assert marker is None or marker < ids.index("t1"), "свой блок остался под списком"


def test_hidden_head_row_never_changes_the_view():
    # скрытая строка, которую сейчас заменяет код: перенос либо пропускается (сайт не
    # трогается), либо проходит только с тем же видом — допуск расхождений ноль
    cfg = {
        "page_styles": {"services": "kopfbild"},
        "page_blocks": {"services": [{"key": "page_head", "enabled": False}]},
    }
    new, report = page_axes_migration.migrate(cfg)
    if report.surfaces["services"] in ("skip", "mismatch"):
        assert new == cfg, "пропущенная поверхность не меняется"
    for photo in (True, False):
        want = _ctx(cfg, "services", True, photo)
        assert _ctx(_without_old_key(new), "services", True, photo) == want


def test_materialize_refuses_a_hidden_row_the_code_overrides():
    from apps.core import listing_parts
    from apps.core import page_parts as pp

    s = listing_parts.LISTINGS["services"]
    assert pp.materialize_rows(s, [{"key": "page_head", "enabled": False}], "kopfbild") is None


def test_rerun_changes_nothing():
    cfg = {"page_styles": {"events": "tabs", "services": "kopfbild"}}
    once, _ = page_axes_migration.migrate(cfg)
    twice, report = page_axes_migration.migrate(once)
    assert twice == once and not report.changed


def test_no_code_no_change():
    cfg = {"hero_title": "x"}
    new, report = page_axes_migration.migrate(cfg)
    assert new == cfg and report.surfaces == {}


def test_review_translations_follow_their_blocks_after_rows_are_inserted():
    from apps.tenants import siteconfig

    text = {"key": "text", "id": "t1", "data": {"title": "Hallo", "body": "x"}}
    cfg = {
        "page_styles": {"services": "kopfbild"},
        "page_blocks": {"services": [text]},
        "i18n": {"en": {"page_blocks": {"services": [{"data": {"title": "Hello"}}]}}},
    }
    new, report = page_axes_migration.migrate(cfg)
    assert report.surfaces == {"services": "done"}
    rows = siteconfig.localize(siteconfig.normalize(new), "en")["page_blocks"]["services"]
    own = next(r for r in rows if r.get("id") == "t1")
    assert own["data"]["title"] == "Hello", "перевод остался у своего блока"


def test_review_one_mismatch_leaves_the_whole_site_untouched(monkeypatch):
    from apps.core import page_parts as pp

    real = pp.materialize_rows

    def fail_events(s, rows, code):
        return None if s.name == "events" else real(s, rows, code)

    monkeypatch.setattr(pp, "materialize_rows", fail_events)
    cfg = {"page_styles": {"events": "tabs", "services": "kopfbild"}}
    new, report = page_axes_migration.migrate(cfg)
    assert report.surfaces["events"] == "skip" and new == cfg, "сайт не тронут целиком"


def test_review_other_hosts_and_languages_stay_byte_for_byte():
    junk_host = [{"key": "nope", "x": 1}, {"key": "text", "id": "a1", "data": {"title": "A"}}]
    cfg = {
        "page_styles": {"services": "kopfbild"},
        "page_blocks": {"text": junk_host},
        "i18n": {"en": {"page_blocks": {"text": [{"data": {"title": "B"}}]}, "hero_title": "Hi"}},
    }
    new, report = page_axes_migration.migrate(cfg)
    assert report.surfaces == {"services": "done"}
    assert new["page_blocks"]["text"] == junk_host, "чужой хост не переписан нормализацией"
    assert new["i18n"]["en"]["page_blocks"]["text"] == [{"data": {"title": "B"}}]
    assert new["i18n"]["en"]["hero_title"] == "Hi"
