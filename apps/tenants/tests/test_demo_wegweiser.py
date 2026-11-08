"""Wegweiser W-5 (2026-11-08): демо `online_shop` («Weitwerk») — носитель макета S1."""

import re
from pathlib import Path

from apps.tenants.demo_kits import ONLINE_SHOP


def test_online_shop_root_is_wegweiser_without_the_old_carousels():
    assert ONLINE_SHOP.config_patch["catalog_page_style"] == "wegweiser"
    # две карусели «neu_sale» стояли над направлениями, а сетка повторяла «Neu»
    assert ("catalog", "neu_sale") not in ONLINE_SHOP.page_presets


def test_online_shop_fills_every_focus_tab():
    """«Im Fokus» рисует вкладку от трёх карточек — у демо должны быть все три."""
    src = Path(__file__).resolve().parents[1].joinpath("demo_kits.py").read_text()
    start = src.index("ONLINE_SHOP = DemoKit(")
    end = src.index(" = DemoKit(", start + 30)
    block = src[start:end]
    assert len(re.findall(r'badge="neu"', block)) >= 3
    assert len(re.findall(r'badge="beliebt"', block)) >= 3
