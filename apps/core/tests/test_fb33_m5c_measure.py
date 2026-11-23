"""FB-33 M5c: замок замера «до/после» стопки 11 `scripts/fb33_m5c_measure.py` (план §1 п.4, §3).

Самопроверка чистых функций сверки (без БД): равные замеры — чисто; разный хэш витрины,
другой `site_config` после «Speichern», другие `items` вставки — расхождение; SQL экрана в
допуске ±1 — чисто, вне — расхождение; POST — не больше базы + SQL одного `blocks_for`
(или `--sql-slack`); разметка схемы (д) — только печать. Плюс то, на чём держится хэш
витрины (снятие `csrfmiddlewaretoken`, `form_token`, `nonce`), и факт «сервер понял `after`».
"""

import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "fb33_m5c_measure.py"


def _script():
    spec = importlib.util.spec_from_file_location("fb33_m5c_measure", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _script()


def _page(**over):
    page = {
        "kit": "shop",
        "code": "home",
        "screen": {"status": 200, "sql": 45, "marks": {"blocks": ["a", "b"], "counts": {"row": 2}}},
        "blocks_for_sql": 3,
        "add_tail": {"sql": 4, "new_index": 2, "items": [{"pos": 0, "key": "a"}]},
        "add_after": {"target": "b", "honored": False},
        "up": {"sql": 4},
        "save_plain": {"before": "x", "after": "x", "same": True},
        "save_updown": {"before": "x", "after": "x", "same": True},
        "tasks": [],
    }
    page.update(over)
    return page


def _run(**page_over):
    return {
        "pages": {"shop|home": _page(**page_over)},
        "storefront": {"shop|/": {"status": 200, "sha256": "s1"}},
    }


def _diff(before, after, **kw):
    diff = M.compare(before, after, **kw)
    _text, clean = M.report(diff)
    return diff, clean


def test_equal_runs_are_clean():
    base = _run()
    diff, clean = _diff(base, copy.deepcopy(base))
    assert clean
    assert not any(diff.values())


def test_storefront_hash_differs():
    after = _run()
    after["storefront"]["shop|/"]["sha256"] = "s2"
    diff, clean = _diff(_run(), after)
    assert not clean
    assert len(diff["a"]) == 1


def test_storefront_page_missing_is_not_clean():
    after = _run()
    del after["storefront"]["shop|/"]
    diff, clean = _diff(_run(), after)
    assert not clean
    assert diff["missing"]


def test_site_config_after_save_differs():
    diff, clean = _diff(_run(), _run(save_plain={"before": "x", "after": "y", "same": False}))
    assert not clean
    assert len(diff["b"]) == 1


def test_items_add_without_after_differ():
    after = _run(add_tail={"sql": 4, "new_index": 1, "items": [{"pos": 0, "key": "b"}]})
    diff, clean = _diff(_run(), after)
    assert not clean
    assert len(diff["c"]) == 1


def test_new_block_id_does_not_count():
    known = {"about"}
    one = [{"key": "about"}, {"key": "text", "id": "aaa111", "data": {"t": 1}}]
    two = [{"key": "about"}, {"key": "text", "id": "bbb222", "data": {"t": 1}}]
    assert M.norm_items(one, known) == M.norm_items(two, known)
    assert M.norm_items(one, known)[1]["id"] == M.NEW_ID
    kept = [{"key": "text", "id": "old1"}]
    assert M.norm_items(kept, {"old1"})[0]["id"] == "old1"
    assert M.inserted_at(one, known) == 1


def test_screen_sql_within_and_outside_slack():
    _d, clean = _diff(_run(), _run(screen={"status": 200, "sql": 46, "marks": {}}))
    # разметка (д) другая — только печать, SQL +1 — в допуске
    assert clean
    diff, clean = _diff(_run(), _run(screen={"status": 200, "sql": 47, "marks": {}}))
    assert not clean
    assert len(diff["d"]) == 1
    _d, clean = _diff(_run(), _run(screen={"status": 200, "sql": 44, "marks": {}}))
    assert clean
    _d, clean = _diff(_run(), _run(screen={"status": 200, "sql": 46, "marks": {}}), screen_slack=0)
    assert not clean


def test_post_sql_allowance_is_one_blocks_for():
    # база: up 4 SQL, blocks_for 3 → «после» до 7 — чисто, 8 — расхождение
    _d, clean = _diff(_run(), _run(up={"sql": 7}))
    assert clean
    diff, clean = _diff(_run(), _run(up={"sql": 8}))
    assert not clean
    assert "up" in diff["d"][0]
    diff, clean = _diff(_run(), _run(add_tail={**_page()["add_tail"], "sql": 8}))
    assert not clean
    # явный допуск `--sql-slack`
    _d, clean = _diff(_run(), _run(up={"sql": 8}), sql_slack=4)
    assert clean
    _d, clean = _diff(_run(), _run(up={"sql": 5}), sql_slack=0)
    assert not clean


def test_markup_change_is_print_only():
    marks = {"blocks": ["a", "c"], "counts": {"row": 3}}
    diff, clean = _diff(_run(), _run(screen={"status": 200, "sql": 45, "marks": marks}))
    assert clean
    assert diff["e"]


def test_after_honored_fact_change_is_print_only():
    diff, clean = _diff(_run(), _run(add_after={"target": "b", "honored": True}))
    assert clean
    assert diff["e"]


def test_strip_volatile():
    html = (
        '<input type="hidden" name="csrfmiddlewaretoken" value="AAA">'
        '<input value="BBB" type="hidden" name="csrfmiddlewaretoken">'
        '<input type="hidden" name="form_token" value="CCC" id="id_form_token">'
        '<script nonce="DDD">x</script><input name="q" value="keep">'
    )
    out = M.strip_volatile(html)
    for token in ("AAA", "BBB", "CCC", "DDD"):
        assert token not in out
    assert 'value="keep"' in out
    assert M.page_sha(html) == M.page_sha(html.replace("AAA", "ZZZ").replace("DDD", "Q"))
    assert M.page_sha(html) != M.page_sha(html.replace("keep", "other"))


def test_after_honored():
    known = {"a", "b", "c"}
    new = {"key": "text", "id": "n1"}
    # вставка сразу за целью
    assert M.after_honored([{"key": "a"}, {"key": "b"}, new, {"key": "c"}], known, "b") is True
    # сервер поле не знает — блок в хвосте
    assert M.after_honored([{"key": "a"}, {"key": "b"}, {"key": "c"}, new], known, "b") is False
    # цель — последний блок: хвост не отличить
    assert M.after_honored([{"key": "a"}, {"key": "b"}, new], known, "b") is None
    # вставки нет
    assert M.after_honored([{"key": "a"}], known, "a") is None


def test_after_target_avoids_last_block():
    own = [{"ref": "a"}, {"ref": "b"}]
    tail = [{"key": "a"}, {"key": "b"}, {"key": "text", "id": M.NEW_ID}]
    assert M._after_target(own, tail) == "a"
    tail = [{"key": "b"}, {"key": "a"}, {"key": "text", "id": M.NEW_ID}]
    assert M._after_target(own, tail) == "b"
    assert M._after_target([{"ref": "a"}], tail) == ""


def test_schema_marks():
    html = (
        '<ul data-schema-row><li data-schema-drag="a"><a data-schema-block="a"></a></li></ul>'
        '<ul data-schema-row><li data-schema-pinned="b"><a data-schema-block="b"></a></li></ul>'
        "<details data-schema-add></details><form data-schema-add-row></form>"
    )
    marks = M.schema_marks(html)
    assert marks["blocks"] == ["a", "b"]
    assert marks["rows"] == 2
    assert marks["counts"]["drag"] == 1
    assert marks["counts"]["pinned"] == 1
    assert marks["counts"]["add"] == 1  # `data-schema-add-row` — не `data-schema-add`


def test_sample_is_deterministic_and_spread():
    rows = list(range(100))
    assert M.sample(rows, 0) == rows
    assert M.sample(rows, 200) == rows
    picked = M.sample(rows, 5)
    assert picked == M.sample(rows, 5)
    assert len(picked) == 5
    assert picked[0] == 0
    assert picked[-1] >= 80  # объекты в конце списка тоже попадают


def test_stand_db_only():
    """Скрипт не меряет мимо стенда: проверка имени БД и настроек — в `main`."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'endswith("_stand")' in src
    assert '"config.settings.stand"' in src
    assert "set_rollback(True)" in src  # записи (б)–(г) — с откатом
    assert "session.delete()" in src  # сессии владельца и анонима не остаются в кэше
