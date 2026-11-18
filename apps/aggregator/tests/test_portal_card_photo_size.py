"""Владелец 2026-11-18: фото в карточках выдачи портала одного размера. Блок фото 4:3 во
flex-колонке растягивался под большую картинку (min-height: auto по содержимому) —
`overflow-hidden` на блоке держит пропорцию (стенд 1300 px: 288/288/432/288 → 216 у всех)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_card_photo_box_clips_to_its_aspect():
    src = (ROOT / "templates/aggregator/_cards.html").read_text(encoding="utf-8")
    box = src[src.index("aspect-[4/3]") - 200 : src.index("aspect-[4/3]") + 300]
    assert "overflow-hidden" in box
