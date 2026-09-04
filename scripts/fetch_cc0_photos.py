#!/usr/bin/env python3
"""Подбор CC0/PDM-кандидатов демо-фото (Openverse) — второй канал рядом с генерацией.

Волна AMP (2026-09-03). Правило `static/demo/photos/README.md`: только CC0/public
domain ИЛИ AI. Поэтому фильтр лицензии — жёсткий (`license=cc0,pdm`), провенанс
пишется рядом в `<out>/sources.json` для последующего SOURCES.md.

    python scripts/fetch_cc0_photos.py queries.json --out /tmp/cand --per 4

Спека — JSON-список {"name","query"} (можно "queries": [...] — несколько запросов
на слот). На выходе `<out>/<name>__cc<i>.jpg`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse

API = "https://api.openverse.org/v1/images/"
MIN_SIDE = 640  # мельче — на карточке будет мыло


def search(query: str, limit: int) -> list[dict]:
    qs = urllib.parse.urlencode(
        {"q": query, "license": "cc0,pdm", "page_size": max(limit * 3, 12), "size": "large"}
    )
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", "60", f"{API}?{qs}"], capture_output=True, text=True
    )
    try:
        data = json.loads(proc.stdout)
    except Exception:  # noqa: BLE001 — пустой/битый ответ не должен ронять подбор
        return []
    out = []
    for r in data.get("results", []):
        w, h = r.get("width") or 0, r.get("height") or 0
        if min(w, h) < MIN_SIDE:
            continue
        if r.get("license") not in ("cc0", "pdm"):
            continue  # страховка: фильтр API — не повод не проверить
        out.append(r)
        if len(out) >= limit:
            break
    return out


def download(url: str, dst: str) -> bool:
    proc = subprocess.run(
        ["curl", "-sSL", "--max-time", "120", "-o", dst, "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
    )
    ok = (proc.stdout or "").strip()[-3:] == "200" and os.path.getsize(dst) > 20000
    if not ok and os.path.exists(dst):
        os.remove(dst)
        return False
    try:  # битый файл лучше выбросить сразу, чем показать агенту-приёмщику
        from PIL import Image

        Image.open(dst).verify()
    except Exception:  # noqa: BLE001
        os.remove(dst)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="JSON со слотами {name, query|queries}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per", type=int, default=3, help="кандидатов на слот")
    args = ap.parse_args()

    slots = json.load(open(args.spec))
    os.makedirs(args.out, exist_ok=True)
    sources_path = os.path.join(args.out, "sources.json")
    sources = json.load(open(sources_path)) if os.path.exists(sources_path) else {}

    for slot in slots:
        name = slot["name"]
        queries = slot.get("queries") or [slot["query"]]
        got = 0
        for query in queries:
            for r in search(query, args.per):
                if got >= args.per:
                    break
                dst = os.path.join(args.out, f"{name}__cc{got + 1}.jpg")
                if os.path.exists(dst):
                    got += 1
                    continue
                if not download(r["url"], dst):
                    continue
                sources[os.path.basename(dst)] = {
                    "title": r.get("title"),
                    "creator": r.get("creator"),
                    "license": r.get("license"),
                    "source": r.get("source"),
                    "landing": r.get("foreign_landing_url"),
                    "query": query,
                }
                got += 1
        print(f"{name}: {got} CC0-кандидатов", flush=True)
        json.dump(sources, open(sources_path, "w"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
