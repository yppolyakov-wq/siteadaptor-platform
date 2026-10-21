import pytest


@pytest.fixture(autouse=True)
def _reset_invoice_mail_throttle():
    """Лимит писем со счётом (CO-2) живёт в общем Redis: без сброса повторные локальные
    прогоны тестов с тем же адресом упирались бы в него."""
    from django.core.cache import cache

    try:
        client = cache._cache.get_client()
        for key in client.scan_iter("*invoice-mail:*"):
            client.delete(key)
    except Exception:  # noqa: BLE001 — другой бэкенд кэша: сбрасывать нечего
        pass
    yield
