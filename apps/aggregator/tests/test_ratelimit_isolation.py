"""Класс флака CI #2683/#2714: xdist делит ОДИН Redis, чужой `cache.clear()` обнуляет
`rl:*` между хитами — тест видит 200 вместо 429. Любой тест, крутящий счётчик лимита
руками, обязан брать приватный кэш `isolated_ratelimit` (conftest)."""

import re
from pathlib import Path

TESTS = Path(__file__).parent


def test_every_manual_ratelimit_hit_uses_isolated_cache():
    offenders = []
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        src = path.read_text()
        for m in re.finditer(r"def (test_\w+)\(([^)]*)\):(.*?)(?=\ndef |\Z)", src, re.S):
            if "ratelimit.hit(" in m.group(3) and "isolated_ratelimit" not in m.group(2):
                offenders.append(f"{path.name}::{m.group(1)}")
    assert offenders == [], offenders
