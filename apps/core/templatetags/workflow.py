"""U-D2: шаблонные теги конвейера — действия FSM для строк/карточек.

`_status_actions.html` рендерит кнопки-переходы из `allowed_targets` текущего
статуса + подписи из pipeline. Для календарей (итерируют доменные объекты) —
тег `status_actions`; для доски карточка отдаёт готовый `allowed_actions`.
"""

from django import template

from apps.core import transactions

register = template.Library()


@register.simple_tag(takes_context=True)
def status_actions(context, kind, obj):
    """``[{target, label, stage, danger}]`` переходов FSM из ``obj.status``. FB-3: правила
    переходов владельца (site_config) СКРЫВАЮТ не-danger переходы (FSM/apply не трогаем)."""
    from apps.core import refunds, transition_rules

    tenant = getattr(context.get("request"), "tenant", None)
    subset = transition_rules.subset_for(tenant, kind) if tenant is not None else None
    actions = transactions.allowed_actions_for(kind, obj.status, subset, obj=obj)
    # KA-D3: у отмены оплаченной брони номера рядом с кнопкой — выбор возврата.
    for a in actions:
        a["refund_choice"] = refunds.needs_choice(kind, obj, a["target"], obj.status, tenant)
    return actions
