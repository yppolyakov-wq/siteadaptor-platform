"""Замок каркаса Playwright-стендов `scripts/standlib.py` (T-13.4, 2026-11-21).

Стенды в CI не входят (там нет браузера), поэтому здесь — только то, что проверяется без
браузера и без БД: счётчик `Report`, обход `matrix`, размеры и языки. Сам каркас в Chromium
проверяет `scripts/standlib.py --selftest`.

И правило: каждый новый `scripts/*_stand.py` пишется через каркас. Стенды, написанные до него,
перечислены в `LEGACY_STANDS`; список можно только сокращать — стенд переносится на каркас при
следующей правке и уходит из списка.
"""

import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"

#: стенды до каркаса (38 на 2026-11-21 + `fb33_m4c_scope_stand.py`: стопка 7 FB-33 написала его
#: параллельно, до прихода каркаса в main). НЕ дополнять: новый стенд импортирует `standlib`.
LEGACY_STANDS = frozenset(
    """
    ais5_translate_stand.py ais7_text_draft_stand.py assistant_a0_stand.py
    assistant_ai_stand.py assistant_help_stand.py aufbau_owner_stand.py aufbau_stand.py
    content_pages_stand.py design_stand.py editor_p5_stand.py editor_p5b_stand.py
    editor_photo_stand.py fb33_m1_card_stand.py fb33_m2b2a_faq_stand.py
    fb33_m2b2b_faq_stand.py fb33_m2c_quick_links_stand.py fb33_m2i34_c5_window_stand.py
    fb33_m2i34_cart_stand.py fb33_m2i5b_i18n_stand.py fb33_m2i5c_translate_stand.py
    fb33_m35b_stand.py fb33_m35c_i18n_stand.py fb33_m37_preview_stand.py fb33_m3_3_stand.py
    fb33_m3_3d_text_source_stand.py fb33_m3_4_karte_stand.py fb33_m3_5a_texte_stand.py
    fb33_m3_6_stand.py fb33_m3_9_owner_stand.py fb33_m3_window_stand.py fb33_m4c_scope_stand.py
    fb33_m4_studio_settings_stand.py fb33_m4b_studio_dupes_stand.py studio_boundary_stand.py
    text_pages_stand.py wizard_v4_e2e_stand.py wizard_v4_photo_stand.py
    wizard_v4_pruefen_stand.py wizard_v4_stand.py
    """.split()
)
LEGACY_MAX = 39

_USES = re.compile(r"^\s*(?:import standlib\b|from standlib import\b)", re.M)


