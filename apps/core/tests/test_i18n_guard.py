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
import re

import pytest

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


def test_no_english_msgid_without_german_translation():
    """Базовый язык проекта — немецкий, но часть msgid заведена по-английски.
    Если у такой строки нет немецкого `msgstr`, немецкий владелец видит
    английский текст (волна I18N-12 чинила 20 таких). Замок держит класс."""
    spec = importlib.util.spec_from_file_location(
        "i18n_status", ROOT / "scripts" / "i18n_status.py"
    )
    status = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(status)
    cats = {
        loc: status.parse_po(ROOT / f"locale/{loc}/LC_MESSAGES/django.po") for loc in status.LOCALES
    }
    bad = status.english_msgid_without_german(cats)
    assert bad == [], "английский msgid без немецкого перевода: " + "; ".join(bad[:10])


def test_all_catalogs_carry_the_same_msgids():
    """Пять каталогов обязаны нести один и тот же набор msgid: расхождение
    означает, что у части пользователей строка молча уедет по-немецки."""
    spec = importlib.util.spec_from_file_location(
        "i18n_status", ROOT / "scripts" / "i18n_status.py"
    )
    status = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(status)
    cats = {
        loc: set(status.parse_po(ROOT / f"locale/{loc}/LC_MESSAGES/django.po"))
        for loc in status.LOCALES
    }
    union = set().union(*cats.values())
    drift = {loc: sorted(union - ids)[:5] for loc, ids in cats.items() if union - ids}
    assert drift == {}, f"расхождение наборов msgid: {drift}"


@pytest.mark.django_db
def test_form_labels_are_translatable():
    """Подпись поля формы кабинета обязана переводиться.

    Без явного `label`/`verbose_name` Django печатает машинное имя поля
    («Base price», «Is featured») — оно не переводится НИ на один язык, включая
    немецкий. До I18N-13 таких подписей было 56 из 198; замок не даёт классу
    вернуться: под ru у каждой подписи обязана быть кириллица (исключения —
    бренды и единицы измерения).
    """
    import importlib
    import inspect

    from django import forms as dj_forms
    from django.utils import translation

    cyrillic = re.compile(r"[а-яА-ЯёЁ]")
    brandish = re.compile(
        r"^(E-?Mail|WhatsApp|Instagram|Facebook|Telegram|TikTok|LinkedIn|YouTube|URL|SEO|PDF|"
        r"CSV|QR|API|IBAN|BIC|SKU|EAN|MwSt\.?|USt\.?|VAT|Stripe|PayPal|Klarna|SEPA|Google|"
        r"DATEV|ID|Bio|kg|g|ml|l)\b",
        re.I,
    )
    bad = []
    with translation.override("ru"):
        for path in sorted(ROOT.glob("apps/*/forms.py")):
            module_name = f"apps.{path.parent.name}.forms"
            try:
                module = importlib.import_module(module_name)
            except Exception:  # приложение может быть не сконфигурировано
                continue
            for cls_name, cls in vars(module).items():
                if not (
                    inspect.isclass(cls)
                    and issubclass(cls, (dj_forms.Form, dj_forms.ModelForm))
                    and cls.__module__ == module_name
                ):
                    continue
                try:
                    form = cls()
                except Exception:  # формам с обязательным tenant нужен контекст
                    continue
                for field_name, field in form.fields.items():
                    label = str(field.label or "").strip()
                    if not label or cyrillic.search(label) or brandish.match(label):
                        continue
                    bad.append(f"{module_name}.{cls_name}.{field_name}: «{label}»")
    assert bad == [], "подписи полей без перевода: " + "; ".join(bad[:12])
