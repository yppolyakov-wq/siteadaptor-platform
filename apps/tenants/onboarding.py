"""Onboarding-Wizard (Track D / D0c): состояние пошаговой настройки бизнеса.

Мастер живёт на /dashboard/setup/ (apps.core.views.setup_view): ≤5 шагов, одно
решение на шаг, каждый можно пропустить, прогресс резюмируется. Состояние —
в Tenant.site_config["onboarding"] (siteconfig.normalize и site_view его
сохраняют): {"step": 1..5, "skipped": [...], "completed": bool}.

Шаги: 1) Was machst du? (business_type → предвыбор блоков) → 2) Was willst du
anbieten? (тумблеры модулей) → 3) Basics (адрес/часы/контакты) → 4) Erster
Inhalt (пресеты акций) → 5) Geschafft. Достижение шага 5 = мастер завершён.
"""

TOTAL_STEPS = 5


def get_state(tenant) -> dict:
    """Валидное состояние мастера из site_config (мусор → дефолты)."""
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    raw = config.get("onboarding")
    raw = raw if isinstance(raw, dict) else {}
    step = raw.get("step")
    if not isinstance(step, int) or not 1 <= step <= TOTAL_STEPS:
        step = 1
    skipped = sorted(
        {s for s in raw.get("skipped", []) if isinstance(s, int) and 1 <= s < TOTAL_STEPS}
    )
    return {"step": step, "skipped": skipped, "completed": bool(raw.get("completed"))}


def save_state(tenant, state: dict) -> None:
    config = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    config["onboarding"] = state
    tenant.site_config = config
    tenant.save(update_fields=["site_config", "updated_at"])


def advance(tenant, *, skip: bool = False) -> dict:
    """Перейти к следующему шагу (опц. пометив текущий пропущенным).

    Шаг 5 — финальный экран: добравшись до него, мастер завершён.
    """
    state = get_state(tenant)
    if skip and state["step"] < TOTAL_STEPS and state["step"] not in state["skipped"]:
        state["skipped"] = sorted({*state["skipped"], state["step"]})
    if state["step"] < TOTAL_STEPS:
        state["step"] += 1
    if state["step"] >= TOTAL_STEPS:
        state["completed"] = True
    save_state(tenant, state)
    return state


def back(tenant) -> dict:
    """Вернуться на шаг назад (сравнить варианты, поменять тип бизнеса).

    Возврат не «раз-завершает» мастер: completed остаётся, плашка прогресса
    на дашборде не воскресает из-за просмотра прежних шагов.
    """
    state = get_state(tenant)
    if state["step"] > 1:
        state["step"] -= 1
        state["skipped"] = [s for s in state["skipped"] if s != state["step"]]
        save_state(tenant, state)
    return state


def progress(tenant) -> tuple[int, int]:
    """(пройдено, всего) для плашки «Setup-Fortschritt N/5» на дашборде."""
    state = get_state(tenant)
    done = TOTAL_STEPS if state["completed"] else state["step"] - 1
    return done, TOTAL_STEPS
