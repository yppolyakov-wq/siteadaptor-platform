"""M21.11 P4: заготовки для «＋ Neue Seite».

Заготовка = несохранённая страница (заголовок + текст) для формы: GET ничего не пишет,
страница появляется только по «Speichern». Текст собирается из данных бизнеса, которые
уже есть (часы, адрес, способы оплаты); чего нет — остаётся пометка «bitte ergänzen».
Всё экранируется ДО разметки и проходит тот же санитайзер, что ввод владельца.
"""

from __future__ import annotations

from django.utils.html import escape
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

STARTERS = (
    ("leer", gettext_lazy("Leere Seite")),
    ("faq", gettext_lazy("Häufige Fragen")),
    ("anfahrt", gettext_lazy("Öffnungszeiten & Anfahrt")),
    ("zahlung", gettext_lazy("Zahlungsarten")),
)
KEYS = frozenset(k for k, _l in STARTERS)


def _p(text: str) -> str:
    return "<p>" + escape(text).replace("\n", "<br>") + "</p>"


def _fill() -> str:
    return "<p><em>" + escape(_("Bitte ergänzen.")) + "</em></p>"


def _faq() -> str:
    parts = []
    for q in (
        _("Wie kann ich bestellen?"),
        _("Wie lange dauert die Lieferung?"),
        _("Kann ich etwas zurückgeben?"),
    ):
        parts.append("<h3>" + escape(q) + "</h3>" + _fill())
    return "".join(parts)


def _anfahrt(tenant) -> str:
    out = ["<h2>" + escape(_("Öffnungszeiten")) + "</h2>"]
    week = []
    try:
        week = list(tenant.opening_hours_week()) if tenant is not None else []
    except Exception:  # noqa: BLE001 — заготовка не должна падать на данных
        week = []
    if week:
        out.append("<ul>" + "".join("<li>" + escape(line) + "</li>" for line in week) + "</ul>")
    elif tenant is not None and (tenant.opening_hours or "").strip():
        out.append(_p(tenant.opening_hours.strip()))
    else:
        out.append(_fill())
    out.append("<h2>" + escape(_("Anfahrt")) + "</h2>")
    address = (getattr(tenant, "address", "") or "").strip() if tenant is not None else ""
    out.append(_p(address) if address else _fill())
    return "".join(out)


def _zahlung(tenant) -> str:
    from apps.core import payment_methods

    codes = []
    try:
        codes = payment_methods.available(tenant) if tenant is not None else []
    except Exception:  # noqa: BLE001
        codes = []
    if not codes:
        return _p(_("Folgende Zahlungsarten bieten wir an:")) + _fill()
    items = "".join("<li>" + escape(str(payment_methods.label(c))) + "</li>" for c in codes)
    return _p(_("Folgende Zahlungsarten bieten wir an:")) + "<ul>" + items + "</ul>"


def build(key: str, tenant=None) -> tuple[str, str]:
    """(title, body) заготовки; неизвестный ключ → пустая страница."""
    from apps.core.richtext import sanitize_page

    labels = dict(STARTERS)
    if key not in KEYS or key == "leer":
        return "", ""
    body = {"faq": _faq, "anfahrt": lambda: _anfahrt(tenant), "zahlung": lambda: _zahlung(tenant)}
    return str(labels[key]), sanitize_page(body[key]())
