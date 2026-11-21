"""FB-33 M3-9b: одна блокировка на операции, которые нельзя вести одновременно, —
миграции деплоя и пересев демо (пересев удаляет схему, которую мигрирует деплой →
`MigrationSchemaMissing`). Блокировка — сессионная advisory-блокировка Postgres на
отдельном соединении; `scripts/deploy.sh` ведёт миграции через `manage.py run_locked`."""

import os
import pathlib
import re
import subprocess
import threading
import time

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def ops_lock(monkeypatch):
    from apps.core import ops_lock as module

    monkeypatch.delenv(module.ENV_HELD, raising=False)
    return module


# --- сама блокировка --------------------------------------------------------------------


def test_second_lock_is_not_taken(ops_lock):
    with ops_lock.session_lock(timeout=0):
        with pytest.raises(ops_lock.Busy):
            with ops_lock.session_lock(timeout=0):
                pass
    with ops_lock.session_lock(timeout=0):  # отпущена — берётся снова
        pass


def test_lock_lives_on_its_own_connection(ops_lock):
    """Соединение блокировки — своё, не рабочее соединение Django: команда под блокировкой
    вправе закрывать и пересоздавать рабочие (`connections.close_all()` параллельного
    исполнителя миграций, подпроцессы пересева) — блокировка от этого не отпускается."""
    from django.db import connection

    with ops_lock.session_lock(timeout=0):
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [ops_lock.KEY])
            assert cur.fetchone()[0] is False  # рабочее соединение её не держит и не возьмёт
    with connection.cursor() as cur:  # отпущена вместе с соединением блокировки
        cur.execute("SELECT pg_try_advisory_lock(%s)", [ops_lock.KEY])
        assert cur.fetchone()[0] is True
        cur.execute("SELECT pg_advisory_unlock(%s)", [ops_lock.KEY])


def test_lock_waits_for_release(ops_lock):
    taken, release = threading.Event(), threading.Event()

    def holder():
        with ops_lock.session_lock(timeout=0):
            taken.set()
            release.wait(10)

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert taken.wait(10)
        threading.Timer(0.3, release.set).start()
        started = time.monotonic()
        with ops_lock.session_lock(timeout=10, poll=0.05):
            assert time.monotonic() - started >= 0.2
    finally:
        release.set()
        thread.join(10)


def test_timeout_message_names_the_way_out(ops_lock):
    with ops_lock.session_lock(timeout=0, what="migrate_schemas --tenant"):
        with pytest.raises(ops_lock.Busy) as exc:
            with ops_lock.session_lock(timeout=0, what="seed_demo_tenants"):
                pass
    text = str(exc.value)
    assert "migrate_schemas --tenant" in text  # кто держит
    assert "seed_demo_tenants" in text  # кто не дождался


def test_hold_marks_children_and_is_reentrant(ops_lock):
    with ops_lock.hold(timeout=0):
        assert os.environ[ops_lock.ENV_HELD] == "1"  # подпроцессы (--jobs) её не берут
        with ops_lock.hold(timeout=0):  # тот же процесс — без взаимной блокировки
            pass
        assert os.environ[ops_lock.ENV_HELD] == "1"
        with pytest.raises(ops_lock.Busy):
            with ops_lock.session_lock(timeout=0):
                pass
    assert ops_lock.ENV_HELD not in os.environ
    with ops_lock.session_lock(timeout=0):
        pass


# --- manage.py run_locked ---------------------------------------------------------------


class _FakeProc:
    def __init__(self, code, seen, ops_lock):
        self.code, self.seen, self.ops_lock = code, seen, ops_lock

    def wait(self, timeout=None):
        self.seen["env_held"] = os.environ.get(self.ops_lock.ENV_HELD)
        try:
            with self.ops_lock.session_lock(timeout=0):
                self.seen["locked"] = False
        except self.ops_lock.Busy:
            self.seen["locked"] = True
        return self.code


def test_run_locked_passes_arguments_and_exit_code(ops_lock, monkeypatch):
    seen = {}

    def popen(argv, **kwargs):
        seen["argv"] = argv
        return _FakeProc(3, seen, ops_lock)

    monkeypatch.setattr(ops_lock.subprocess, "Popen", popen)
    with pytest.raises(SystemExit) as exc:
        call_command("run_locked", "migrate_schemas", "--tenant", "--executor=multiprocessing")
    assert exc.value.code == 3
    assert seen["argv"][2:] == ["migrate_schemas", "--tenant", "--executor=multiprocessing"]
    assert seen["locked"] is True and seen["env_held"] == "1"
    with ops_lock.session_lock(timeout=0):  # после команды отпущена
        pass


