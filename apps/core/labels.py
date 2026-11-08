"""FB-20: метки («Neu», «Beliebt», …) — один реестр для всех продаваемых сущностей.

У товара метка была с давних пор (`Product.badge`); теперь та же метка есть у акции,
услуги, события и номера. Хранение — код в поле `badge` (choices НЕ на модели: реестр
растёт без миграций, прецедент `card_style`). Подпись — lazy, на витрине в языке
клиента. Мусорный код → метки нет (не 500).
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

#: код → подпись (порядок = порядок в форме).
LABELS = {
    "tagesgericht": _("Tagesgericht"),
    "neu": _("Neu"),
    "beliebt": _("Beliebt"),
    "empfehlung": _("Empfehlung"),
}

#: choices для форм кабинета: «—» = без метки.
CHOICES = [("", "—"), *LABELS.items()]


def label_for(code: str | None) -> str:
    """Подпись метки или "" (пусто/неизвестный код)."""
    return LABELS.get(code or "", "")


def clean(code: str | None) -> str:
    """Код из формы → допустимый код или ""."""
    return code if code in LABELS else ""
