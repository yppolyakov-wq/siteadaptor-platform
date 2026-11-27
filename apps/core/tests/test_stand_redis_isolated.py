"""FB-33 стопка 13: сервер стенда не делит базу Redis с тестами.

58 тест-файлов зовут `cache.clear()` (FLUSHDB базы кэша). Сессии сервера стенда лежат в том
же кэше (`SESSION_ENGINE = cache`), поэтому параллельный pytest стирал вход обхода владельца —
782 ложных ✗ на базе стопки 13. Стенд по умолчанию берёт свою базу Redis; явный
`REDIS_CACHE_URL` по-прежнему главнее.
"""

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]

_PRINT = (
    "import django;django.setup();from django.conf import settings;"
    "print(settings.CACHES['default']['LOCATION'])"
)


def _location(extra_env: dict) -> str:
    env = {k: v for k, v in os.environ.items() if k != "REDIS_CACHE_URL"}
    env.update(extra_env, DJANGO_SETTINGS_MODULE="config.settings.stand")
    out = subprocess.run(
        [sys.executable, "-c", _PRINT],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def test_stand_cache_is_not_the_test_cache_db():
    location = _location({})
    assert location.startswith("redis://")
    assert not location.rstrip("/").endswith("/1"), location


def test_explicit_redis_cache_url_wins():
    assert _location({"REDIS_CACHE_URL": "redis://localhost:6379/9"}) == "redis://localhost:6379/9"


def test_session_hook_does_not_pin_stand_cache_to_test_db():
    """FB-33 стопка 16 K1: хук сессии экспортировал `REDIS_CACHE_URL=…/1` (= база кэша pytest),
    и запасная база стенда (/2) не срабатывала — тесты стирали сессию инвентаря (302 кейтеринга).
    База кэша по умолчанию и так /1 (`config/settings/base.py`), экспорт не нужен."""
    hook = (ROOT / ".claude/hooks/session-start.sh").read_text(encoding="utf-8")
    assert "export REDIS_CACHE_URL=" not in hook