def test_run_locked_busy_exits_with_own_code_and_runs_nothing(ops_lock, monkeypatch, capsys):
    monkeypatch.setattr(
        ops_lock.subprocess, "Popen", lambda *a, **k: pytest.fail("команда запущена")
    )
    with ops_lock.session_lock(timeout=0, what="seed_demo_tenants"):
        with pytest.raises(SystemExit) as exc:
            call_command("run_locked", "--lock-timeout", "0", "migrate_schemas", "--shared")
    assert exc.value.code == ops_lock.EXIT_BUSY != 1
    assert "seed_demo_tenants" in capsys.readouterr().err


# --- пересев демо -----------------------------------------------------------------------


def test_reseed_does_not_start_while_the_lock_is_held(ops_lock, monkeypatch):
    from apps.tenants.management.commands import seed_demo_tenants

    monkeypatch.setattr(
        seed_demo_tenants.Command,
        "_seed_one",
        lambda *a, **k: pytest.fail("пересев пошёл под чужой блокировкой"),
    )
    with ops_lock.session_lock(timeout=0, what="migrate_schemas --tenant"):
        # CommandError → manage.py выходит с кодом 1
        with pytest.raises(CommandError, match="migrate_schemas --tenant"):
            call_command("seed_demo_tenants", "--kit", "shop", "--lock-timeout", "0")


def test_reseed_takes_the_lock_while_seeding(ops_lock, monkeypatch):
    from apps.tenants.management.commands import seed_demo_tenants

    seen = {}

    def seed_one(self, key, options):
        try:
            with ops_lock.session_lock(timeout=0):
                seen[key] = False
        except ops_lock.Busy:
            seen[key] = True
        return True

    monkeypatch.setattr(seed_demo_tenants.Command, "_seed_one", seed_one)
    call_command("seed_demo_tenants", "--kit", "shop")
    assert seen == {"shop": True}
    with ops_lock.session_lock(timeout=0):
        pass


def test_reseed_list_needs_no_lock(ops_lock):
    with ops_lock.session_lock(timeout=0):
        call_command("seed_demo_tenants", "--list")


# --- scripts/deploy.sh (статически: Docker-демона в тестах нет) --------------------------


def _deploy() -> str:
    return (ROOT / "scripts" / "deploy.sh").read_text()


