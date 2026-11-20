"""FB-33 M3-5b: части окна блока «Seitenaufbau» — вопросы FAQ («Texte») и плашки
Schnellzugriff («Was»). Только модель для шаблона: пишут `faq_content` (черновик —
`aufbau_draft`) и данные блока `quick_links` (`hero_tiles.update_data`)."""

from __future__ import annotations


def _item(config: dict, home: bool, host: str, ref: str) -> dict:
    from apps.core import site_schema

    try:
        items = site_schema.load_items(config, home, host)
    except Exception:  # noqa: BLE001 — окно без части лучше, чем упавший экран
        return {}
    return next((it for it in items if isinstance(it, dict) and it.get("id") == ref), {})


def decorate(
    selected: dict | None, saved: dict, draft: dict | None, home: bool, config: dict, host: str
) -> None:
    """Дополнить выбранную строку частями среза. `saved` — сохранённый конфиг (вопросы
    черновика и их источники — из `draft`), `config` — показанный (с черновиком)."""
    if not selected:
        return
    from apps.core import aufbau_draft, faq_content, hero_tiles
    from apps.tenants import siteconfig

    row = {"key": selected.get("key"), "id": selected.get("ref") if selected.get("cblock") else ""}
    if aufbau_draft._is_faq_row({"home": home}, row):
        items, src = faq_content.state(saved, draft)
        selected["faq_items"] = faq_content.panel(items, src, saved)
    key = selected.get("key") or ""
    if selected.get("cblock") and (siteconfig.cblock_type(key) or key) == "quick_links":
        # плашки и выбор набора — одна форма (смена набора сбрасывает скрытие и подписи)
        data = _item(config, home, host, selected["ref"]).get("data") or {}
        selected["tiles"] = hero_tiles.panel(data)
        selected["fields"] = []
