"""Тесты витринной презентации архетипов (S2): сетка тизеров «Наши разделы».

`storefront.archetype_teasers` сводит активные архетипы реестра с оверрайдами
владельца (заголовок/описание/скрытие); `teaser_specs` — данные для формы
кабинета. Оверрайды живут в `site_config["archetypes"]`.
"""

from apps.tenants import siteconfig, storefront
from apps.tenants.tests.factories import TenantFactory


def _tenant(**kwargs):
    return TenantFactory.build(**kwargs)


def test_teasers_use_registry_defaults():
    teasers = storefront.archetype_teasers(_tenant())
    by_key = {t["key"]: t for t in teasers}
    assert "catalog" in by_key
    assert by_key["catalog"]["label"]  # дефолт из реестра
    assert by_key["catalog"]["url_name"] == "storefront-products"
    # Утилитарные (teaser=False) и без публичной страницы — не в сетке.
    assert "inbox" not in by_key
    assert "customer_account" not in by_key
    assert "promotions" not in by_key


def test_owner_override_label_and_blurb():
    tenant = _tenant(
        site_config={"archetypes": {"catalog": {"label": "Speisekarte", "blurb": "Frisch & vegan"}}}
    )
    by_key = {t["key"]: t for t in storefront.archetype_teasers(tenant)}
    assert by_key["catalog"]["label"] == "Speisekarte"
    assert by_key["catalog"]["blurb"] == "Frisch & vegan"


def test_hidden_archetype_dropped_from_grid():
    tenant = _tenant(site_config={"archetypes": {"booking": {"hidden": True}}})
    keys = [t["key"] for t in storefront.archetype_teasers(tenant)]
    assert "booking" not in keys
    assert "catalog" in keys


def test_disabled_module_not_in_teasers():
    tenant = _tenant(disabled_modules=["events"])
    keys = [t["key"] for t in storefront.archetype_teasers(tenant)]
    assert "events" not in keys


def test_teaser_specs_for_cabinet_form():
    tenant = _tenant(site_config={"archetypes": {"catalog": {"label": "Speisekarte"}}})
    by_key = {s["key"]: s for s in storefront.teaser_specs(tenant)}
    cat = by_key["catalog"]
    assert cat["default_label"]  # дефолт реестра для placeholder
    assert cat["label"] == "Speisekarte"  # текущий оверрайд
    assert cat["visible"] is True
    # Скрытый архетип всё равно в форме (чекбокс «показывать» снят).
    tenant2 = _tenant(site_config={"archetypes": {"catalog": {"hidden": True}}})
    cat2 = {s["key"]: s for s in storefront.teaser_specs(tenant2)}["catalog"]
    assert cat2["visible"] is False


def test_archetypes_section_in_registry_default_off():
    cfg = siteconfig.normalize({})
    section = {s["key"]: s for s in cfg["sections"]}["archetypes"]
    assert section["enabled"] is False  # легаси не затронут


def test_normalize_sanitizes_archetype_overrides():
    cfg = siteconfig.normalize(
        {"archetypes": {"catalog": {"label": "X", "blurb": 5, "hidden": "yes"}, "bad": "nope"}}
    )
    # S3 добавил поля обложки (intro/hero_image) — пустые по умолчанию.
    assert cfg["archetypes"]["catalog"] == {
        "label": "X",
        "blurb": "",
        "hidden": True,
        "intro": "",
        "hero_image": "",
        "gallery": [],
    }
    assert "bad" not in cfg["archetypes"]  # значение не-dict отброшено
