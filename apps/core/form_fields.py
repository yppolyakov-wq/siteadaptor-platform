"""KA-M2: денежное поле, которое понимает «12,50» на любом языке кабинета.

`type="text" inputmode="decimal"` вместо `type="number"`: числовое поле браузера с немецкой
запятой отдаёт пустую строку (iOS, Telegram), и цена молча терялась. Атрибутов `pattern`/
`required` не ставим: недопустимое скрытое поле во вкладке молча отменяет отправку формы в
Chrome (класс X6-6) — проверку делает сервер."""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import formats

from .money import parse_money


def format_money(value) -> str:
    """Значение для поля: Decimal → по локали («12,50» в de), строка — как ввёл человек."""
    if value is None or value == "":
        return ""
    if isinstance(value, Decimal | int | float) and not isinstance(value, bool):
        return formats.number_format(Decimal(str(value)), 2, use_l10n=True, force_grouping=False)
    return str(value)


class MoneyInput(forms.TextInput):
    def __init__(self, attrs=None):
        base = {"inputmode": "decimal", "autocomplete": "off"}
        super().__init__({**base, **(attrs or {})})

    def format_value(self, value):
        text = format_money(value)
        return text or None


class MoneyField(forms.DecimalField):
    widget = MoneyInput

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            parsed = parse_money(value)
        except ValueError:
            raise ValidationError(self.error_messages["invalid"], code="invalid") from None
        if parsed is None:
            return None
        return parsed

    def widget_attrs(self, widget):
        # step/min/max — только для числового поля; у текстового они бессмысленны.
        return forms.Field.widget_attrs(self, widget)
