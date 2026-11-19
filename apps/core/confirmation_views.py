"""FB-33 M2h-5: превью страницы подтверждения для «Seitenaufbau».

Настоящее подтверждение открывается только по коду сделки; превью — синтетический пример без
БД (ни заказа, ни записи, ни клиента): владелец видит, где стоят его блоки, «Was passiert
jetzt» и «Empfehlungen». Только члену команды с правом сайта, остальным — 404 (адрес не
сообщает, что он существует); вне индекса, не кэшируется.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.core import page_settings

#: код примера — заметно не настоящий (настоящие коды — буквы и цифры без дефиса)
SAMPLE_CODE = "MUSTER-1234"


def sample_deal() -> SimpleNamespace:
    """Пример сделки для карточки: только подписи, без данных клиента."""
    return SimpleNamespace(
        reference_code=SAMPLE_CODE,
        title=_("Beispielbestellung"),
        lines=((1, _("Beispielartikel"), "12,50"), (2, _("Beispielartikel"), "7,00")),
        total="19,50",
    )


def confirmation_preview(request):
    if not page_settings._may_preview(request):
        raise Http404
    response = render(
        request,
        "storefront/confirmation_preview.html",
        {"sample": sample_deal()},
    )
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Cache-Control"] = "private, no-store"
    return response
