"""SEC-G11b: приложение не под root, версии образов закреплены.

Docker-демона в CI нет — замок держит ТЕКСТ: пользователь app с фиксированным uid,
которым deploy.sh выравнивает том media, и отсутствие плавающих тегов.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text()


def test_app_image_runs_as_fixed_non_root_user():
    df = _read("Dockerfile")
    assert "--uid 10001" in df and "--gid 10001" in df
    assert "chown app:app /app/media /app/staticfiles" in df
    users = re.findall(r"^USER\s+(\S+)", df, re.M)
    assert users and users[-1] == "app", "последняя инструкция USER должна быть app"
    # USER после всех RUN-шагов сборки (компиляция .mo, установка пакетов — от root)
    assert df.rindex("USER app") > df.rindex("msgfmt")


def test_deploy_aligns_media_owner_to_the_same_uid():
    sh = _read("scripts", "deploy.sh")
    step = sh.split("[2b/8]", 1)[1].split("step ", 1)[0]
    assert "--user 0" in step and "chown -h 10001:10001" in step
    # ошибка chown не проглатывается последним echo
    assert "'set -eu;" in step
    # шаг стоит ДО первой команды приложения под app (миграции, перезапуск)
    assert sh.index("[2b/8]") < sh.index("migrate_schemas --shared")


def test_no_floating_image_tags():
    tags = re.findall(r"^\s*image:\s*(\S+)", _read("docker-compose.prod.yml"), re.M)
    external = [t for t in tags if not t.startswith("siteadaptor-app")]
    assert external, "ожидались внешние образы"
    for tag in external:
        version = tag.split(":", 1)[1]
        assert re.match(r"^\d+\.\d+(\.\d+)?-", version) or re.match(r"^\d+\.\d+\.\d+$", version), (
            tag
        )
    for path in (("Dockerfile",), ("caddy", "Dockerfile")):
        for base in re.findall(r"^FROM\s+(\S+)", _read(*path), re.M):
            assert re.search(r":\d+\.\d+\.\d+", base), base
