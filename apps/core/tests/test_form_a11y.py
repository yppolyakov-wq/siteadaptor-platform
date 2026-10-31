"""KA-12 E9.4c: ошибки и подсказки полей связаны с виджетом (aria-describedby)."""

import re
from pathlib import Path

from django import forms
from django.conf import settings
from django.template.loader import render_to_string

from apps.core.templatetags.form_a11y import a11y, describedby_ids

TEMPLATES = Path(settings.BASE_DIR) / "templates"


class _Form(forms.Form):
    name = forms.CharField(help_text="Hilfe")
    city = forms.CharField()


def _bound(data):
    form = _Form(data=data)
    form.is_valid()
    return form


def _ids(html):
    return set(re.findall(r'\bid="([^"]+)"', html))


def _described(html):
    out = set()
    for val in re.findall(r'aria-describedby="([^"]+)"', html):
        out.update(val.split())
    return out


def test_filter_links_errors_and_keeps_help():
    form = _bound({})
    assert describedby_ids(form["name"]) == "id_name_helptext id_name_errors"
    assert describedby_ids(form["city"]) == "id_city_errors"
    a11y(form["name"])
    html = str(form["name"])
    assert 'aria-describedby="id_name_helptext id_name_errors"' in html
    assert 'aria-invalid="true"' in html


def test_filter_leaves_valid_field_to_django():
    form = _bound({"name": "x", "city": "y"})
    a11y(form["city"])
    assert "aria-describedby" not in str(form["city"])


def test_shared_partials_render_every_referenced_id():
    """Каждый id из aria-describedby существует на странице (без висячих ссылок)."""
    form = _bound({})
    for tpl in ("tenant/_settings_field.html", "catalog/_pf_field.html", "crm/_form_field.html"):
        for name in ("name", "city"):
            html = render_to_string(tpl, {"field": form[name]})
            referenced = _described(html)
            assert referenced, (tpl, name)
            assert referenced <= _ids(html), (tpl, name, referenced - _ids(html))


def test_valid_field_help_reference_resolves():
    form = _bound({"name": "x", "city": "y"})
    html = render_to_string("tenant/_settings_field.html", {"field": form["name"]})
    assert _described(html) == {"id_name_helptext"} <= _ids(html)


_FIELD_ERR_LOOP = re.compile(r"\{% for \w+ in (?!form\.non_field_errors)[\w.]+\.errors %\}")


def test_cabinet_field_error_loops_have_container_id():
    """Замок: цикл ошибок поля в кабинете обёрнут в блок с id «…_errors»."""
    skip = ("storefront/", "account/", "aggregator/", "email", "pdf/", "public/", "platform/")
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel.startswith(skip) or rel in _LEGACY:
            continue
        text = path.read_text()
        for m in _FIELD_ERR_LOOP.finditer(text):
            before = text[max(0, m.start() - 120) : m.start()]
            if "_errors" not in before:
                offenders.append(rel)
    assert not offenders, sorted(set(offenders))


# Не поля формы: ошибки строки импорта и предпросмотра цен — список, а не ошибка поля.
_LEGACY = {
    "imports/import_preview.html",
    "stays/_price_preview.html",
}


def test_static_describedby_targets_exist_in_template():
    """Литеральные id в aria-describedby (без шаблонных выражений) объявлены в том же шаблоне."""
    dangling = []
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text()
        ids = set(re.findall(r'\bid="([^"{}]+)"', text))
        for val in re.findall(r'aria-describedby="((?:[^"{]|\{\{.*?\}\}|\{%.*?%\})+)"', text):
            val = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "§", val)
            for ref in val.split():
                if "§" in ref:
                    continue
                if ref not in ids:
                    dangling.append((path.relative_to(TEMPLATES).as_posix(), ref))
    assert not dangling, dangling
