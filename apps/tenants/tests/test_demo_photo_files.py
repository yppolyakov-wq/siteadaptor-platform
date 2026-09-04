"""Фонд демо-фото: один и тот же кадр не может стоять под двумя ключами.

Приёмка 2026-09-04 нашла восемь пар байт-в-байт: плитка категории «Sandalen» и
товар «Sandale Ebbe», два свитера, два полотенца — на витрине это читается как
ошибка вёрстки, а не как ассортимент. Класс системный: кадры подбираются
батчами (разные агенты, разные заходы), и увидеть повтор можно только сверив
фонд целиком — что и делает этот замок."""

import hashlib
import pathlib
from collections import defaultdict

PHOTOS = pathlib.Path(__file__).resolve().parents[3] / "static/demo/photos"

# Пара из кита «restaurant», доставшаяся до волны OS: оба ключа — фон одного
# зала. Осознанно оставлена как есть (правка чужого кита меняет его вид);
# запись здесь фиксирует, что это известный долг, а не новый промах.
KNOWN_PAIRS = {("restaurant-food", "wine-restaurant")}


def test_no_two_keys_share_the_same_frame():
    by_hash = defaultdict(list)
    for f in sorted(PHOTOS.glob("*.webp")):
        by_hash[hashlib.md5(f.read_bytes()).hexdigest()].append(f.stem)
    dups = {tuple(sorted(v)) for v in by_hash.values() if len(v) > 1}
    assert dups <= KNOWN_PAIRS, f"один кадр под несколькими ключами: {sorted(dups - KNOWN_PAIRS)}"
