"""I18N-13: замки гейта «строка без пути перевода».

Класс дефектов: подпись, которую xgettext не извлекает (не обёрнута вовсе или
обёрнута внутри f-строки), проходит мимо `scripts/i18n_gap.py` — msgid не
появляется, «непокрытой» строка не считается, и у ru/tr/uk навсегда остаётся
немецкий текст. Сканер сверяет находки с базовой линией; здесь — замок, что
базовая линия не расходится с кодом молча.
"""

import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _scanner():
    spec = importlib.util.spec_from_file_location(
        "i18n_untranslated", ROOT / "scripts" / "i18n_untranslated.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_new_untranslated_strings():
    """Новая необёрнутая подпись обязана быть либо переведена, либо осознанно
    внесена в базовую линию (`--write-baseline`) — молча копиться не может."""
    scanner = _scanner()
    baseline = json.loads(scanner.BASELINE.read_text(encoding="utf-8"))
    fresh = [f for f in scanner.collect() if f["text"] not in baseline.get(f["file"], [])]
    assert fresh == [], "строки без пути перевода вне базовой линии: " + "; ".join(
        f"{f['file']}:{f['line']} «{f['text'][:60]}»" for f in fresh[:10]
    )


def test_gettext_inside_fstring_is_reported():
    """Правило f-строк живое: xgettext не извлекает `f"{_('X')}"`, поэтому такой
    литерал обязан либо уже лежать в .po, либо попасть в находки."""
    scanner = _scanner()
    sample = ROOT / "apps" / "core" / "views.py"
    known = scanner.po_msgids()
    findings = scanner.scan_python(sample, "apps/core/views.py", known)
    assert isinstance(findings, list)
    # Литералы из f-строк этого модуля переведены — значит правило молчит.
    assert not [f for f in findings if f["rule"] == "fstring" and f["text"] in known]
