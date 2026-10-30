"""KA-12 E9.7: замок дизайн-системы кабинета — то, что аудит нашёл «по месту», не возвращается.

- произвольные цвета `bg-[#…]` (вместо токенов/деталей `ui-*`);
- зелёные кнопки-действия (действие — `.ui-btn-primary`; зелёный — цвет статуса «в работе»).
Переключатели состояния (сегмент «вкл/выкл») помечаются `data-ui-state` и проверку не проходят.
"""

import re
from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR) / "templates"
DASHBOARD = [
    p
    for p in ROOT.glob("**/*.html")
    if '{% extends "tenant/_base_dashboard.html" %}' in p.read_text(encoding="utf-8")
]
GREEN_ACTION = re.compile(
    r'<(?:a|button)\b(?![^>]*data-ui-state)[^>]*class="[^"]*\bbg-(?:green|emerald)-(?:500|600|700)\b'
)


def test_no_arbitrary_hex_backgrounds():
    bad = [
        str(p.relative_to(ROOT))
        for p in DASHBOARD
        if re.search(r"\bbg-\[#[0-9a-fA-F]+\]", p.read_text(encoding="utf-8"))
    ]
    assert not bad, bad


def test_no_green_action_buttons():
    bad = [
        str(p.relative_to(ROOT))
        for p in DASHBOARD
        if GREEN_ACTION.search(p.read_text(encoding="utf-8"))
    ]
    assert not bad, bad


ALL = sorted(ROOT.glob("**/*.html"))


def test_phone_and_email_inputs_open_the_right_keyboard():
    """E9.5: поле телефона — `type="tel"`, e-mail — `type="email"` (клавиатура на телефоне)."""
    bad = []
    for p in ALL:
        src = p.read_text(encoding="utf-8")
        for tag in re.findall(r'<input\b[^>]*\bname="phone"[^>]*>', src):
            if 'type="tel"' not in tag and 'type="hidden"' not in tag:
                bad.append(f"{p.relative_to(ROOT)}: phone")
        for tag in re.findall(r'<input\b[^>]*\bname="email"[^>]*>', src):
            if 'type="email"' not in tag and 'type="hidden"' not in tag:
                bad.append(f"{p.relative_to(ROOT)}: email")
    assert not bad, bad


def test_cabinet_shrinks_large_photos_before_upload():
    """E9.5: фото > 4.5 МБ уменьшается в браузере (сервер режет на 5 МБ). Поведение —
    Playwright-стенд; здесь — что скрипт подключён к каждому экрану кабинета."""
    base = (ROOT / "tenant/_base_dashboard.html").read_text(encoding="utf-8")
    assert '{% include "core/_photo_shrink.html" %}' in base
    js = (ROOT / "core/_photo_shrink.html").read_text(encoding="utf-8")
    assert "4.5 * 1024 * 1024" in js and "requestSubmit" in js


def test_variant_row_folds_stock_fields_on_phone():
    """E9.5: учётные поля варианта на телефоне свёрнуты, но остаются в форме (W0)."""
    src = (ROOT / "catalog/product_form.html").read_text(encoding="utf-8")
    box = src.split("data-variant-more>", 1)[1].split("</span>", 1)[0]
    for name in ("content", "cost", "reorder_point", "reorder_target", "sku", "gtin", "sort"):
        assert f'name="{name}"' in box, name
    assert 'class="hidden sm:contents"' in src and "data-variant-more-toggle" in src
