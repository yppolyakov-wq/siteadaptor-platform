"""FB-3: правила переходов статусов (кабинет-конфигуратор поверх FSM).

Безопасный scope (Вариант A): FSM (`apps/*/state_machine.py`) — ЖЁСТКИЙ ПОЛ (легальный
граф + все побочки on_transition неизменны). Владелец может лишь СКРЫТЬ/показать уже-
легальные НЕ-danger переходы (напр. убрать «No-Show»). Danger/отмена (`pipeline.is_danger`)
не прячется никогда (иначе карточку не закрыть). apply()/kanban_action по-прежнему сверяются
с FSM → «протухшее» правило безвредно.

Хранение: site_config["transitions"][kind][src] = [разрешённые не-danger dst]. Отсутствие
src → дефолт (все легальные показаны). Пустой список → скрыть все не-danger из src.
"""

from apps.core import pipeline


def _sm_for(kind):
    from apps.core import transactions

    return transactions.sm_for(kind)


def subset_for(tenant, kind: str) -> dict:
    """{src: [dst,...]} правил перехода для kind из site_config (или {} — тогда дефолт)."""
    cfg = getattr(tenant, "site_config", None)
    if isinstance(cfg, dict):
        node = cfg.get("transitions")
        if isinstance(node, dict) and isinstance(node.get(kind), dict):
            return node[kind]
    return {}


def keep_target(status: str, target: str, subset: dict) -> bool:
    """Показывать ли переход `target` из `status`. Danger — всегда; иначе: нет правила
    для status → да; есть → только если target в списке разрешённых."""
    if pipeline.is_danger(target):
        return True
    rule = subset.get(status)
    if rule is None:
        return True
    return target in rule


def _status_display(kind: str, status: str, custom: dict) -> str:
    """Подпись статуса-источника: своё имя владельца (FB-4a/b) или дефолт из модели."""
    if custom.get(status):
        return custom[status]
    from apps.core import transactions

    model = transactions.model_for(kind)
    return dict(getattr(model, "STATUSES", [])).get(status, status)


def editor_rows(tenant, kind: str) -> list[dict]:
    """Строки панели правил: по одному src (у которого есть не-danger легальные переходы).

    [{src, src_label, targets: [{dst, label, enabled, danger}]}]. danger-цели показываем
    как всегда-вкл (в UI — disabled-чекбокс). enabled = текущее правило (или всё по дефолту).
    """
    from apps.core import status_labels
    from apps.tenants import siteconfig

    sm = _sm_for(kind)
    subset = subset_for(tenant, kind)
    custom = status_labels.custom_labels(tenant, kind)
    rows = []
    for src in siteconfig.status_label_statuses(kind) or ():
        legal = list(sm.allowed_targets(src))
        if not any(not pipeline.is_danger(d) for d in legal):
            continue  # из src нечего скрывать (только danger/терминал)
        targets = [
            {
                "dst": d,
                "label": pipeline.action_label(kind, d),
                "danger": pipeline.is_danger(d),
                "enabled": keep_target(src, d, subset),
            }
            for d in legal
        ]
        rows.append(
            {"src": src, "src_label": _status_display(kind, src, custom), "targets": targets}
        )
    return rows


def save(tenant, kind: str, request) -> None:
    """Targeted-write site_config["transitions"][kind] из чекбоксов `t_<src>_<dst>`.

    Пишем правило src ТОЛЬКО когда владелец скрыл хотя бы один не-danger переход (иначе
    дефолт — presence-minimal). Danger не хранится/не прячется. Прочие kind/ключи целы.
    """
    from apps.tenants import siteconfig

    sm = _sm_for(kind)
    rules = {}
    for src in siteconfig.status_label_statuses(kind) or ():
        nd = [d for d in sm.allowed_targets(src) if not pipeline.is_danger(d)]
        if not nd:
            continue
        enabled = [d for d in nd if request.POST.get(f"t_{src}_{d}")]
        if enabled != nd:  # владелец что-то скрыл (порядок сохранён → subset ⇒ !=)
            rules[src] = enabled
    cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
    allt = dict(cfg.get("transitions") or {})
    if rules:
        allt[kind] = rules
    else:
        allt.pop(kind, None)
    if allt:
        cfg["transitions"] = allt
    else:
        cfg.pop("transitions", None)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
