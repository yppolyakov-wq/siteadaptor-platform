"""MA-L (2026-11-02, фидбэк Mini App): нижние слои витрины на телефоне.

Панель покупки детали стояла bottom-0 под нижним меню (z-40) — кнопка покупки
пряталась за меню; плавающие кнопки ложились на панель и на ссылки права в подвале.
Высоты слоёв задаёт app.css по data-атрибутам — замок, что атрибуты и правила на месте.
"""

from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR)


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_layer_hooks_present_in_templates():
    assert "data-sf-bottom-nav" in _read("templates/storefront/_action_bar.html")
    assert "data-buybar" in _read("templates/storefront/_detail_buybar.html")
    assert "data-sf-presence" in _read("templates/storefront/_presence_fab.html")
    base = _read("templates/storefront/_base.html")
    assert "data-sf-footer-inner" in base and "data-chat-fab" in base


def test_built_css_lifts_buybar_above_bottom_nav():
    css = _read("static/css/app.css")
    assert "[data-buybar]{bottom:var(--sf-nav-h" in css
    assert "[data-sf-footer-inner]{padding-bottom:" in css
    assert "[data-chat-fab]" in css and "[data-sf-presence]" in css
