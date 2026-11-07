"""FB-19: поле «Stadt» — подсказки городов и каноническое написание (поле остаётся текстом)."""

import pytest
from django import forms

from apps.core import cities


def test_canonical_fixes_case_umlauts_and_spaces():
    assert cities.canonical("köln") == "Köln"
    assert cities.canonical("  duesseldorf ") == "Düsseldorf"
    assert cities.canonical("MUENCHEN") == "München"


def test_unknown_city_is_kept_as_typed():
    assert cities.canonical("Kleinkleckersdorf  Ost") == "Kleinkleckersdorf Ost"
    assert cities.canonical("") == ""


def test_suggestions_have_region_first_and_no_duplicates():
    names = cities.suggestions()
    assert "Solingen" in names[:25] and "Haan" in names and "Wien" in names
    assert len({cities._key(n) for n in names}) == len(names)


def test_widget_renders_input_with_its_own_datalist():
    class F(forms.Form):
        city = forms.CharField(widget=cities.CityInput)

    html = str(F()["city"])
    assert 'list="id_city-cities"' in html and '<datalist id="id_city-cities">' in html
    assert '<option value="Köln">' in html and 'autocomplete="address-level2"' in html


@pytest.mark.django_db
def test_settings_and_signup_forms_canonicalize_the_city():
    from apps.tenants.forms import BusinessSignupForm

    form = BusinessSignupForm(data={"city": "frankfurt am main"})
    form.is_valid()
    assert form.cleaned_data.get("city") == "Frankfurt am Main"
