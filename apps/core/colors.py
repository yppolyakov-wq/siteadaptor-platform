"""Цвета и контраст WCAG 2.x — общий слой витрины и городского портала (PH-12b).

`ink_on` — текст ПОВЕРХ цветного фона (берём из белого/тёмного то, что контрастнее; витрина —
`--accent-ink`, портал — `--portal-ink`). `readable_on_white` — сам цвет как текст на белом
(ссылки цветом бренда): затемняем, пока контраст не станет ≥ 4,5:1. `normalize_hex` —
допускает только `#rrggbb`: цвет из админки попадает в `<style>`, мусор там — CSS-инъекция.
"""

import re

INK_DARK = "#111827"
INK_LIGHT = "#ffffff"
AA = 4.5
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def normalize_hex(value, default: str = INK_DARK) -> str:
    value = (value or "").strip() if isinstance(value, str) else ""
    return value.lower() if _HEX.fullmatch(value) else default


def rel_luminance(hex_color: str) -> float:
    """Относительная яркость WCAG 2.x (sRGB линеаризуется по каналам)."""

    def lin(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((rel_luminance(a), rel_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ink_on(background: str) -> str:
    """DL-5/SP-17: цвет текста поверх фона — тот, что даёт БОЛЬШИЙ контраст (без порогов).
    Не-hex/битое значение → белый (fail-safe, как раньше у витрины)."""
    background = (background or "").strip()
    if not _HEX.fullmatch(background):
        return INK_LIGHT
    on_white = contrast(INK_LIGHT, background)
    on_dark = contrast(INK_DARK, background)
    return INK_DARK if on_dark > on_white else INK_LIGHT


def _mix(a: str, b: str, t: float) -> str:
    """Линейное смешение a → b (t = доля b) в sRGB."""
    ca = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb, strict=True))


def readable_on_white(color: str) -> str:
    """Цвет как текст на белом с контрастом ≥ 4,5:1: затемняем к INK_DARK шагами 10 %.
    Сам бренд, если он уже проходит, не трогаем."""
    color = normalize_hex(color)
    for step in range(11):
        candidate = _mix(color, INK_DARK, step / 10)
        if contrast(candidate, INK_LIGHT) >= AA:
            return candidate
    return INK_DARK
