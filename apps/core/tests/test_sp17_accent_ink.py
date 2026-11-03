"""SP-17 (решение владельца 2026-11-03): подпись на акцент-фоне тенанта читаема.

Кнопки витрины несли жёсткий text-white поверх `background: var(--accent)`; у
светлого акцента (лайм, янтарь, пастель) белый текст нечитаем. Цвет текста теперь
берёт `--accent-ink` (DL-5: тёмные чернила для светлого акцента) одним правилом CSS.
"""

from __future__ import annotations

from pathlib import Path

from apps.core.context import _accent_ink

ROOT = Path(__file__).resolve().parents[3]


def test_light_accents_get_dark_ink():
    assert _accent_ink("#c8f542") == "#111827"  # лайм
    assert _accent_ink("#fcd34d") == "#111827"  # янтарь
    assert _accent_ink("#4f46e5") == "#ffffff"  # индиго — прежний вид
    assert _accent_ink("not-a-color") == "#ffffff"  # fail-safe


def test_accent_background_takes_ink_after_utilities():
    built = (ROOT / "static" / "css" / "app.css").read_text()
    rule = '[style*="background: var(--accent)"]'
    assert rule in built
    # правило стоит ПОСЛЕ утилит — иначе равная специфичность отдала бы победу text-white
    assert built.index(rule) > built.index(".text-white{")
    tail = built[built.index(rule) :].split("}", 1)[0]
    assert "var(--accent-ink" in tail


def test_storefront_defines_ink_variable():
    base = (ROOT / "templates" / "storefront" / "_base.html").read_text()
    assert "--accent-ink: {{ storefront_accent_ink" in base
