"""DCC «демо-покрытие каталога Золингена»: спеки бизнесов → DemoKit'ы.

`demo_kits.KITS.update(city_kits())` подключает их к общему реестру. Импортировать
`demo_kits` отсюда можно только лениво (внутри функций) — модуль собирается с конца
`demo_kits.py`, когда его верхние имена уже определены.
"""

from __future__ import annotations


def businesses():
    from .solingen import BUSINESSES

    return BUSINESSES


def city_kits() -> dict:
    from .builder import city_kits as _build

    return _build(businesses())
