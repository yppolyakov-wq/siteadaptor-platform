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
    "tenant/legal_page_form.html",
]


@pytest.mark.parametrize("tpl", CABINET)
def test_cabinet_forms_include_editor(tpl):
    assert '{% include "catalog/_richtext_editor.html" %}' in (ROOT / "templates" / tpl).read_text()


def test_forms_mark_long_text_widgets_for_the_editor():
    from apps.events.forms import EventForm, TeacherForm, TourForm

    assert "data-rte" in EventForm.Meta.widgets["description"].attrs
    assert "data-rte" in TourForm.Meta.widgets["description"].attrs
    assert "data-rte" in TeacherForm.Meta.widgets["bio"].attrs
    assert 'data-rte="page"' in (ROOT / "templates/tenant/legal_page_form.html").read_text()


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


# --- B4: картинка с компьютера, по центру, две колонки -------------------------------


def _png_upload(name="bild.png"):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _upload_req(files, user=None):
    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    req = RequestFactory().post("/dashboard/site/seiten/bild/", files)
    req.user = user or AnonymousUser()
    req.tenant = TenantFactory.build(schema_name="public", slug="b4", name="B4")
    return req


@pytest.mark.django_db
def test_page_image_upload_saves_local_image_and_needs_login(settings):
    from django.contrib.auth import get_user_model

    from apps.core.content_page_views import page_image_upload
    from apps.core.richtext import sanitize_page

    settings.ROOT_URLCONF = "config.urls_tenant"
    anon = page_image_upload(_upload_req({"image": _png_upload()}))
    assert anon.status_code == 302  # без входа — на логин

    user = get_user_model().objects.create_user(username="b4-owner", password="pw1234567")
    resp = page_image_upload(_upload_req({"image": _png_upload()}, user))
    import json

    url = json.loads(resp.content)["url"]
    assert resp.status_code == 200 and url.startswith(settings.MEDIA_URL)
    # адрес проходит санитайзер страниц — картинка не пропадёт при сохранении
    assert url in sanitize_page(f'<p><img src="{url}" alt=""></p>')

    from django.core.files.uploadedfile import SimpleUploadedFile

    fake = SimpleUploadedFile("x.png", b"kein bild", content_type="image/png")
    bad = page_image_upload(_upload_req({"image": fake}, user))
    assert b"error" in bad.content
    assert bad.status_code == 400


def test_page_image_upload_has_write_rule_and_route():
    from django.urls import reverse

    from apps.core import view_perms

    assert view_perms.RULES["content-page-image"] == view_perms._r(view_perms.WE, view_perms.WE)
    assert reverse("content-page-image", urlconf="config.urls_tenant").endswith("/seiten/bild/")


@pytest.mark.django_db
def test_media_library_keeps_images_used_inside_pages_and_legal_texts():
    """Картинка в тексте страницы/правового документа занята — медиатека её не удалит."""
    from django.conf import settings

    from apps.core import media_registry
    from apps.core.models import ContentPage, LegalDoc

    m = settings.MEDIA_URL
    ContentPage.objects.create(
        slug="versand", title="Versand", body=f'<p><img src="{m}pages/a.webp" alt=""></p>'
    )
    LegalDoc.objects.create(kind="impressum", locale="de", text=f'<img src="{m}pages/b.webp">')
    used = media_registry.used_paths()
    assert {"pages/a.webp", "pages/b.webp"} <= used


def test_columns_and_center_survive_the_page_sanitizer():
    from apps.core.richtext import sanitize_page

    html = (
        '<div class="sf-grid"><div class="sf-col-8"><p>A</p></div>'
        '<div class="sf-col-8"><p class="sf-center">B</p></div></div>'
    )
    assert sanitize_page(html) == html
    out = _render('{% rich_block t mode="page" %}', t=html)
    assert 'class="sf-grid"' in out and 'class="sf-center"' in out


def test_editor_has_upload_center_and_columns_in_page_mode():
    js = (ROOT / "templates/catalog/_richtext_editor.html").read_text()
    for marker in ('"center"', '"columns"', "function pickAndUpload", "data-rte-status"):
        assert marker in js, marker
    form = (ROOT / "templates/tenant/content_page_form.html").read_text()
    assert "data-rte-upload=\"{% url 'content-page-image' %}\"" in form


@pytest.mark.django_db
def test_page_image_upload_strips_exif(settings):
    import io
    import json

    from django.contrib.auth import get_user_model
    from django.core.files.storage import default_storage
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from apps.core.content_page_views import page_image_upload

    settings.ROOT_URLCONF = "config.urls_tenant"
    img = Image.new("RGB", (16, 16), "blue")
    exif = Image.Exif()
    exif[0x010F] = "Telefon-Hersteller"  # Make
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    up = SimpleUploadedFile("foto.jpg", buf.getvalue(), content_type="image/jpeg")
    user = get_user_model().objects.create_user(username="b4-exif", password="pw1234567")
    url = json.loads(page_image_upload(_upload_req({"image": up}, user)).content)["url"]
    path = url[len(settings.MEDIA_URL) :]
    with default_storage.open(path) as fh, Image.open(fh) as saved:
        assert not saved.getexif()
