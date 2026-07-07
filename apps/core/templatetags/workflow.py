"""U-D2: шаблонные теги конвейера — действия FSM для строк/карточек.

`_status_actions.html` рендерит кнопки-переходы из `allowed_targets` текущего
статуса + подписи из pipeline. Для календарей (итерируют доменные объекты) —
тег `status_actions`; для доски карточка отдаёт готовый `allowed_actions`.
"""

from django import template

from apps.core import transactions

register = template.Library()


@register.simple_tag
def status_actions(kind, obj):
    """``[{target, label, stage, danger}]`` переходов FSM из ``obj.status``."""
    return transactions.allowed_actions_for(kind, obj.status)
