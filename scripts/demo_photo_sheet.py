"""Контактный лист кандидатов CC0-фото — чтобы кадр выбирался ГЛАЗАМИ, но дёшево.

Каждое демо-фото обязано быть просмотрено до коммита (README рядом с фото), а
поиск по слову регулярно отдаёт чужой предмет, водяной знак или узнаваемое лицо.
Смотреть кандидатов по одному дорого, поэтому скрипт собирает миниатюры в ОДИН
размеченный лист: смотрящий читает одну картинку и называет номер.

    python scripts/demo_photo_sheet.py sneakers:"sneaker shoe" mug:"coffee mug"

Для каждого ключа рядом с листом пишется `<key>.json` — метаданные кандидатов в
том же порядке, что номера на листе (url/лицензия/источник/страница-источник).
Скачивание выбранного кадра — `scripts/demo_photo_fetch.py get <url> <key>`.
"""

from __future__ import annotations

import argparse
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import requests
from PIL import Image, ImageDraw

API = "https://api.openverse.org/v1/images/"
OK_LICENSES = {"cc0", "pdm"}
UA = "siteadaptor-demo-photo-fetch/1.0 (CC0 demo assets)"
CELL = 260
COLS = 4
#: Источники современной фотографии (первый проход поиска).
PHOTO_SOURCES = "rawpixel,stocksnap"
#: Оцифрованные собрания: по общему слову отдают экспонат, а не товар.
ARCHIVE_SOURCES = {
    "met",
    "smithsonian",
    "clevelandmuseum",
    "brooklynmuseum",
    "rijksmuseum",
    "statensmuseum",
    "thorvaldsensmuseum",
    "digitaltmuseum",
    "nypl",
    "sciencemuseum",
    "museumsvictoria",
    "svgsilh",
    "biodiversity",
    "floraon",
    "geographorguk",
    "wordpress",
    "spacex",
    "nasa",
    "phylopic",
    "bio_diversity",
    "wellcome_collection",
}


def _page(term: str, page: int, source: str = "") -> list[dict]:
    params = {"q": term, "license": "cc0,pdm", "page_size": 20, "page": page, "mature": "false"}
    if source:
        params["source"] = source
    try:
        r = requests.get(
            f"{API}?{urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": UA},
            timeout=40,
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception:  # noqa: BLE001 — сеть/квота: отдаём что есть
        return []


def _search(term: str, limit: int) -> list[dict]:
    """Кандидаты: сначала СОВРЕМЕННАЯ фотография, потом всё остальное.

    Без этого разделения общий запрос («ceramic plate», «teapot») отдаёт почти
    исключительно оцифрованные музейные собрания — археологическая керамика
    вместо посуды, которую можно поставить в магазин. Поэтому первый проход
    ограничен фото-стоками, а свободный добор идёт следом и без музейных
    источников."""
    out, seen = [], set()

    def collect(results):
        for item in results:
            url = str(item.get("url", ""))
            if str(item.get("license", "")).lower() not in OK_LICENSES:
                continue
            # Вектор/иконка на витрине смотрится инородно — отбрасываем сразу.
            if url.lower().endswith(".svg") or url in seen:
                continue
            if str(item.get("source", "")).lower() in ARCHIVE_SOURCES:
                continue
            seen.add(url)
            out.append(item)
            if len(out) >= limit:
                return True
        return False

    for page in (1, 2):
        if collect(_page(term, page, PHOTO_SOURCES)):
            return out
    for page in (1, 2, 3):
        if collect(_page(term, page)):
            break
    return out


def _thumb(item: dict) -> Image.Image | None:
    for url in (item.get("thumbnail"), item.get("url")):
        if not url:
            continue
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=45)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content))
            return img.convert("RGB")
        except Exception:  # noqa: BLE001 — битый кадр просто не попадёт на лист
            continue
    return None


def _search_many(terms: list, limit: int) -> list[dict]:
    """Кандидаты по нескольким формулировкам, по очереди из каждой.

    Одно слово часто промахивается («ceramic plate» отдаёт археологию, а
    «plate table setting» — сервировку), поэтому кит даёт 2-3 запроса, а лист
    показывает смесь: если первая формулировка пустая, вторая спасает ключ."""
    pools = [_search(t, limit) for t in terms if t]
    out, seen = [], set()
    for i in range(limit):
        for pool in pools:
            if i >= len(pool):
                continue
            url = pool[i].get("url")
            if url in seen:
                continue
            seen.add(url)
            out.append(pool[i])
            if len(out) >= limit:
                return out
    return out


def sheet(key: str, term: str, out_dir: Path, limit: int = 12) -> dict:
    # «q1|q2|q3» — несколько формулировок одного мотива.
    items = _search_many([t.strip() for t in term.split("|")], limit)
    with ThreadPoolExecutor(max_workers=8) as pool:
        thumbs = list(pool.map(_thumb, items))

    pairs = [(it, th) for it, th in zip(items, thumbs, strict=True) if th is not None]
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = []
    for n, (it, _th) in enumerate(pairs, start=1):
        meta.append(
            {
                "n": n,
                "title": it.get("title"),
                "url": it.get("url"),
                "license": it.get("license"),
                "source": it.get("source"),
                "creator": it.get("creator"),
                "landing": it.get("foreign_landing_url"),
                "size": [it.get("width"), it.get("height")],
            }
        )
    (out_dir / f"{key}.json").write_text(
        json.dumps({"key": key, "term": term, "candidates": meta}, ensure_ascii=False, indent=1)
    )
    if not pairs:
        return {"key": key, "term": term, "count": 0, "sheet": ""}

    rows = (len(pairs) + COLS - 1) // COLS
    canvas = Image.new("RGB", (COLS * CELL, rows * (CELL + 22)), "#ffffff")
    draw = ImageDraw.Draw(canvas)
    for i, (_it, th) in enumerate(pairs):
        th = th.copy()
        th.thumbnail((CELL - 8, CELL - 8), Image.LANCZOS)
        x = (i % COLS) * CELL + (CELL - th.size[0]) // 2
        y = (i // COLS) * (CELL + 22) + (CELL - th.size[1]) // 2
        canvas.paste(th, (x, y))
        label_y = (i // COLS) * (CELL + 22) + CELL + 4
        draw.text(((i % COLS) * CELL + 6, label_y), f"#{i + 1}", fill="#111111")
    path = out_dir / f"{key}.png"
    canvas.save(path, "PNG")
    return {"key": key, "term": term, "count": len(pairs), "sheet": str(path)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("specs", nargs="*", help="key:term (термин без двоеточия = и ключ, и запрос)")
    ap.add_argument("--from-file", default="", help="файл со строками key:term (по одной)")
    ap.add_argument("--out", default="", help="каталог для листов")
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    out_dir = Path(a.out) if a.out else Path("photo-sheets")

    specs = list(a.specs)
    if a.from_file:
        specs += [ln.strip() for ln in Path(a.from_file).read_text().splitlines() if ln.strip()]
    jobs = []
    for spec in specs:
        key, _, term = spec.partition(":")
        jobs.append((key, term or key))
    done = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for row in pool.map(lambda kt: sheet(kt[0], kt[1], out_dir, a.limit), jobs):
            done += 1
            print(f"{done}/{len(jobs)} {row['key']} n={row['count']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
