"""FB-33 M3-6 (макет M0-10): закреплённые правовые строки «Seitenaufbau» и подписи их кнопок.

§ 312j Abs. 3 BGB («Button-Lösung»): кнопка, которой покупатель берёт на себя обязанность
платить, должна прямо это говорить («Zahlungspflichtig bestellen» / «… buchen»). Поэтому:

- подпись кнопки НИГДЕ не хранится и не пишется: витрина берёт её литералом из шаблона
  (`cart.html`, `gift_voucher.html`, `_buybox_*`), окно показывает те же msgid отсюда — серым
  полем без `name` вне формы; любой POST на строку — отказ (`aufbau_draft._m36_op`);
- строка не двигается, не скрывается и не меняет ширину (как и раньше: `site_schema.mutate`).

Замок `test_fb33_m3_6c_pinned.py` рендерит витрину в обоих режимах корзины (оплата и
«Unverbindlich anfragen», MEN-9) и сверяет подпись окна с подписью витрины.
"""

from __future__ import annotations

from django.utils.translation import gettext as _

from apps.core import detail_parts

#: строки с подписью кнопки по закону: (модуль разделов, ref строки)
LEGAL_ROWS = frozenset({("cart", "summary"), ("gift", "form")})


def _module(host: str) -> str:
    return detail_parts.module_of(detail_parts.shared_host(host or "")) or ""


def is_legal(host: str, ref: str) -> bool:
    """Закреплённая правовая строка: итог корзины, форма ваучера, «Kaufen»/«Buchung»."""
    if ref == detail_parts.KAUF_REF:
        return detail_parts.has_kauf(detail_parts.shared_host(host or ""))
    return (_module(host), ref) in LEGAL_ROWS


def ref_kind(host: str) -> str:
    """«order» — заказ с итогом (корзина, ваучер), «buy» — «Kaufen» товара (кнопка заказа —
    в корзине), «booking» — «Buchung» (услуга, номер, событие, тур)."""
    shared = detail_parts.shared_host(host or "")
    if _module(host) in ("cart", "gift"):
        return "order"
    return "buy" if shared == "product_detail" else "booking"


def label(host: str, ref: str, config: dict | None = None) -> str:
    """Подпись кнопки, как её рисует витрина (те же msgid, что в шаблонах). Пусто — у строки
    своей кнопки с подписью по закону нет («Kaufen»: заказ подтверждают в корзине)."""
    if not is_legal(host, ref):
        return ""
    kind = ref_kind(host)
    if kind == "buy":
        return ""
    if kind == "booking":
        return _("Zahlungspflichtig buchen")
    if _module(host) == "cart" and (config or {}).get("quote_cart"):
        # MEN-9: корзина = запрос на просчёт — платёжной обязанности нет, § 312j не применяется
        return _("Unverbindlich anfragen")
    return _("Zahlungspflichtig bestellen")


def panel(host: str, ref: str, config: dict | None = None) -> dict | None:
    """Часть окна «Texte» закреплённой правовой строки: плашка и подпись кнопки (только
    чтение). Тексты — gettext; плашка у итога и ваучера — дословно макет M0-10."""
    if not is_legal(host, ref):
        return None
    kind = ref_kind(host)
    quote = _module(host) == "cart" and bool((config or {}).get("quote_cart"))
    if kind == "order" and quote:
        text = _(
            "Hier wird unverbindlich angefragt – ohne Zahlungspflicht. Deshalb heißt der Button "
            "„Unverbindlich anfragen“. Der Block lässt sich nicht verschieben, ausblenden oder "
            "in der Breite ändern."
        )
    elif kind == "order":
        text = _(
            "Bestellübersicht, Gesamtpreis und der Button „Zahlungspflichtig bestellen“ müssen "
            "direkt untereinander stehen — so verlangt es § 312j BGB (Button-Lösung). Deshalb "
            "lässt er sich nicht verschieben, ausblenden oder in der Breite ändern. Texte und "
            "Felder können Sie anpassen."
        )
    elif kind == "booking":
        text = _(
            "Bei kostenpflichtigen Buchungen muss der Button „Zahlungspflichtig buchen“ heißen — "
            "so verlangt es § 312j BGB (Button-Lösung). Deshalb lässt sich dieser Block nicht "
            "verschieben, ausblenden oder in der Breite ändern."
        )
    else:
        text = _(
            "Der Kauf wird im Warenkorb mit dem Button „Zahlungspflichtig bestellen“ "
            "abgeschlossen — so verlangt es § 312j BGB (Button-Lösung). Dieser Block hat deshalb "
            "einen festen Platz: Er lässt sich nicht verschieben, ausblenden oder in der Breite "
            "ändern."
        )
    return {
        "title": _("Dieser Block ist fest."),
        "text": text,
        "label": label(host, ref, config),
        "field_label": _("Beschriftung des Buchungs-Buttons")
        if kind == "booking"
        else _("Beschriftung des Bestell-Buttons"),
        "fixed_note": _("Gesetzlich vorgegeben, nicht änderbar."),
        # бесплатная бронь сохраняет прежний текст (KA-H11): подсказка, а не второе поле
        "free": _("Bei kostenlosen Angeboten: „%(label)s“.") % {"label": _("Book now")}
        if kind == "booking"
        else "",
    }


#: строки без полей ввода: вкладка «Felder» говорит это прямо (макет M0-10, «Bestellübersicht»)
NO_INPUT_ROWS = frozenset({("cart", "summary")})


def no_input(host: str, ref: str) -> str:
    if (_module(host), ref) not in NO_INPUT_ROWS:
        return ""
    return _("Hier werden keine Angaben abgefragt")


def decorate(selected, host: str, config: dict) -> None:
    """Части окна закреплённой правовой строки: «pinned» (Texte) и «noinput» (Felder)."""
    if not selected:
        return
    ref = selected.get("ref") or ""
    found = panel(host, ref, config)
    if found:
        selected["legal"] = found
    note = no_input(host, ref)
    if note:
        selected["noinput"] = note
