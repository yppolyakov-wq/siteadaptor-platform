#!/usr/bin/env python3
"""Генератор демо-фото (AI) для `static/demo/photos/`.

Волна AMP (2026-09-03): картинки демо-китов генерируются моделью изображений через
keyless-эндпоинт `image.pollinations.ai`. Правило README демо-фото допускает
AI-generated наравне с CC0.

ВАЖНО про параллелизм: у эндпоинта лимит «1 запрос на IP одновременно»
(иначе `Queue full for IP`), поэтому генерация СТРОГО последовательная с
ретраями и backoff. Готовые файлы пропускаются — прогон можно возобновлять.

    python scripts/gen_demo_photos.py spec.json --out /tmp/cand --seeds 1,2
    python scripts/gen_demo_photos.py spec.json --out /tmp/cand --only markt-eier

Спека — JSON-список {"name","prompt","w","h"} (см. docs/amp-grocery-photos-plan-*).
На выходе `<out>/<name>__s<seed>.jpg`; в репозиторий кадры кладёт `--install`
(конверт в webp с целевым размером файла).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

ENDPOINT = "https://image.pollinations.ai/prompt/"
MIN_BYTES = 5000  # меньше — это JSON с ошибкой, а не картинка


def fetch(prompt: str, out: str, *, seed: int, w: int, h: int, tries: int = 5) -> bool:
    url = ENDPOINT + urllib.parse.quote(prompt, safe="")
    url += f"?width={w}&height={h}&nologo=true&seed={seed}"
    for attempt in range(tries):
        proc = subprocess.run(
            ["curl", "-sS", "--max-time", "240", "-o", out, "-w", "%{http_code}", url],
            capture_output=True,
            text=True,
        )
        code = (proc.stdout or "").strip()[-3:]
        size = os.path.getsize(out) if os.path.exists(out) else 0
        if code == "200" and size > MIN_BYTES:
            return True
        time.sleep(5 + attempt * 5)  # очередь занята / 5xx — ждём и повторяем
    if os.path.exists(out) and os.path.getsize(out) <= MIN_BYTES:
        os.remove(out)  # не оставляем JSON-ошибку под видом кадра
    return False


def to_webp(src: str, dst: str, *, max_bytes: int = 150_000) -> int:
    """Конверт в webp с подбором качества под целевой размер файла."""
    from PIL import Image

    im = Image.open(src).convert("RGB")
    for quality in (86, 80, 74, 68, 62, 55):
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=quality, method=6)
        if buf.tell() <= max_bytes or quality == 55:
            with open(dst, "wb") as fh:
                fh.write(buf.getvalue())
            return buf.tell()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="JSON со слотами {name,prompt,w,h}")
    ap.add_argument("--out", required=True, help="каталог кандидатов")
    ap.add_argument("--seeds", default="1", help="через запятую: 1,2")
    ap.add_argument("--only", default="", help="через запятую: только эти name")
    ap.add_argument("--install", default="", help="каталог static/demo/photos — положить webp")
    ap.add_argument("--pick", default="", help="JSON {name: seed} — какой кандидат ставить")
    ap.add_argument("--workers", type=int, default=1, help="параллельных запросов (лимит IP — 2)")
    args = ap.parse_args()

    slots = json.load(open(args.spec))
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        slots = [s for s in slots if s["name"] in want]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    os.makedirs(args.out, exist_ok=True)

    if args.install:
        pick = json.load(open(args.pick)) if args.pick else {}
        done = 0
        for slot in slots:
            seed = pick.get(slot["name"], seeds[0])
            src = os.path.join(args.out, f"{slot['name']}__s{seed}.jpg")
            if not os.path.exists(src):
                print(f"SKIP (нет кандидата) {slot['name']} seed={seed}")
                continue
            dst = os.path.join(args.install, f"{slot['name']}.webp")
            size = to_webp(src, dst)
            done += 1
            print(f"install {slot['name']}.webp  {size // 1024} KB")
        print(f"\nУстановлено: {done}")
        return 0

    # Порядок задач — ПО ПРОХОДАМ (сперва первый seed на ВСЕ слоты): прерванный
    # прогон всё равно оставляет по кандидату на каждый слот.
    jobs = [(slot, seed) for seed in seeds for slot in slots]
    total = len(jobs)
    lock = threading.Lock()
    state = {"n": 0, "ok": 0}

    def run(job):
        slot, seed = job
        out = os.path.join(args.out, f"{slot['name']}__s{seed}.jpg")
        if os.path.exists(out) and os.path.getsize(out) > MIN_BYTES:
            got, mark = True, "skip"
        else:
            got = fetch(
                slot["prompt"],
                out,
                seed=seed,
                w=int(slot.get("w", 1024)),
                h=int(slot.get("h", 768)),
            )
            mark = "OK  " if got else "FAIL"
        with lock:
            state["n"] += 1
            state["ok"] += bool(got)
            print(f"[{state['n']}/{total}] {mark} {os.path.basename(out)}", flush=True)

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(run, jobs))
    else:
        for job in jobs:
            run(job)
            time.sleep(1.0)
    print(f"\nГотово: {state['ok']}/{total}")
    return 0 if state["ok"] == total else 1


if __name__ == "__main__":
    sys.exit(main())
