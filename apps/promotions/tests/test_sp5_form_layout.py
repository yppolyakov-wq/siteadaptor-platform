"""SP-5 (аудит пространства 2026-11-02): форма акции — парные поля в две колонки.

Табы «Rabatt»/«Zeit» шли одной колонкой по полю (~1500 px); пары цен, скидок, дат,
количеств и часов окна теперь рядом на sm+. Набор полей и их name прежние; при
создании пустой рейл не съедает 340 px.
"""

import re
from pathlib import Path

from django.conf import settings

TPL = Path(settings.BASE_DIR) / "templates/promotions/promotion_form.html"


def _pairs(text):
    grids = re.findall(
        r'<div class="grid sm:grid-cols-2 gap-x-4 gap-y-3 items-start">(.*?)</div>', text, re.S
    )
    return [tuple(re.findall(r"field.name == '([a-z_]+)'", g)) for g in grids]


def test_price_date_quantity_pairs_side_by_side():
    pairs = _pairs(TPL.read_text(encoding="utf-8"))
    for pair in [
        ("compare_at_price", "price_override"),
        ("discount_percent", "discount_off"),
        ("starts_at", "ends_at"),
        ("available_quantity", "max_per_customer"),
        ("rule_hour_from", "rule_hour_to"),
    ]:
        assert pair in pairs, pair


def test_rail_grid_only_for_saved_promotion():
    text = TPL.read_text(encoding="utf-8")
    grid = text.split("data-promo-form-grid")[0].rsplit("<div", 1)[-1]
    assert "{% if promotion %}lg:grid" in grid
