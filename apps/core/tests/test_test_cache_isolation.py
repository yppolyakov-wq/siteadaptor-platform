"""PH-12a: кэш тестов изолирован между воркерами xdist (флаки параллельного прогона)."""

from config.settings._xdist import worker_cache

BASE = "redis://localhost:6379/1"


def test_without_xdist_location_is_unchanged():
    assert worker_cache(BASE, "") == (BASE, "")
    assert worker_cache(BASE, "master") == (BASE, "")


def test_each_worker_gets_its_own_database():
    assert worker_cache(BASE, "gw0") == ("redis://localhost:6379/3", "")
    assert worker_cache(BASE, "gw1") == ("redis://localhost:6379/4", "")
    dbs = {worker_cache(BASE, f"gw{n}")[0] for n in range(13)}
    assert len(dbs) == 13  # базы 3…15, без брокера (0), кэша (1) и result (2)


def test_second_round_is_separated_by_key_prefix():
    loc0, pre0 = worker_cache(BASE, "gw0")
    loc13, pre13 = worker_cache(BASE, "gw13")
    assert loc13 == loc0 and pre13 == "gw13" and pre0 == ""


def test_test_settings_apply_the_worker_cache(monkeypatch):
    import importlib

    import config.settings.test as test_settings

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    mod = importlib.reload(test_settings)
    try:
        assert mod.CACHES["default"]["LOCATION"].endswith("/4")
    finally:
        monkeypatch.delenv("PYTEST_XDIST_WORKER")
        importlib.reload(test_settings)
