"""PH-12a: изоляция кэша тестов между воркерами pytest-xdist.

CI гоняет `pytest -n auto`, все воркеры писали в одну базу Redis: `cache.clear()` (у
django-redis — FLUSHDB) одного воркера стирал magic-link токен или прогретый кэш соседа →
флаки, которые не воспроизводятся поодиночке. Каждому воркеру — своя база (0/1/2 заняты
брокером, кэшем и result backend); воркеров больше, чем баз, — второй круг отделяется
префиксом ключей. Без xdist (локальный прогон) настройки прежние.

Предел (ревью): `cache.clear()` — это FLUSHDB всей базы, префикс от него НЕ защищает. Больше
13 воркеров (`-n` > 13) снова делят базы и вернут флаки; CI на GitHub — 4 воркера (`-n auto`).
"""

import re

FIRST_DB = 3
MAX_DB = 15  # стандартный Redis: 16 баз (0…15)


def worker_cache(location: str, worker: str) -> tuple[str, str]:
    """(LOCATION, KEY_PREFIX) кэша для воркера `gwN`; иначе — как было и пустой префикс."""
    m = re.fullmatch(r"gw(\d+)", worker or "")
    if not m or not re.search(r"/\d+$", location):
        return location, ""
    n = int(m.group(1))
    slots = MAX_DB - FIRST_DB + 1
    db = FIRST_DB + n % slots
    prefix = f"gw{n}" if n >= slots else ""
    return re.sub(r"/\d+$", f"/{db}", location), prefix
