"""Двуязычная витрина (i18n): платформенный механизм оверлеев site_config.

Базовая локаль — немецкий (значения-строки, как раньше). Переводы других локалей
живут в config["i18n"][locale] и накладываются siteconfig.localize() перед рендером.
Механизм есть у любого тенанта; реальные переводы сидятся демо-китом (pranasy).
"""

from apps.tenants import siteconfig


def test_normalize_preserves_only_supported_locale_overlays():
    cfg = siteconfig.normalize(
        {
            "hero_title": "Hallo",
            "i18n": {
                "en": {"hero_title": "Hello"},
                "fr": {"hero_title": "Bonjour"},  # неподдерживаемая → отброшена
                "de": {"hero_title": "x"},  # базовая локаль не оверлеится
                "bad": "nope",
            },
        }
    )
    assert cfg["i18n"] == {"en": {"hero_title": "Hello"}}


def test_normalize_no_i18n_key_when_empty():
    # Легаси-конфиг без переводов: ключ i18n не появляется (нулевая регрессия).
    cfg = siteconfig.normalize({"hero_title": "Hallo"})
    assert "i18n" not in cfg


def test_localize_de_returns_base_without_i18n_key():
    cfg = siteconfig.normalize({"hero_title": "Hallo", "i18n": {"en": {"hero_title": "Hello"}}})
    de = siteconfig.localize(cfg, "de")
    assert de["hero_title"] == "Hallo"
    assert "i18n" not in de  # служебный ключ не утекает в шаблон


def test_localize_en_overlays_scalar_text():
    cfg = siteconfig.normalize(
        {
            "hero_title": "Frisch",
            "about_text": "Vegan",
            "i18n": {"en": {"hero_title": "Fresh"}},
        }
    )
    en = siteconfig.localize(cfg, "en")
    assert en["hero_title"] == "Fresh"
    assert en["about_text"] == "Vegan"  # без перевода → базовое DE-значение (фолбэк)
    assert "i18n" not in en


def test_localize_does_not_mutate_input():
    cfg = siteconfig.normalize({"hero_title": "Frisch", "i18n": {"en": {"hero_title": "Fresh"}}})
    siteconfig.localize(cfg, "en")
    assert cfg["hero_title"] == "Frisch"  # вход не тронут
    assert cfg["i18n"]["en"]["hero_title"] == "Fresh"


def test_localize_overlays_section_titles_dict():
    cfg = siteconfig.normalize(
        {
            "section_titles": {"products": "Karte", "events": "Termine"},
            "i18n": {"en": {"section_titles": {"products": "Menu"}}},
        }
    )
    en = siteconfig.localize(cfg, "en")
    assert en["section_titles"]["products"] == "Menu"
    assert en["section_titles"]["events"] == "Termine"  # фолбэк на DE


def test_localize_overlays_heroes_list_positionally():
    cfg = siteconfig.normalize(
        {
            "heroes": [
                {"image": "a.jpg", "title": "Eins", "text": "T1"},
                {"image": "b.jpg", "title": "Zwei", "text": "T2"},
            ],
            "i18n": {"en": {"heroes": [{"title": "One"}, {"title": "Two", "text": "T2en"}]}},
        }
    )
    en = siteconfig.localize(cfg, "en")
    assert en["heroes"][0]["title"] == "One"
    assert en["heroes"][0]["text"] == "T1"  # не переведено → DE
    assert en["heroes"][1]["title"] == "Two"
    assert en["heroes"][1]["text"] == "T2en"
    assert en["heroes"][0]["image"] == "a.jpg"  # картинка общая


def test_localize_overlays_faq_pairs():
    cfg = siteconfig.normalize(
        {
            "faq": [{"q": "Vegan?", "a": "Ja"}],
            "i18n": {"en": {"faq": [{"q": "Vegan?", "a": "Yes"}]}},
        }
    )
    en = siteconfig.localize(cfg, "en")
    assert en["faq"][0]["a"] == "Yes"


def test_localize_overlay_extra_list_items_ignored():
    # Оверлей длиннее базы: лишние элементы не плодят секций.
    cfg = siteconfig.normalize(
        {
            "heroes": [{"image": "a.jpg", "title": "Eins"}],
            "i18n": {"en": {"heroes": [{"title": "One"}, {"title": "Ghost"}]}},
        }
    )
    en = siteconfig.localize(cfg, "en")
    assert len(en["heroes"]) == 1
    assert en["heroes"][0]["title"] == "One"


def test_localize_unknown_locale_falls_back_to_base():
    cfg = siteconfig.normalize({"hero_title": "Hallo", "i18n": {"en": {"hero_title": "Hello"}}})
    assert siteconfig.localize(cfg, "fr")["hero_title"] == "Hallo"
    assert siteconfig.localize(cfg, None)["hero_title"] == "Hallo"
