"""Часы для замков, чей результат зависит от дня недели и времени суток.

Секции витрины «по сроку» (`/aktionen/`: «Endet heute · diese Woche», бакеты
«Vorschau»: «Ab dieser Woche · nächster Woche») считаются от ЧАСОВ, а неделя
кончается в воскресенье 23:59. Поэтому у живых часов есть «бомбы»: в воскресенье
«до конца недели» = «до конца сегодняшнего дня», и секции «эта неделя» не бывает по
построению (CI 2026-10-04 — два красных замка), а в 23:59 акция «до конца дня» уже
закончилась (CI 2026-09-10).

`freeze_wednesday_noon` ставит часы на ближайшую прошедшую среду, 12:00 местного
времени: у среды есть и «сегодня», и «до конца недели», и «следующая неделя», а дата
рядом с настоящей — проверки «не в прошлом ли» у других моделей замок не задевает.
"""

from datetime import UTC, timedelta

from django.utils import timezone


def freeze_wednesday_noon(monkeypatch):
    """Заморозить `timezone.now()` на среду 12:00; вернуть это время в местном поясе.

    `timezone.localtime()` берёт `now()` из того же модуля, поэтому замороженное
    время видят и вьюхи, и модели (`auto_now_add`), и сам тест."""
    real = timezone.localtime()
    wednesday = real - timedelta(days=(real.weekday() - 2) % 7)
    frozen = wednesday.replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(timezone, "now", lambda: frozen.astimezone(UTC))
    return timezone.localtime()
