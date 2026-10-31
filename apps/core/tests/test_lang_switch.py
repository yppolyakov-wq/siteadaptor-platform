"""E9.10: один переключатель языка ввода на ВСЕХ экранах кабинета с переводами.

Фидбэк владельца 2026-10-31: «проверь весь функционал и переделай так, чтоб было
одинаково везде». Было три механики: пилюли в форме товара/акции, свёрнутые
«🌐 Translations» у услуги/номера/типа акции и все языки сразу у набора и
правовых текстов. Стало: выпадашка с кодом языка рядом с заголовком страницы
(`{% lang_switch %}` → `tenant/_i18n_switch.html`), поля языков —
`[data-i18n-loc]`, видна группа выбранного языка.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

TEMPLATES = Path(settings.BASE_DIR) / "templates"

#: Где переводы вводятся своим механизмом (Studio — язык канвы ?clang=;
#: мастер — data-loc-pane со своей выпадашкой; витрина — не кабинет).
_OWN_MECHANISM = ("storefront/", "tenant/setup", "tenant/site_home.html", "tenants/")

#: Признаки поля перевода в разметке.
_LOCALE_INPUT = re.compile(
    r'name="\w+_\{\{ *(?:loc|inp\.locale|cell\.locale|p\.loc) *\}\}"'
    r"|name=\"\{\{ *inp\.input_name *\}\}\""
    r"|\bi18n_groups\b|overlay_i18n_inputs|\|i18n_loc\b|data-i18n-loc="
    r"|tenant/_i18n_(?:row|inline)\.html"
)


def _cabinet_templates():
    for path in TEMPLATES.rglob("*.html"):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel.startswith(_OWN_MECHANISM) or rel.startswith("tenant/_"):
            continue
        yield rel, path.read_text(encoding="utf-8")


def _includes(rel: str, text: str) -> str:
    """Текст шаблона + прямо подключённые партиалы (одного уровня достаточно)."""
    out = [text]
    for inc in re.findall(r'{% include "([^"]+)"', text):
        p = TEMPLATES / inc
        if p.exists():
            out.append(p.read_text(encoding="utf-8"))
    return "\n".join(out)


def test_every_screen_with_translations_has_the_language_dropdown():
    missing = []
    for rel, text in _cabinet_templates():
        if "{% extends" not in text or not _LOCALE_INPUT.search(_includes(rel, text)):
            continue
        if "{% lang_switch %}" not in text and "tenant/_i18n_switch.html" not in text:
            missing.append(rel)
    assert not missing, f"Поля переводов без выпадашки языка у заголовка: {missing}"


def test_no_old_collapsed_translation_blocks_left():
    bad = [
        rel
        for rel, text in _cabinet_templates()
        if re.search(r"🌐 *{% trans ['\"]Translations['\"] %}", text)
    ]
    assert not bad, f"Остались свёрнутые «🌐 Translations» вместо выпадашки: {bad}"


def _render_switch(locales):
    tenant = TenantFactory.build(enabled_locales=locales, default_locale=locales[0])
    request = RequestFactory().get("/")
    request.tenant = tenant
    tpl = Template("{% load cabinet %}{% lang_switch %}")
    return tpl.render(Context({"request": request}))


def test_lang_switch_builds_groups_from_tenant_and_shows_codes_only():
    html = _render_switch(["de", "en", "ru"])
    assert "<select data-i18n-select" in html
    for code in ("de", "en", "ru"):
        assert f'<option value="{code}" title=' in html
        assert f">{code}</option>" in html
    assert "🌐" not in html.split("<style>")[0]
    assert '<option value="de" title="Deutsch" selected>' in html


def test_lang_switch_renders_nothing_for_single_language():
    assert "<select" not in _render_switch(["de"])


# --- OverlayI18nFormMixin: событие / тур / ведущий -----------------------------


@pytest.mark.django_db
def test_event_form_adds_translation_fields_and_saves_overlay():
    from apps.events.forms import EventForm
    from apps.events.models import Event

    tenant = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    form = EventForm()
    form.init_overlay_i18n(tenant)
    assert "title_en" in form.fields and "description_en" in form.fields
    names = list(form.fields)
    # перевод стоит сразу за своим базовым полем
    assert names.index("title_en") == names.index("title") + 1
    assert form.fields["title"].i18n_loc == "de"
    assert form.fields["title_en"].i18n_loc == "en"

    event = Event(title="Yoga", description="", title_i18n={"en": "Old"})
    bound = EventForm(instance=event)
    bound.init_overlay_i18n(tenant)
    assert bound.fields["title_en"].initial == "Old"


@pytest.mark.django_db
def test_overlay_mixin_presence_guard_and_clear():
    from apps.events.forms import TeacherForm
    from apps.events.models import Teacher

    tenant = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    teacher = Teacher(
        name="Anna", title="Lehrerin", title_i18n={"en": "Teacher"}, bio_i18n={"en": "x"}
    )
    data = {"name": "Anna", "title": "Lehrerin", "title_en": "  ", "is_active": "on"}
    form = TeacherForm(data, instance=teacher)
    form.init_overlay_i18n(tenant)
    assert form.is_valid(), form.errors
    # пустой перевод удалён, поле не из POST (bio_en) — не тронуто
    assert teacher.title_i18n == {}
    assert teacher.bio_i18n == {"en": "x"}


@pytest.mark.django_db
def test_overlay_mixin_is_inert_for_single_language():
    from apps.events.forms import TeacherForm

    tenant = TenantFactory.build(enabled_locales=["de"], default_locale="de")
    form = TeacherForm()
    form.init_overlay_i18n(tenant)
    assert not [n for n in form.fields if n.endswith("_en")]


# --- E9.10b: переводы оставшихся текстов --------------------------------------


@pytest.mark.django_db
def test_row_translations_save_only_overlays_with_presence_guard():
    from apps.core.i18n_input import save_row_translations
    from apps.core.models import Extra

    tenant = TenantFactory.build(enabled_locales=["de", "en", "ru"], default_locale="de")
    extra = Extra.objects.create(label="Frühstück", price_cents=1200, label_i18n={"ru": "Завтрак"})
    assert save_row_translations(extra, {"label_en": " Breakfast "}, tenant, ("label",))
    extra.refresh_from_db()
    # en записан, ru (нет в POST) не тронут, база не тронута
    assert extra.label_i18n == {"en": "Breakfast", "ru": "Завтрак"}
    assert extra.label == "Frühstück"
    assert not save_row_translations(extra, {}, tenant, ("label",))


@pytest.mark.django_db
def test_product_form_renders_translations_next_to_material():
    from django.template.loader import render_to_string

    from apps.catalog.forms import ProductForm

    tenant = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    form = ProductForm(tenant=tenant)
    assert {"material_en", "care_en", "condition_note_en"} <= set(form.fields)
    html = render_to_string("catalog/_pf_field.html", {"field": form["material"]})
    assert 'data-i18n-loc="de"' in html and 'data-i18n-loc="en" class="hidden"' in html
    assert 'name="material_en"' in html


@pytest.mark.django_db
def test_category_form_size_table_translation_saved():
    from apps.catalog.forms import CategoryForm
    from apps.catalog.models import Category

    tenant = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    cat = Category.objects.create(name={"de": "Hosen"}, size_table="S | 36")
    form = CategoryForm(instance=cat, tenant=tenant)
    assert "size_table_en" in form.fields


@pytest.mark.django_db
def test_i18n_inputs_tag_labels_and_multiline():
    from apps.booking.models import Resource

    tenant = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    request = RequestFactory().get("/")
    request.tenant = tenant
    res = Resource(name="Anna", title="Stylistin", bio="", bio_i18n={"en": "Hi"})
    html = Template(
        '{% load cabinet %}{% include "tenant/_i18n_inline.html" with obj=r fields="name,bio" %}'
    ).render(Context({"request": request, "r": res}))
    assert 'name="name_en"' in html and 'textarea name="bio_en"' in html and ">Hi<" in html
    assert 'data-i18n-loc="en" class="hidden' in html
