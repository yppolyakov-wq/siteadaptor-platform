"""FB-33 M3-5b: части окна блока «Seitenaufbau» — вопросы FAQ («Texte») и плашки
Schnellzugriff («Was»). Только модель для шаблона: пишут `faq_content` (черновик —
`aufbau_draft`) и данные блока `quick_links` (`hero_tiles.update_data`)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _item(config: dict, home: bool, host: str, ref: str) -> dict | None:
    """Строка блока в показанном конфиге; None — прочитать не удалось (в лог)."""
    from django.db import connection

    from apps.core import site_schema

    try:
        items = site_schema.load_items(config, home, host)
    except Exception:  # noqa: BLE001 — окно без формы плашек лучше, чем упавший экран
        logger.exception(
            "window_parts: block rows unavailable (%s, %s, %s)",
            getattr(connection, "schema_name", ""),
            host or "home",
            ref,
        )
        return None
    return next((it for it in items if isinstance(it, dict) and it.get("id") == ref), None)


def _items(config: dict, home: bool, host: str) -> list:
    from apps.core import site_schema

    try:
        return site_schema.load_items(config, home, host)
    except Exception:  # noqa: BLE001 — как `_item`: окно без подсказки лучше упавшего экрана
        logger.exception("window_parts: rows unavailable (%s)", host or "home")
        return []


def decorate(
    selected: dict | None,
    saved: dict,
    draft: dict | None,
    home: bool,
    config: dict,
    host: str,
    opened: int | None = None,
    user=None,
) -> None:
    """Дополнить выбранную строку частями среза. `saved` — сохранённый конфиг (вопросы
    черновика и их источники — из `draft`), `config` — показанный (с черновиком)."""
    if not selected:
        return
    from apps.core import aufbau_draft, faq_content, hero_tiles, object_faq
    from apps.tenants import siteconfig

    row = {"key": selected.get("key"), "id": selected.get("ref") if selected.get("cblock") else ""}
    key = selected.get("key") or ""
    if row["id"] and (siteconfig.cblock_type(key) or key) == "faq_ref" and not home:
        # FB-33 M2b-2b: источник вопросов — в данных строки (`data.source`)
        item = _item(config, home, host, selected["ref"])
        row["data"] = (item or {}).get("data") or {}
    own = None
    if not home and (siteconfig.cblock_type(key) or key) in ("faq", "faq_ref"):
        page = {"home": home, "host": host, "items": (draft or {}).get("items")}
        if page["items"] is None:
            page["items"] = _items(config, home, host)
        own = object_faq.panel(page, host, row, opened, saved, user)
    if aufbau_draft._is_faq_row({"home": home}, row):
        items, src = faq_content.state(saved, draft)
        selected["faq_items"] = faq_content.panel(items, src, saved, opened)
        if own:  # детальная: общие вопросы и выбор источника
            selected["faq_items"].update(own)
    elif own:
        selected["faq_items"] = own  # FB-33 M2b-2b: свои вопросы объекта (или подсказка)
    if selected.get("cblock") and (siteconfig.cblock_type(key) or key) == "quick_links":
        # плашки и выбор набора — одна форма (смена набора сбрасывает скрытие и подписи)
        item = _item(config, home, host, selected["ref"])
        if item is None:
            # ревью M3-5b: без данных блока форма плашек не рисуется — иначе «Übernehmen» с
            # пустым набором стёр бы набор, скрытие и подписи (остаётся прежняя форма набора)
            return
        selected["tiles"] = hero_tiles.panel(item.get("data") or {})
        selected["fields"] = []


#: стопка 2 (a11y M3-5b, как «Felder» M3-5a): список вопросов, когда их не осталось
FAQ_LIST_ANCHOR = "schema-tab-faq-list"


def faq_anchor_id(i: int) -> str:
    """id вопроса FAQ в окне (заголовок <summary> его <details>)."""
    return f"schema-tab-faq-{i}"


def faq_anchor(post, count: int, opened=None) -> str:
    """Якорь после кнопки вопроса FAQ: ↑/↓ — сдвинутый вопрос (`opened` — куда он встал),
    «Entfernen» — тот, что встал на его место (иначе предыдущий; нет — список), новый вопрос —
    последний. `count` — вопросов после правки. Пусто — прежний якорь."""
    if post.get("faq_present") != "1":
        return ""
    if post.get("faq_scope") == "object":
        # FB-33 M2b-2b: свои вопросы объекта — номер после кнопки помнит сама правка (`opened`,
        # `object_faq._remember_focus`): `count` вызывающего — число ОБЩИХ вопросов
        if not isinstance(opened, int) or not any(
            post.get(k) is not None for k in ("faq_move", "faq_remove", "faq_add")
        ):
            return ""
        return faq_anchor_id(opened) if opened >= 0 else FAQ_LIST_ANCHOR
    if post.get("faq_move") is not None:
        return faq_anchor_id(opened) if isinstance(opened, int) and 0 <= opened < count else ""
    removed = str(post.get("faq_remove") or "")
    if removed.isdigit():
        return faq_anchor_id(min(int(removed), count - 1)) if count else FAQ_LIST_ANCHOR
    if post.get("faq_add") is not None and str(post.get("faq_new_q") or "").strip() and count:
        return faq_anchor_id(count - 1)
    return ""
