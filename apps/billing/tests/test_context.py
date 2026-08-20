from datetime import timedelta

from django.utils import timezone

from apps.billing.context import subscription
from apps.billing.state_machine import SUSPENDED, TRIAL


class _Tenant:
    def __init__(self, status, schema="acme", trial_ends_at=None):
        self.subscription_status = status
        self.schema_name = schema
        self.trial_ends_at = trial_ends_at


class _Request:
    pass


def test_trial_days_left_computed():
    req = _Request()
    req.tenant = _Tenant(TRIAL, trial_ends_at=timezone.now() + timedelta(days=5, hours=1))
    ctx = subscription(req)
    assert ctx["subscription_status"] == TRIAL
    assert ctx["subscription_gated"] is False
    assert ctx["trial_days_left"] == 5


def test_gated_status_flagged():
    req = _Request()
    req.tenant = _Tenant(SUSPENDED)
    ctx = subscription(req)
    assert ctx["subscription_gated"] is True
    assert ctx["trial_days_left"] is None


# --- VK-7 (фидбэк владельца 2026-08-20): плашка триала — раз за сессию --------
class _User:
    is_authenticated = True


def _page_request(session=None, method="GET", fetch=False, anonymous=False):
    req = _Request()
    req.tenant = _Tenant(TRIAL, trial_ends_at=timezone.now() + timedelta(days=13, hours=1))
    req.method = method
    req.headers = {"X-Requested-With": "fetch"} if fetch else {}
    req.session = {} if session is None else session
    if not anonymous:
        req.user = _User()
    return req


def test_trial_notice_shown_once_per_session():
    session = {}
    first = subscription(_page_request(session))
    assert first["show_trial_notice"] is True
    assert first["trial_days_left"] == 13
    second = subscription(_page_request(session))
    # На каждом следующем экране плашка не повторяется (постоянное место —
    # экран «Abo & Rechnung», гейт в шаблоне по nav == 'billing').
    assert second["show_trial_notice"] is False


def test_trial_notice_not_burned_by_fetch_fragment_or_post():
    session = {}
    assert subscription(_page_request(session, fetch=True))["show_trial_notice"] is False
    assert subscription(_page_request(session, method="POST"))["show_trial_notice"] is False
    assert session == {}  # флаг не поставлен — первый заход владельца ещё покажет
    assert subscription(_page_request(session))["show_trial_notice"] is True


def test_storefront_visitor_gets_no_session_flag():
    """Процессор глобальный: на витрине запись во флаг завела бы куку каждому
    посетителю (принцип «без трекинг-кук на витрине»)."""
    session = {}
    ctx = subscription(_page_request(session, anonymous=True))
    assert ctx["show_trial_notice"] is False and session == {}
