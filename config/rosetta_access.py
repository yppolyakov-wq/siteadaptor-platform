"""T1-c (FB-12): контроль доступа к django-rosetta (веб-редактор переводов .po).

Rosetta правит .po хрома платформы (общие для ВСЕХ тенантов) — это инструмент
ПЛАТФОРМЕННОГО владельца, не тенанта. Поэтому доступ — только суперпользователю.
"""


def can_translate(user) -> bool:
    return bool(user and user.is_active and user.is_superuser)
