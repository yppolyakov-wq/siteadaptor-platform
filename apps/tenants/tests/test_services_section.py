"""Спринт A / A3: блок «Leistungen & Preise» (services) на главной витрины."""

from types import SimpleNamespace

from django.template.loader import render_to_string

from apps.tenants import siteconfig


def test_services_in_section_registry_disabled_by_default():
    keys = {key for key, _label, _on in siteconfig.SECTIONS}
    assert "services" in keys
    default = {s["key"]: s["enabled"] for s in siteconfig.default_sections()}
    assert default["services"] is False  # показываем только при booking + услугах


def test_services_is_grid_section_with_title_and_viewall():
    # раскладка/заголовок/«View all» работают как у прочих primary-секций
    assert "services" in siteconfig.GRID_SECTION_DEFAULTS
    assert "services" in siteconfig.SECTION_TITLE_KEYS
    assert "services" in siteconfig.SECTION_VIEWALL_KEYS


def _req():
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build(name="Salon Lea")
    return request


def test_services_section_renders_cards(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    services = [
        SimpleNamespace(
            pk="11111111-1111-1111-1111-111111111111",
            name="Waschen & Schneiden",
            duration_minutes=45,
            price_cents=3900,
            price_eur=39.0,
        ),
        SimpleNamespace(
            pk="22222222-2222-2222-2222-222222222222",
            name="Schnupperstunde",
            duration_minutes=30,
            price_cents=0,
            price_eur=0.0,
        ),
    ]
    html = render_to_string(
        "storefront/sections/_services.html",
        {"site": {}, "services_preview": services, "request": _req()},
    )
    assert "Waschen &amp; Schneiden" in html
    assert "39,00" in html or "39.00" in html  # цена платной услуги
    assert "45 min" in html
    assert "Jetzt buchen" in html  # CTA (purchase_label booking)


def test_services_section_empty_when_no_services():
    html = render_to_string(
        "storefront/sections/_services.html",
        {"site": {}, "services_preview": [], "request": _req()},
    )
    assert html.strip() == ""  # пустой блок не рендерится


def _priced_service():
    return SimpleNamespace(
        pk="33333333-3333-3333-3333-333333333333",
        name="Ölwechsel",
        duration_minutes=30,
        price_cents=4900,
        price_eur=49.0,
    )


def test_services_section_shows_festpreis_for_trades(settings):
    """A9/A7: при services_festpreis (модуль jobs) у платной услуги — пометка Festpreis."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    html = render_to_string(
        "storefront/sections/_services.html",
        {
            "site": {},
            "services_preview": [_priced_service()],
            "services_festpreis": True,
            "request": _req(),
        },
    )
    assert "Fixed price" in html  # пометка Festpreis


def test_services_section_no_festpreis_without_flag(settings):
    """Регрессия: без флага (напр. Friseur) пометки Festpreis нет."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    html = render_to_string(
        "storefront/sections/_services.html",
        {"site": {}, "services_preview": [_priced_service()], "request": _req()},
    )
    assert "Fixed price" not in html
