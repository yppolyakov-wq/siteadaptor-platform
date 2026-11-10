"""M21.8: визуальный редактор во всех длинных текстах владельца — замки."""

import re
from pathlib import Path

import pytest
from django.template import Context, Template

from apps.core.richtext import clean_input, clean_page_input, is_rich, to_plain

ROOT = Path(__file__).resolve().parents[3]


def _render(src, **ctx):
    return Template("{% load richtext %}" + src).render(Context(ctx))


def test_is_rich_needs_a_real_tag_boundary():
    """«<info@shop.de>» в Impressum — не тег <i>: плоский текст не теряет адрес."""
    assert not is_rich("Kontakt: <info@shop.de>")
    assert not is_rich("ab <50 € · <Anna>")
    assert is_rich("<p>Text</p>") and is_rich("a<br>b") and is_rich("<H2>Titel</H2>")
    assert clean_input("Kontakt: <info@shop.de>") == "Kontakt: <info@shop.de>"
    assert to_plain("Kontakt: <info@shop.de>") == "Kontakt: <info@shop.de>"


def test_rich_block_plain_keeps_old_look_rich_is_sanitized():
    plain = _render('{% rich_block t css="mt-2" %}', t="Zeile 1\n<script>x</script>")
    assert (
        plain
        == '<div class="mt-2 whitespace-pre-line">Zeile 1\n&lt;script&gt;x&lt;/script&gt;</div>'
    )
    rich = _render(
        '{% rich_block t css="mt-2" %}', t='<p onclick="x">Hi <b>du</b></p><script>1</script>'
    )
    assert rich == '<div class="mt-2 rich-text"><p>Hi <b>du</b></p></div>'
    assert _render("{% rich_block t %}", t="  ") == ""


def test_rich_block_page_mode_keeps_headings_only_in_page_mode():
    t = "<h2>§ 1 Geltungsbereich</h2><p>Text</p>"
    assert "<h2>" in _render('{% rich_block t mode="page" %}', t=t)
    assert "<h2>" not in _render("{% rich_block t %}", t=t)
    assert clean_page_input(t) == t


def test_inline_canvas_edit_only_for_plain_text():
    """Инлайн-правка канвы пишет текст — у форматированного она снесла бы разметку."""
    attrs = 'edit_model="service" edit_pk=1 edit_field="description"'
    assert 'data-edit-field="description"' in _render("{% rich_block t " + attrs + " %}", t="a")
    assert "data-edit" not in _render("{% rich_block t " + attrs + " %}", t="<p>a</p>")


#: витрина: каждое длинное поле владельца выводится через rich_block (план §2).
STOREFRONT = {
    "_dish_info.html": "product.description_text",
    "_category_header.html": "category_description",
    "products.html": "category_description",
    "sections/detail/_service_description.html": "service.description_localized",
    "_service_slots_box.html": "chosen_resource.bio_localized",
    "sections/detail/_stay_description.html": "unit.description_localized",
    "stay_hausordnung.html": "settings.house_rules_localized",
    "event_detail.html": "event.description_text",
    "tour_detail.html": "tour.description_text",
    "lehrer_detail.html": "teacher.bio_localized",
    "blog_detail.html": "post.body_localized",
    "promotion_detail.html": "promotion.description_text",
    "combo_detail.html": "combo.description_localized",
    "legal.html": "legal_body",
}


@pytest.mark.parametrize(("tpl", "var"), STOREFRONT.items())
def test_storefront_long_texts_render_through_rich_block(tpl, var):
    src = (ROOT / "templates/storefront" / tpl).read_text()
    assert f"{{% rich_block {var}" in src
    # прежний вывод «как есть» в pre-line не остался рядом
    assert not re.search(r"whitespace-pre-line[^>]*>\{\{ " + re.escape(var) + r" \}\}", src)


#: кабинет: формы этих полей подключают редактор.
CABINET = [
    "catalog/category_form.html",
    "booking/service_page.html",
    "booking/resource_page.html",
    "stays/unit_page.html",
    "stays/stay_settings.html",
    "events/event_form.html",
    "events/tour_form.html",
    "events/teacher_form.html",
    "events/blog_new.html",
    "events/blog_edit.html",
    "promotions/promotion_form.html",
    "catalog/combo_form.html",
    "tenant/legal_docs.html",
]


@pytest.mark.parametrize("tpl", CABINET)
def test_cabinet_forms_include_editor(tpl):
    assert '{% include "catalog/_richtext_editor.html" %}' in (ROOT / "templates" / tpl).read_text()


def test_forms_mark_long_text_widgets_for_the_editor():
    from apps.events.forms import EventForm, TeacherForm, TourForm

    assert "data-rte" in EventForm.Meta.widgets["description"].attrs
    assert "data-rte" in TourForm.Meta.widgets["description"].attrs
    assert "data-rte" in TeacherForm.Meta.widgets["bio"].attrs
    assert 'data-rte="page"' in (ROOT / "templates/tenant/legal_docs.html").read_text()


def test_overlay_translation_of_long_text_is_sanitized(settings):
    from types import SimpleNamespace

    from apps.core.i18n_input import apply_i18n_overlay

    settings.LANGUAGE_CODE = "de"
    obj = SimpleNamespace(description_i18n={}, name_i18n={})
    tenant = SimpleNamespace(active_locales=["de", "en"])
    apply_i18n_overlay(
        obj, {"description_en": "<p>Hi<script>x</script></p>", "name_en": "<p>Tee</p>"}, tenant
    )
    assert obj.description_i18n["en"] == "<p>Hi</p>"
    assert obj.name_i18n["en"] == "<p>Tee</p>"  # имя — не длинный текст, не трогаем


def test_editor_never_puts_stored_value_raw_into_innerhtml():
    """Security-review M21.8: значение textarea идёт в редактор через белый список
    (DOMParser + копия разрешённых тегов), а не ``innerHTML = value``."""
    js = (ROOT / "templates/catalog/_richtext_editor.html").read_text()
    assert "DOMParser" in js and "function safeCopy" in js
    assert not re.search(r"area\.innerHTML\s*=\s*(v|ta\.value)", js)


def test_empty_text_keeps_canvas_anchor_only_with_edit_attrs():
    attrs = 'edit_model="event" edit_pk=7 edit_field="description"'
    out = _render("{% rich_block t " + attrs + " %}", t="")
    assert 'data-edit-field="description"' in out and out.endswith("></div>")
    assert _render("{% rich_block t %}", t="") == ""


def test_editor_saves_plain_text_as_text_and_empty_as_empty():
    js = (ROOT / "templates/catalog/_richtext_editor.html").read_text()
    assert "function value(area)" in js and "area.textContent" in js
    assert "ta.value = value(area)" in js