def _code(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_deploy_script_is_valid_bash():
    proc = subprocess.run(  # noqa: S603, S607 — фиксированная команда
        ["bash", "-n", str(ROOT / "scripts" / "deploy.sh")], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_deploy_migrations_go_through_the_lock():
    lines = [ln for ln in _code(_deploy()).splitlines() if "migrate_schemas" in ln]
    assert len(lines) == 3
    assert all("manage.py run_locked migrate_schemas" in ln for ln in lines), lines


def test_deploy_stops_on_busy_lock_instead_of_retrying(ops_lock):
    code = _code(_deploy())
    assert f"LOCK_BUSY={ops_lock.EXIT_BUSY}" in code
    # занятая блокировка — не «параллельно не вышло»: повтор по одной схеме ждал бы ещё раз
    assert code.count('"$LOCK_BUSY"') >= 2
    assert "OPS_LOCK_TIMEOUT" in code  # срок ожидания виден и правится


def test_deploy_refuses_a_second_deploy_on_the_host():
    code = _code(_deploy())
    assert re.search(r"flock -n \d+", code)
    assert code.index("flock -n") < code.index("git fetch")  # до любого шага


def test_deploy_cleanup_keeps_rollback_images_and_never_fails():
    code = _code(_deploy())
    assert "IMAGE_KEEP=${IMAGE_KEEP:-5}" in code or 'IMAGE_KEEP="${IMAGE_KEEP:-5}"' in code
    assert "docker builder prune -f --filter until=72h" in code
    assert "cleanup_images || " in code  # ошибка чистки деплой не роняет
    assert code.index("cleanup_images || ") > code.index("docker tag siteadaptor-app:latest")
    # запущенные контейнеры и тома не трогаем: без силы и без широких чисток
    for banned in (
        "system prune",
        "volume prune",
        "--volumes",
        "rmi -f",
        "rmi --force",
        "image prune -a",
        "container prune",
    ):
        assert banned not in code, banned


# --- ревью django-reviewer (2026-11-21) -------------------------------------------------

_REVIEW = pytest.mark.xfail(strict=True, reason="FB-33 M3-9b: замок до кода (ревью)")


@_REVIEW
def test_lock_connection_has_keepalives_and_leaves_settings_alone(ops_lock):
    """Соединение блокировки часами молчит (идут миграции) — без keepalive его срежет
    сетевой экран, и блокировка тихо пропадёт."""
    from django.db import connections

    before = dict(connections["default"].settings_dict.get("OPTIONS") or {})
    params = ops_lock._connect().get_connection_params()
    assert (params["keepalives"], params["keepalives_idle"]) == (1, 30)
    assert (params["keepalives_interval"], params["keepalives_count"]) == (10, 3)
    assert dict(connections["default"].settings_dict.get("OPTIONS") or {}) == before


@_REVIEW
def test_busy_message_says_how_to_find_the_holder(ops_lock):
    with ops_lock.session_lock(timeout=0):
        with pytest.raises(ops_lock.Busy) as exc:
            with ops_lock.session_lock(timeout=0):
                pass
    assert "ops-lock:%" in str(exc.value) and "pg_terminate_backend" in str(exc.value)


@_REVIEW
def test_pooler_that_swaps_sessions_is_a_loud_error_at_take(ops_lock, monkeypatch):
    """Пулер в режиме transaction отдаёт каждому запросу свою сессию: блокировка взята
    «где-то» и ничего не защищает — операция не начинается."""
    pids = iter(range(100, 200))
    monkeypatch.setattr(ops_lock, "_backend_pid", lambda cursor: next(pids))
    with pytest.raises(ops_lock.SessionChanged, match="пулер"):
        with ops_lock.session_lock(timeout=0):
            pytest.fail("операция пошла без блокировки")
    with ops_lock.session_lock(timeout=0):  # и взятая «где-то» блокировка не осталась висеть
        pass


@_REVIEW
def test_session_changed_during_the_operation_is_logged_loudly(ops_lock, monkeypatch, caplog):
    pids = iter([7, 7, 8])
    monkeypatch.setattr(ops_lock, "_backend_pid", lambda cursor: next(pids))
    with caplog.at_level("ERROR", logger="apps.core.ops_lock"):
        with ops_lock.session_lock(timeout=0, what="migrate_schemas --tenant"):
            pass
    assert "migrate_schemas --tenant" in caplog.text and "без защиты" in caplog.text


@_REVIEW
def test_skipping_the_lock_by_environment_is_visible(ops_lock, monkeypatch, caplog):
    """Переменная, случайно попавшая в .env, выключила бы блокировку молча."""
    monkeypatch.setenv(ops_lock.ENV_HELD, "1")
    with caplog.at_level("WARNING", logger="apps.core.ops_lock"):
        with ops_lock.hold(timeout=0, what="seed_demo_tenants"):
            pass
    assert ops_lock.ENV_HELD in caplog.text and "seed_demo_tenants" in caplog.text


@_REVIEW
def test_deploy_body_is_read_whole_and_restarts_itself_after_pull():
    """`git pull` меняет файл под работающим bash: тело — в функции (bash читает её целиком
    до исполнения), а после pull скрипт один раз запускает себя заново — новой версией."""
    text = _deploy()
    code = _code(text)
    assert re.search(r"^main\(\) \{$", code, re.M)
    assert text.rstrip().endswith('main "$@"\nexit')
    pull, reexec = code.index("git pull --ff-only"), code.index('exec "$SELF" "$@"')
    assert pull < reexec < code.index("$COMPOSE build")
    assert 'if [ "${DEPLOY_REEXEC:-0}" != "1" ]; then' in code  # один раз
    assert "export DEPLOY_REEXEC=1" in code


@_REVIEW
def test_deploy_host_lock_lives_in_the_repo_and_is_not_retaken_after_restart():
    code = _code(_deploy())
    assert 'DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-$REPO_DIR/.git/siteadaptor-deploy.lock}"' in code
    assert "/tmp" not in code
    # после перезапуска дескриптор 9 унаследован — второй flock на новый дескриптор отказал бы
    guard = code.index('if [ "${DEPLOY_REEXEC:-0}" = "1" ]; then')
    assert guard < code.index("flock -n 9")


@_REVIEW
def test_deploy_template_schema_goes_through_the_lock():
    lines = [ln for ln in _code(_deploy()).splitlines() if "ensure_template_schema" in ln]
    assert lines and all("manage.py run_locked ensure_template_schema" in ln for ln in lines)
    assert _code(_deploy()).count('"$LOCK_BUSY"') >= 4  # занято — стоп, а не «шаблон не готов»


@_REVIEW
def test_deploy_cleanup_does_not_hide_a_failed_prune():
    code = _code(_deploy())
    line = next(ln for ln in code.splitlines() if "docker builder prune" in ln)
    assert "|" not in line.replace("||", "")
