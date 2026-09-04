"""Плейсхолдер демо-фото: частная игла обязана стоять ВЫШЕ общей.

`_EMOJI` сканируется сверху вниз, первое совпадение по ПОДСТРОКЕ выигрывает.
Класс дефекта повторялся трижды: «Schale» ловилась иглой «schal» и получала
шарф; «Karaffe … glas» — стакан; махровое полотенце «frottee» — чайную чашку
(«frot-TEE-»). Такие промахи видны только на витрине, тестам они незаметны,
поэтому пары ниже прибиты явно."""

import pytest

from apps.tenants.demo_images import _emoji_for

# (ключ, ожидаемая тема, чем ловился раньше)
CASES = [
    ("schale-rund-steinzeug", "🥣", "иглой schal → 🧣"),
    ("handtuch-frottee-hand", "🧻", "иглой tee- → 🍵"),
    ("duschtuch-frottee-gross", "🧻", "иглой tee- → 🍵"),
    ("handtuecher-stapel-frottee", "🧻", "не ловился вовсе"),
    ("tuch-ahorn", "🧣", "не ловился вовсе"),
    ("gaestetuch-waffel-paar", "🧻", "не ловился вовсе"),
    ("sandale-ebbe", "🩴", "иглой dal → 🍛 (san-DAL-e)"),
    ("bereich-sandalen", "🩴", "иглой dal → 🍛"),
    ("notizbuch-taschen-a6", "📓", "иглой taschen → 👜"),
    ("haarbuerste-ahorn-holz", "💇", "иглой buerste → 🧹 (метла)"),
    # Соседи, которые правка НЕ имеет права сломать.
    ("dal-linsen-essen", "🍛", "дал остаётся далом"),
    ("taschen-uebersicht", "👜", "сумки остаются сумками"),
    ("tee-nebel-sencha", "🍵", "чай остаётся чаем"),
    ("schal-winter-wolle", "🧣", "шарф остаётся шарфом"),
]


@pytest.mark.parametrize("key,expected,history", CASES)
def test_placeholder_theme_is_specific(key, expected, history):
    assert _emoji_for(key) == expected, f"{key}: раньше ловился {history}"


def test_generic_fallback_is_not_food_outside_food_context():
    """Фидбэк 2026-07-28: 🍽️ в карточке рюкзака выглядел ошибкой."""
    assert _emoji_for("völlig-unbekanntes-ding") == "✨"
