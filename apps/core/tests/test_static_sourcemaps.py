"""Прод собирает статику ManifestStaticFilesStorage: ссылка `sourceMappingURL` на
несуществующий файл роняет collectstatic — а с ним и старт web-контейнера (инцидент
2026-10-24: вендорные leaflet/maplibre ссылались на .map, которых нет в репозитории).
Тесты collectstatic не гоняют, поэтому ловим класс здесь."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "static"
_REF = re.compile(r"sourceMappingURL=([^\s*]+)")


def test_every_source_map_reference_exists():
    missing = []
    for path in list(ROOT.rglob("*.js")) + list(ROOT.rglob("*.css")):
        for ref in _REF.findall(path.read_text(errors="ignore")):
            if ref.startswith(("data:", "http:", "https:", "//")):
                continue
            if not (path.parent / ref).exists():
                missing.append(f"{path.relative_to(ROOT)} → {ref}")
    assert not missing, missing
