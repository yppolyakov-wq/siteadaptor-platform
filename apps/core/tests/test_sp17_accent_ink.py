"""SP-17 (решение владельца 2026-11-03): подпись на акцент-фоне тенанта читаема.

Кнопки на `background: var(--accent)` берут `--accent-ink` (правило DL-5 в _base.html).
Выбор чернил был по гамма-яркости с порогом 0.62 — средние тона (зелёный, оранжевый,
голубой) получали белый текст 2.3–2.8:1. Теперь — те чернила, что дают больший контраст
по формуле WCAG.
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
    assert _accent_ink("#zzzzzz") == "#ffffff"


def _contrast(a, b):
    from apps.core.context import _rel_luminance

    la, lb = sorted((_rel_luminance(a), _rel_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_mid_tone_accents_pick_the_readable_ink():
    """a11y-ревью: при пороге 0.62 средние тона получали белый текст ~2.5:1."""
    for accent in ("#22c55e", "#f97316", "#0ea5e9", "#16a34a"):
        ink = _accent_ink(accent)
        assert ink == "#111827", accent
        assert _contrast(accent, ink) >= 4.5, accent
    # ink всегда не хуже альтернативы
    for accent in ("#4f46e5", "#15803d", "#b45309", "#7c3aed", "#e11d48"):
        ink = _accent_ink(accent)
        other = "#ffffff" if ink == "#111827" else "#111827"
        assert _contrast(accent, ink) >= _contrast(accent, other), accent


def test_accent_background_takes_ink():
    """Правило DL-5 в _base.html: любой инлайн-фон акцента берёт --accent-ink."""
    base = (ROOT / "templates" / "storefront" / "_base.html").read_text()
    assert '[style*="background: var(--accent)"]' in base
    assert "color: var(--accent-ink, #ffffff) !important" in base


def test_storefront_defines_ink_variable():
    base = (ROOT / "templates" / "storefront" / "_base.html").read_text()
    assert "--accent-ink: {{ storefront_accent_ink" in base
