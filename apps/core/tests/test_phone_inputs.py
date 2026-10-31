"""KA-12 E9.5: телефон — правильная клавиатура и доступные фото-кнопки."""

import importlib
import inspect
import pkgutil
import re
from pathlib import Path

from django import forms
from django.conf import settings

import apps

TEMPLATES = Path(settings.BASE_DIR) / "templates"
_PHONE = re.compile(r"phone|telefon|whatsapp|mobil")


def _form_classes():
    seen = set()
    for info in pkgutil.walk_packages(apps.__path__, "apps."):
        if not (info.name.endswith(".forms") or ".forms." in info.name):
            continue
        mod = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(cls, forms.BaseForm)
                and cls.__module__ == mod.__name__
                and cls not in seen
            ):
                seen.add(cls)
                yield cls


def test_phone_and_email_form_fields_use_matching_input_type():
    bad = []
    for cls in _form_classes():
        for name, field in cls.base_fields.items():
            kind = getattr(field.widget, "input_type", None)
            if isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
                continue
            if _PHONE.search(name) and kind != "tel":
                bad.append(f"{cls.__name__}.{name}={kind}")
            if re.search(r"email", name) and kind != "email":
                bad.append(f"{cls.__name__}.{name}={kind}")
    assert not bad, bad


def _cabinet_templates():
    for path in TEMPLATES.rglob("*.html"):
        rel = path.relative_to(TEMPLATES).as_posix()
        if not rel.startswith(("storefront/", "aggregator/")):
            yield rel, path.read_text()


def test_handwritten_phone_inputs_are_tel():
    pat = re.compile(r'<input[^>]*name="[a-z_]*(?:phone|telefon|whatsapp)[a-z_]*"[^>]*>')
    bad = [
        rel
        for rel, text in _cabinet_templates()
        for tag in pat.findall(text)
        if not re.search(r'type="(tel|hidden)"', tag)
    ]
    assert not bad, bad


def test_barcode_inputs_open_numeric_keypad():
    from apps.catalog.forms import ProductForm

    assert ProductForm().fields["gtin"].widget.attrs.get("inputmode") == "numeric"
    bad = [
        rel
        for rel, text in _cabinet_templates()
        for tag in re.findall(r'<input[^>]*name="gtin"[^>]*>', text)
        if 'inputmode="numeric"' not in tag and 'type="hidden"' not in tag
    ]
    assert not bad, bad


def test_photo_button_file_inputs_stay_keyboard_reachable():
    """Файл-инпут внутри <label>-кнопки 📷 — sr-only, не display:none (иначе Tab его не видит)."""
    pat = re.compile(r"<label\b[^>]*>[^<]*📷[^<]*<input[^>]*type=\"file\"[^>]*>")
    bad = [
        rel
        for rel, text in _cabinet_templates()
        for tag in pat.findall(text)
        if 'class="hidden"' in tag
    ]
    assert not bad, bad
