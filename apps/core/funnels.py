"""E5 «задача-первым»: реестр шагов воронок покупки для прогресс-степпера.

Ведём клиента последовательно: каждая витринная воронка = короткая цепочка
шагов (выбор → детали/время → подтверждено). Степпер (тег `funnel_steps`)
показывает, где клиент сейчас и сколько осталось — снижает отвал. Данные
плоские (без моделей/миграций); лейблы i18n.
"""

from django.utils.translation import gettext_lazy as _

# kind → упорядоченные лейблы шагов (1-based). Гранулярность = РЕАЛЬНЫЕ страницы
# воронки, а не микрошаги внутри страницы.
FUNNELS = {
    "service": (_("Leistung"), _("Termin"), _("Bestätigt")),  # /termin/ → слот → готово
    "stay": (_("Auswahl"), _("Daten"), _("Bestätigt")),  # номера → даты → готово
    "event": (_("Veranstaltung"), _("Tickets"), _("Bestätigt")),
    "order": (_("Warenkorb"), _("Versand"), _("Bestätigt")),
}


def funnel_labels(kind: str) -> tuple:
    return FUNNELS.get(kind, ())


def funnel_steps(kind: str, current: int) -> list[dict]:
    """Список шагов с состоянием done/current/upcoming для рендера степпера.

    current — 1-based номер текущего шага; вне диапазона → пустой список
    (степпер не рендерится, без регрессии)."""
    labels = funnel_labels(kind)
    if not labels or not (1 <= current <= len(labels)):
        return []
    out = []
    for i, label in enumerate(labels, start=1):
        state = "done" if i < current else ("current" if i == current else "upcoming")
        out.append({"n": i, "label": label, "state": state})
    return out
