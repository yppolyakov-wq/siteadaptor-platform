"""Context processor: данные подписки для баннера в кабинете владельца.

Подключён в TEMPLATES (config/settings/base.py). subscription_status/gated ставит
middleware; здесь добавляем число оставшихся дней триала для баннера.
"""

from django.utils import timezone

from .state_machine import GATED_STATUSES, TRIAL

# VK-7 (фидбэк владельца 2026-08-20): «Тест: осталось 13 дней» висел НА КАЖДОМ
# экране кабинета и съедал первый экран. Показываем один раз за сессию (при
# входе) всплывающим тостом; постоянный показ остаётся только на экране
# «Abo & Rechnung», где это рабочая информация, а не напоминание.
TRIAL_NOTICE_SESSION_KEY = "trial_notice_seen"


def _is_page_view(request) -> bool:
    """Полноценный заход на страницу кабинета (не fetch-фрагмент, не POST) —
    иначе единственный показ за сессию сгорел бы на фоновом запросе календаря.

    Гейт по залогиненному пользователю обязателен: процессор глобальный и на
    ВИТРИНЕ тоже; запись во флаг сессии там завела бы куку каждому посетителю
    (принцип «без трекинг-кук на витрине»)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    return request.method == "GET" and request.headers.get("X-Requested-With") != "fetch"


def subscription(request):
    tenant = getattr(request, "tenant", None)
    status = getattr(request, "subscription_status", None)
    if status is None:
        status = getattr(tenant, "subscription_status", "") if tenant is not None else ""

    trial_days_left = None
    if status == TRIAL and getattr(tenant, "trial_ends_at", None):
        trial_days_left = max(0, (tenant.trial_ends_at - timezone.now()).days)

    show_trial_notice = False
    if trial_days_left is not None and _is_page_view(request):
        session = getattr(request, "session", None)
        if session is not None and not session.get(TRIAL_NOTICE_SESSION_KEY):
            session[TRIAL_NOTICE_SESSION_KEY] = True
            show_trial_notice = True

    return {
        "subscription_status": status,
        "subscription_gated": status in GATED_STATUSES,
        "trial_days_left": trial_days_left,
        "show_trial_notice": show_trial_notice,
    }
