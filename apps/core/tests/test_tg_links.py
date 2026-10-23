"""Фидбэк 2026-10-23: в Mini App «Anrufen» не делал ничего — Telegram не открывает
tel:/mailto: из своего окна. И витрина, и кабинет перехватывают такие ссылки."""

from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR) / "templates"


def test_storefront_handles_tel_links_inside_telegram():
    body = (ROOT / "storefront" / "_base.html").read_text()
    assert "tg.showPopup" in body and "(tel|mailto)" in body and "tg.openLink" in body
    assert 'id="tg-link-labels"' in body


def test_cabinet_bridge_handles_tel_links_inside_telegram():
    body = (ROOT / "tenant" / "_tg_shim.html").read_text()
    assert "web_app_open_popup" in body and "(tel|mailto)" in body
    assert "web_app_open_link" in body and "popup_closed" in body
