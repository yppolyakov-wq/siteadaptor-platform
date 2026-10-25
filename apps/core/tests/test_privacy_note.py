"""KA-12 A-1 (E7.7, Art. 13 DSGVO): каждая форма витрины, собирающая e-mail, телефон или
файл, показывает ссылку на Datenschutzerklärung. Замок класса: новая форма без заметки
краснит CI. Исключения — осознанным списком (там ссылка уже есть своя)."""

import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import override_settings

ROOT = Path(__file__).resolve().parents[3] / "templates" / "storefront"
FIELD = re.compile(r'type="(?:file|email|tel)"|name="(?:email|phone)"')
# Своя ссылка на Datenschutz уже есть рядом с полем.
OWN_LINK = {"sections/_block_newsletter.html"}


def _forms(text):
    for m in re.finditer(r"<form\b.*?</form>", text, flags=re.S):
        yield m.group(0)


def test_every_storefront_form_with_personal_data_links_privacy():
    missing = []
    for path in ROOT.rglob("*.html"):
        rel = str(path.relative_to(ROOT))
        if rel in OWN_LINK or rel == "_privacy_note.html":
            continue
        text = path.read_text()
        if rel == "_buybox_contact_fields.html":
            if "_privacy_note.html" not in text:
                missing.append(rel)
            continue
        for form in _forms(text):
            if FIELD.search(form) and "_privacy_note.html" not in form:
                missing.append(rel)
    assert not missing, missing


@override_settings(ROOT_URLCONF="config.urls_tenant")
def test_note_renders_link_and_photo_hint():
    html = render_to_string("storefront/_privacy_note.html", {"photos": 1})
    assert "/datenschutz/" in html and "Fotos" in html
    assert "Fotos" not in render_to_string("storefront/_privacy_note.html", {})
