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
