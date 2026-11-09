"""FB-26: «Was verkaufen Sie?» при регистрации.

Решения владельца 2026-11-08: направления — первым вопросом и ОБЯЗАТЕЛЬНО (без них не
понять, отель это или магазин); ниша — вторым, по желанию; у ниши — «Demo ansehen».
Замки: без направлений форма не проходит; пустая ниша выводится из направлений только
однозначно; модули следуют направлениям; ответ доезжает в состояние мастера и в
SignupRequest; страница рисует чипы до ниши.
"""

import pytest
from django.test import RequestFactory

from apps.tenants import services, signup_directions, views
from apps.tenants.forms import BusinessSignupForm

pytestmark = pytest.mark.django_db

BASE = {
    "business_name": "Haus am See",
    "slug": "fb26-haus",
    "city": "Hilden",
    "email": "owner@fb26.test",
    "password1": "Wolke-Zimt-7x9q",
    "password2": "Wolke-Zimt-7x9q",
}


def _form(**kw):
    return BusinessSignupForm(data={**BASE, **kw})


def test_directions_are_required():
    form = _form(business_type="hotel")
    assert not form.is_valid() and "directions" in form.errors


def test_niche_is_optional_and_inferred_only_when_unambiguous():
    form = _form(directions=["zimmer"])
    assert form.is_valid(), form.errors
    assert form.cleaned_data["business_type"] == "hotel"
    form = _form(directions=["gastro", "waren"])
    assert form.is_valid() and form.cleaned_data["business_type"] == "restaurant"
    # Termine: салон? мастерская? — не угадываем.
    form = _form(directions=["termine"])
    assert form.is_valid() and form.cleaned_data["business_type"] == "other"
    # Выбранная ниша сильнее вывода.
    form = _form(directions=["zimmer"], business_type="events")
    assert form.is_valid() and form.cleaned_data["business_type"] == "events"


def test_unknown_chips_are_rejected():
    form = _form(directions=["waren", "evil"])
    assert not form.is_valid() and "directions" in form.errors


def test_modules_follow_directions():
    chosen = signup_directions.directions_for("hotel", ["termine"])
    disabled = set(signup_directions.disabled_modules("hotel", chosen))
    assert "stays" in disabled  # номера не отмечены — модуль выключен
    assert "booking" not in disabled
    chosen = signup_directions.directions_for("other", ["zimmer", "anfragen"])
    disabled = set(signup_directions.disabled_modules("other", chosen))
    assert not {"stays", "jobs"} & disabled
    assert {"booking", "events"} <= disabled


def test_gastro_chip_expands_by_type():
    assert signup_directions.directions_for("restaurant", ["gastro"]) == ["speisekarte", "tisch"]
    # Кейтерингу столы неуместны — остаётся меню.
    assert signup_directions.directions_for("catering", ["gastro"]) == ["speisekarte"]


def test_new_tenant_carries_choice_into_wizard_state():
    tenant = services._new_tenant(
        business_name="X",
        slug="fb26-x",
        business_type="other",
        city="Hilden",
        email="x@fb26.test",
        wizard_v4=True,
        directions=["zimmer", "anfragen"],
    )
    state = tenant.site_config["onboarding"]
    assert state["directions"] == ["zimmer", "anfragen"] and state["flow"] == "v4"
    assert "stays" not in tenant.disabled_modules


def test_signup_request_stores_directions(settings):
    from importlib import import_module

    from apps.tenants.models import SignupRequest

    settings.SIGNUP_EMAIL_CONFIRMATION = True
    settings.ROOT_URLCONF = "config.urls_public"
    request = RequestFactory().post(
        "/registrieren/", {**BASE, "directions": ["zimmer"]}, REMOTE_ADDR="10.26.0.1"
    )
    request.session = import_module(settings.SESSION_ENGINE).SessionStore()
    views.BusinessSignupView.as_view()(request)
    req = SignupRequest.objects.get(email=BASE["email"])
    assert req.directions == ["zimmer"] and req.business_type == "hotel"


def test_page_asks_directions_before_niche(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    request = RequestFactory().get("/registrieren/")
    request.session = {}
    html = views.BusinessSignupView.as_view()(request).content.decode()
    assert html.index('name="directions"') < html.index('name="business_type"')
    for key in signup_directions.KEYS:
        assert f'value="{key}"' in html
    assert 'data-chips="zimmer"' in html  # ниша «Hotel» знает свой чип (фильтр на странице)


def test_preselected_niche_prefills_chips(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    request = RequestFactory().get("/registrieren/?type=restaurant")
    request.session = {}
    html = views.BusinessSignupView.as_view()(request).content.decode()
    assert 'value="gastro" checked' in html


def test_old_online_chip_still_understood_but_no_longer_offered():
    """SHP (2026-11-09): «в лавке» и «онлайн с доставкой» — один пункт «Waren» (способы
    получения спрашивает мастер). Новая форма «online» не принимает; старые заявки с ним
    по-прежнему включают заказы и выводят тип online_shop."""
    assert not _form(directions=["online"]).is_valid()
    assert signup_directions.clean(["online"]) == ["online"]
    assert signup_directions.resolve_type("", ["online"]) == "online_shop"
    chosen = signup_directions.directions_for("retail", ["online"])
    assert chosen == ["waren"]
    assert "orders" not in signup_directions.disabled_modules("retail", chosen, online=True)
    assert "orders" in signup_directions.disabled_modules("other", ["waren"])
    assert signup_directions.initial_for("online_shop") == ["waren"]


def test_page_shows_examples_for_every_choice(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    request = RequestFactory().get("/registrieren/")
    request.session = {}
    html = views.BusinessSignupView.as_view()(request).content.decode()
    assert "Spielzeug" in html and "Drogerie" in html  # «любые товары», не только еда
    assert 'value="online"' not in html  # SHP: один пункт «Waren verkaufen»
    for chip in signup_directions.CHOICES:
        assert str(chip[4]) in html
