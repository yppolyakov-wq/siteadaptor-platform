"""FB-19b: список муниципалитетов Германии для подсказок поля «Stadt».

Источник — Gemeindeverzeichnis Destatis (GV-ISys, «Gemeinden in Deutschland nach Fläche,
Bevölkerung und Postleitzahl», Satzart 60). Лицензия: «Vervielfältigung und Verbreitung,
auch auszugsweise, mit Quellenangabe gestattet» — © Statistisches Bundesamt (Destatis).

    curl -sSL -o /tmp/gv.xlsx "https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/\
Gemeindeverzeichnis/Administrativ/Archiv/GVAuszugJ/31122024_Auszug_GV.xlsx?__blob=publicationFile"
    uv run python scripts/build_gemeinden.py /tmp/gv.xlsx

Пишет static/data/gemeinden_de.json: {"source": …, "items": [[name, population], …]},
по убыванию населения; суффиксы статуса («, Stadt», «, Hansestadt», «, M») сняты, одноимённые
общины склеены (в подсказке важно название, а не какая из одиннадцати Neuenkirchen).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent.parent / "static" / "data" / "gemeinden_de.json"
SOURCE = "© Statistisches Bundesamt (Destatis), Gemeindeverzeichnis, Stand 31.12.2024"


def build(path: str) -> dict:
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[1]
    best: dict[str, int] = {}
    for row in ws.iter_rows(values_only=True):
        if row[0] != "60" or not row[7]:
            continue
        name = str(row[7]).split(", ", 1)[0].strip()
        pop = int(row[9] or 0)
        if name and pop >= best.get(name, -1):
            best[name] = pop
    items = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"source": SOURCE, "items": [[n, p] for n, p in items]}


if __name__ == "__main__":
    data = build(sys.argv[1])
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data['items'])} Gemeinden → {OUT}")
