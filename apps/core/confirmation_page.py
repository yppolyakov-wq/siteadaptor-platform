"""FB-33 M2h: страница подтверждения — один хост блоков `confirmation` на заказ, запись, номер,
билет и стол (решение владельца 2026-11-19, `docs/fb33-editor-model-2026-11-19.md` §«План M2h»).

Разделы (порядок постоянный): `summary` — карточка сделки (код, сумма, оплата), неподвижна;
`next` «Was passiert jetzt» — один свой текст на сайт, рисуется только при своём тексте;
`recommend` «Empfehlungen» — по умолчанию ВЫКЛ (K3), хранится только включение
(`confirm_show_recommend: True`), товары как «Passt dazu» корзины без позиций сделки.

Свои блоки: над карточкой (до `summary`), под карточкой, после «Was passiert jetzt», хвост.
ПДн: блоки подтверждения рисуются с ЧИСТЫМ контекстом (без сделки и данных клиента —
`siteui.page_blocks` для этого хоста), блоки с формами здесь не рисуются (`FORM_BLOCKS`).
Модуль без БД, кроме `recommend_products`.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

HOST = "confirmation"
NEXT_KEY = "confirmation_next"
NEXT_MAX = 1200
RECOMMEND_FLAG = "confirm_show_recommend"
RECOMMEND_MAX = 4
#: блоки с полями ввода — на подтверждении не рисуются (данные сделки рядом, ПДн)
FORM_BLOCKS = frozenset({"newsletter", "anfrage_ref", "message_ref"})
#: блоки с POST-формой БЕЗ полей данных клиента — карточки «В корзину» (замок
#: `test_every_block_with_a_post_form_is_kept_off_the_confirmation`)
SAFE_POST_BLOCKS = frozenset({"list"})


def clean_next(value) -> str:
    """Свой текст «Was passiert jetzt»: строка без лишних пробелов по краям, не длиннее NEXT_MAX."""
    return value.strip()[:NEXT_MAX] if isinstance(value, str) else ""


def recommend_on(site) -> bool:
    return isinstance(site, dict) and site.get(RECOMMEND_FLAG) is True


def parts(site) -> dict:
    """Места своих блоков: {"lead", "after_summary", "after_next", "tail"} — `ids:` куски;
    без строк разделов все блоки — в хвосте (под карточкой)."""
    from apps.core import detail_parts
    from apps.tenants import siteconfig

    rows = siteconfig.page_rows(site, HOST) if isinstance(site, dict) else []
    keys = list(detail_parts.flow_section_keys(HOST))
    a = detail_parts.anchors(rows, HOST, keys)

    def part(ids):
        return detail_parts.ids_part(ids) if ids else ""

    return {
        "lead": part(a["lead"]),
        "after_summary": part(a["after"].get("summary", [])),
        "after_next": part(a["after"].get("next", [])),
        "tail": part(a["tail"]),
    }


def recommend_products(exclude_ids) -> list:
    """Товары «Empfehlungen» — как «Passt dazu» корзины (рекомендованные вперёд), без позиций
    сделки. Сбой — пустой список (подтверждение не падает из-за рекомендаций)."""
    try:
        from apps.catalog.upsell import upsell_products

        return upsell_products(exclude_ids, RECOMMEND_MAX)
    except Exception:  # noqa: BLE001 — рекомендации не роняют подтверждение
        logger.warning("confirmation recommend failed", exc_info=True)
        return []


def deal_product_ids(context) -> list:
    """Товары сделки (только id — для исключения из рекомендаций; в блоки не уходят)."""
    order = context.get("order")
    if order is None:
        return []
    try:
        return [i.product_id for i in order.items.all()]
    except Exception:  # noqa: BLE001
        logger.warning("confirmation: order items unreadable", exc_info=True)
        return []