def _mod():
    spec = importlib.util.spec_from_file_location("standlib", SCRIPTS / "standlib.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # playwright в каркасе импортируется лениво — здесь не нужен
    return mod


def _uses_standlib(path: pathlib.Path) -> bool:
    return bool(_USES.search(path.read_text(encoding="utf-8")))


def test_sizes_and_langs_are_the_acceptance_set():
    sl = _mod()
    assert sl.SIZES == ((1440, 900), (390, 844))
    assert sl.LANGS == ("de", "ru")
    assert sl.JS_MODES == (False, True)  # проход без JS — обязательный и первый


def test_report_counts_and_exit_code():
    sl = _mod()
    rep = sl.Report(quiet=True)
    assert rep.exit_code == 0
    assert rep.check(True, "ок") is True
    assert rep.check(1 == 2, "плохо", code="overflow") is False
    assert (rep.ok, rep.fail, rep.codes) == (1, ["плохо"], ["overflow"])
    assert rep.exit_code == 1


def test_report_prints_repeated_signature_once(capsys):
    sl = _mod()
    rep = sl.Report()
    rep.check(True, "вход")
    rep.check(False, "390 de: гор. скролл 12px", sigs="гор. скролл /aufbau/", code="overflow")
    rep.check(False, "390 ru: гор. скролл 12px", sigs="гор. скролл /aufbau/", code="overflow")
    rep.check(False, "без подписи")
    rep.check(False, "без подписи")
    rep.note("settle timeout")
    rep.note("settle timeout")
    out = capsys.readouterr().out
    assert out.count("  ✓ вход") == 1
    assert out.count("гор. скролл 12px") == 1 and "390 de" in out, out
    assert out.count("  ✗ без подписи") == 1
    assert out.count("  · settle timeout") == 1
    assert len(rep.fail) == 4 and rep.codes == ["overflow", "overflow", "other", "other"]

    line = rep.summary("проба")
    out = capsys.readouterr().out
    assert line == "проба: 1 ✓, 4 ✗" and out.rstrip().endswith(line)
    assert "×2    гор. скролл /aufbau/" in out and "напр.: 390 de: гор. скролл 12px" in out
    assert "×2    settle timeout" in out


def test_report_quiet_hides_passes_but_not_failures(capsys):
    sl = _mod()
    rep = sl.Report(quiet=True)
    rep.check(True, "тихо")
    rep.check(True, "громко", quiet=False)
    rep.check(False, "дефект")
    out = capsys.readouterr().out
    assert "тихо" not in out and "  ✓ громко" in out and "  ✗ дефект" in out


def test_report_finish_exits_nonzero_on_failure(capsys):
    sl = _mod()
    good, bad = sl.Report(), sl.Report()
    good.check(True, "ок")
    bad.check(False, "плохо")
    with pytest.raises(SystemExit) as ok_exit:
        good.finish("стенд")
    with pytest.raises(SystemExit) as bad_exit:
        bad.finish("стенд")
    assert (ok_exit.value.code, bad_exit.value.code) == (0, 1)
    assert "стенд: 1 ✓, 0 ✗" in capsys.readouterr().out


def test_matrix_default_is_eight_combinations_nojs_first():
    sl = _mod()
    combos = list(sl.matrix())
    assert len(combos) == len(set(combos)) == 8
    assert set(combos) == {
        (w, h, lang, js) for (w, h) in sl.SIZES for lang in sl.LANGS for js in (False, True)
    }
    assert [c[3] for c in combos] == [False] * 4 + [True] * 4
    assert combos[0] == (1440, 900, "de", False)


def test_matrix_takes_a_narrowed_set():
    sl = _mod()
    assert list(sl.matrix(sizes=((390, 844),), langs=("ru",), js_modes=(True,))) == [
        (390, 844, "ru", True)
    ]
    assert list(sl.matrix(langs=())) == []


def test_module_documents_the_rule_and_selftest():
    doc = _mod().__doc__
    assert "--selftest" in doc and "новые стенды — только через каркас" in doc
    assert "playwright install" in doc and "config.settings.stand" in doc


def test_new_stands_must_use_standlib():
    stands = sorted(SCRIPTS.glob("*_stand.py"))
    assert stands, "стенды не найдены — замок смотрит не туда"
    bare = [p.name for p in stands if p.name not in LEGACY_STANDS and not _uses_standlib(p)]
    assert not bare, (
        f"новый стенд без каркаса: {bare} — запуск браузера, вход, Report, размеры и языки "
        "брать из scripts/standlib.py (`import standlib`), в LEGACY_STANDS не дописывать"
    )


def test_legacy_list_only_shrinks():
    assert len(LEGACY_STANDS) <= LEGACY_MAX, "LEGACY_STANDS можно только сокращать"
    stale = sorted(n for n in LEGACY_STANDS if not (SCRIPTS / n).exists())
    assert not stale, f"стенда уже нет — убрать из LEGACY_STANDS: {stale}"
    moved = sorted(n for n in LEGACY_STANDS if _uses_standlib(SCRIPTS / n))
    assert not moved, f"стенд уже на каркасе — убрать из LEGACY_STANDS: {moved}"


def test_the_lock_itself_tells_a_stand_with_standlib_from_one_without(tmp_path):
    # Замок, который ничего не ловит, хуже отсутствующего.
    new, old, talk = (tmp_path / n for n in ("a_stand.py", "b_stand.py", "c_stand.py"))
    new.write_text("import sys\n\nimport standlib as sl\n", encoding="utf-8")
    old.write_text("from playwright.sync_api import sync_playwright\n", encoding="utf-8")
    talk.write_text('"""Когда-нибудь перенести на standlib."""\n', encoding="utf-8")
    assert _uses_standlib(new)
    assert not _uses_standlib(old)
    assert not _uses_standlib(talk)  # упоминание в тексте — не импорт
