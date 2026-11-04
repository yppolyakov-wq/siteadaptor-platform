"""SEC-G12b: `scripts/backup.sh` реально проходит до конца на обычном `.env.prod`.

Прод показал: скрипт выходил молча и без бэкапа — необязательные ключи
(`BACKUP_DIR`, `BACKUP_KEEP_DAYS`, `BACKUP_S3_BUCKET`, `DB_PORT`) в `.env.prod` обычно не
заданы, а `grep` без совпадений под `set -e -o pipefail` обрывал присваивание. Замок
гоняет НАСТОЯЩИЙ скрипт с подменённым `docker` (демона в CI нет).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

_FAKE_DOCKER = """#!/usr/bin/env bash
case "$*" in
  *pg_dump*) head -c 4096 /dev/urandom ;;
  *tar*) head -c 64 /dev/urandom ;;
  *) exit 0 ;;
esac
"""


def _run(tmp_path: Path, env_lines: str, *, fail_dump: bool = False):
    if not shutil.which("bash") or not shutil.which("gzip"):
        pytest.skip("нет bash/gzip")
    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "backup.sh", proj / "scripts" / "backup.sh")
    (proj / ".env.prod").write_text(env_lines)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    body = _FAKE_DOCKER
    if fail_dump:
        body = body.replace("head -c 4096 /dev/urandom", "exit 3")
    docker.write_text(body)
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    backups = tmp_path / "backups"
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "BACKUP_DIR": str(backups)}
    proc = subprocess.run(
        ["bash", str(proj / "scripts" / "backup.sh"), "single"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, backups


def test_runs_to_the_end_without_optional_keys(tmp_path):
    proc, backups = _run(tmp_path, "DB_NAME=platform\nDB_USER=platform\nDB_PASSWORD=x\n")
    assert proc.returncode == 0, proc.stderr
    assert "backup done" in proc.stdout
    names = sorted(p.name for p in backups.iterdir())
    assert any(n.startswith("db-") for n in names)
    assert any(n.startswith("media-") for n in names)


def test_failure_is_loud_not_silent(tmp_path):
    proc, _ = _run(tmp_path, "DB_NAME=platform\nDB_USER=platform\n", fail_dump=True)
    assert proc.returncode != 0
    assert "backup FAILED" in proc.stderr
