"""U-D2: конвейер статус→стадия — покрытие всех статусов FSM + форма колонок."""

from importlib import import_module

from apps.core import pipeline
from apps.core.transactions import _KIND_SM, TRANSACTION_KINDS


def _all_statuses(kind):
    """Все статусы (src ∪ dst) из таблицы переходов FSM данного kind."""
    module_path, cls_name = _KIND_SM[kind]
    sm = getattr(import_module(module_path), cls_name)()
    statuses = set()
    for t in sm.transitions:
        statuses.add(t.src)
        statuses.add(t.dst)
    return statuses


def test_pipeline_covers_every_fsm_status():
    """Каждый статус каждого FSM размечен в PIPELINE — иначе карточка «потеряется»
    (замок против дрейфа: добавили статус в FSM — обнови PIPELINE)."""
    for kind in TRANSACTION_KINDS:
        mapped = set(pipeline.PIPELINE[kind])
        missing = _all_statuses(kind) - mapped
        assert not missing, f"{kind}: статусы без стадии — {missing}"


def test_pipeline_stages_are_canonical():
    for kind in TRANSACTION_KINDS:
        for status, stage in pipeline.PIPELINE[kind].items():
            assert stage in pipeline.STAGES, f"{kind}.{status} → неизвестная стадия {stage}"


def test_pipeline_for_returns_four_ordered_columns():
    cols = pipeline.pipeline_for("order")
    assert [c["stage"] for c in cols] == list(pipeline.STAGES)
    # у заказа две колонки «в работе»/«готово» непусты
    by_stage = {c["stage"]: c["statuses"] for c in cols}
    assert "new" in by_stage["intake"]
    assert set(by_stage["in_progress"]) == {"confirmed", "ready"}
    assert set(by_stage["done"]) == {"picked_up", "shipped"}
    assert set(by_stage["terminal"]) == {"cancelled", "returned"}


def test_stage_for_unknown_status_falls_back_to_intake():
    assert pipeline.stage_for("order", "zzz-nonexistent") == "intake"
    assert pipeline.stage_for("nonexistent-kind", "new") == "intake"


def test_action_label_falls_back_to_status_code():
    assert pipeline.action_label("order", "confirmed")  # есть подпись
    assert pipeline.action_label("order", "zzz") == "zzz"  # фолбэк — код
