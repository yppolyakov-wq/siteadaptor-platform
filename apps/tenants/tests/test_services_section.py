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


def _fake_service(pk, name, minutes, cents, description="", image_url=""):
    """Фейк услуги с интерфейсом контракта SellableEntity (UB1-2): карточка секции
    рендерится через sellable_card → адаптеру нужны name_localized/
    description_localized(locale) и image_url — как у booking.Service."""
    return SimpleNamespace(
        pk=pk,
        name=name,
        description=description,
        image_url=image_url,
        duration_minutes=minutes,
        price_cents=cents,
        price_eur=cents / 100,
        name_localized=lambda locale=None: name,
        description_localized=lambda locale=None: description,
    )


def test_services_section_renders_cards(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    services = [
        _fake_service("11111111-1111-1111-1111-111111111111", "Waschen & Schneiden", 45, 3900),
        _fake_service("22222222-2222-2222-2222-222222222222", "Schnupperstunde", 30, 0),
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
    return _fake_service("33333333-3333-3333-3333-333333333333", "Ölwechsel", 30, 4900)


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


def test_services_section_shows_description(settings):
    """A3: богатая карточка услуги — описание рендерится при наличии."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    svc = _fake_service(
        "44444444-4444-4444-4444-444444444444",
        "Ölwechsel",
        30,
        4900,
        description="Inkl. Öl, Filter und Entsorgung.",
    )
    html = render_to_string(
        "storefront/sections/_services.html",
        {"site": {}, "services_preview": [svc], "request": _req()},
    )
    assert "Inkl. Öl, Filter und Entsorgung." in html


def test_services_section_shows_photo(settings):
    """A3: богатая карточка услуги — фото рендерится при наличии image_url."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    svc = _fake_service(
        "55555555-5555-5555-5555-555555555555",
        "Färben",
        90,
        6900,
        image_url="https://img.example/haircolor.jpg",
    )
    html = render_to_string(
        "storefront/sections/_services.html",
        {"site": {}, "services_preview": [svc], "request": _req()},
    )
    assert "https://img.example/haircolor.jpg" in html


def test_services_section_no_photo_without_image(settings):
    """Регрессия: без image_url карточка без <img> (как раньше)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    svc = _fake_service("66666666-6666-6666-6666-666666666666", "Bart", 15, 1200)
    html = render_to_string(
        "storefront/sections/_services.html",
        {"site": {}, "services_preview": [svc], "request": _req()},
    )
    assert "<img" not in html
