"""Поиск и загрузка CC0-фото для демо-витрин (`static/demo/photos/`).

Внешние фото на витрине не используются — файл кладётся в репозиторий, поэтому
лицензия обязана быть CC0/Public-Domain-Mark. Скрипт делает ровно три вещи и
НИЧЕГО не решает за человека: ищет кандидатов, показывает их метаданные и, по
явной команде, скачивает выбранный кадр в webp нужного размера.

Каждый кадр всё равно ОБЯЗАН быть просмотрен глазами (агентом) до коммита —
поиск по слову регулярно отдаёт чужой предмет, водяные знаки или узнаваемые
лица; правила — `static/demo/photos/README.md`.

    # найти кандидатов (JSON в stdout)
    python scripts/demo_photo_fetch.py search "sneaker" --limit 12

    # скачать выбранный кадр под ключ кита
    python scripts/demo_photo_fetch.py get <image_url> sneakers --size product

`search` фильтрует выдачу Openverse по `license=cc0,pdm` И перепроверяет
лицензию каждой записи по её метаданным (фильтр API — не гарантия).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
from PIL import Image

API = "https://api.openverse.org/v1/images/"
OK_LICENSES = {"cc0", "pdm"}
UA = "siteadaptor-demo-photo-fetch/1.0 (CC0 demo assets)"

#: Целевые размеры (README демо-фото): товар/галерея, баннер, портрет.
SIZES = {
    "product": (800, 600),
    "hero": (1600, 900),
    "portrait": (400, 400),
    "cover": (1200, 900),
}

DEST = Path("static/demo/photos")


def search(term: str, limit: int = 12, page: int = 1) -> list[dict]:
    qs = urlencode(
        {
            "q": term,
            "license": "cc0,pdm",
            "page_size": min(limit, 20),
            "page": page,
            "mature": "false",
        }
    )
    r = requests.get(
        f"{API}?{qs}", headers={"Accept": "application/json", "User-Agent": UA}, timeout=40
    )
    r.raise_for_status()
    out = []
    for item in r.json().get("results", []):
        # Перепроверка: фильтр API — не гарантия, лицензия берётся из записи.
        if str(item.get("license", "")).lower() not in OK_LICENSES:
            continue
        out.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "thumbnail": item.get("thumbnail"),
                "license": item.get("license"),
                "source": item.get("source"),
                "creator": item.get("creator"),
                "landing": item.get("foreign_landing_url"),
                "width": item.get("width"),
                "height": item.get("height"),
            }
        )
    return out


def fetch(url: str, key: str, size: str = "product", quality: int = 80) -> Path:
    box = SIZES[size]
    r = requests.get(url, headers={"User-Agent": UA}, timeout=90)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    # cover-crop до целевых пропорций, затем ресайз вниз (вверх не растягиваем).
    tw, th = box
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    if scale < 1:
        nw, nh = round(sw * scale), round(sh * scale)
        img = img.resize((nw, nh), Image.LANCZOS)
        sw, sh = img.size
    left, top = (sw - min(sw, round(th * sw / sh) if sh else sw)) // 2, 0
    # простой центр-кроп под соотношение
    target_ratio = tw / th
    if sw / sh > target_ratio:
        nw = round(sh * target_ratio)
        left = (sw - nw) // 2
        img = img.crop((left, 0, left + nw, sh))
    else:
        nh = round(sw / target_ratio)
        top = (sh - nh) // 2
        img = img.crop((0, top, sw, top + nh))
    if img.size[0] > tw:
        img = img.resize(box, Image.LANCZOS)

    DEST.mkdir(parents=True, exist_ok=True)
    path = DEST / f"{key}.webp"
    q = quality
    while q >= 45:
        img.save(path, "WEBP", quality=q, method=6)
        if path.stat().st_size <= 150_000:
            break
        q -= 8
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("term")
    s.add_argument("--limit", type=int, default=12)
    s.add_argument("--page", type=int, default=1)

    g = sub.add_parser("get")
    g.add_argument("url")
    g.add_argument("key")
    g.add_argument("--size", choices=sorted(SIZES), default="product")

    a = ap.parse_args()
    if a.cmd == "search":
        json.dump(search(a.term, a.limit, a.page), sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    path = fetch(a.url, a.key, a.size)
    print(f"{path} {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
