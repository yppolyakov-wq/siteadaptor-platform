"""FB-33 M3-9b: одна блокировка на операции над схемами, которые нельзя вести одновременно.

Деплой мигрирует схемы всех бизнесов, пересев демо (`seed_demo_tenants`) удаляет и создаёт
схемы заново. Вместе они давали `MigrationSchemaMissing`: пересев удалял схему, которую в
этот момент мигрировал деплой (сервер, 2026-11-21). Теперь обе операции берут ОДНУ
блокировку — вторая ждёт первую, а не дождавшись срока, выходит с понятным сообщением.

Устройство:

* блокировка — сессионная advisory-блокировка Postgres (`pg_try_advisory_lock`, один ключ
  `KEY`): живёт, пока живо соединение, и сама снимается, если процесс упал — «забытых»
  блокировок не бывает;
* соединение блокировки — ОТДЕЛЬНОЕ (`connections.create_connection`), не рабочее
  соединение Django: команда под блокировкой вправе закрывать и пересоздавать свои
  соединения (параллельный исполнитель `migrate_schemas` делает `connections.close_all()`
  и порождает процессы; `seed_demo_tenants --jobs N` — подпроцессы), блокировка этого не
  замечает. Через пулер соединений в режиме transaction сессионные блокировки не работают —
  соединение блокировки должно идти в Postgres напрямую (сейчас так и есть); смена
  сессии проверяется (`pg_backend_pid` до взятия, после и перед снятием) — `SessionChanged`;
* `hold()` на время блокировки ставит переменную окружения `ENV_HELD`: порождённые процессы
  (подпроцессы пересева, команда под `run_locked`) её наследуют и свою блокировку не берут —
  иначе ждали бы родителя вечно;
* `manage.py run_locked <команда> …` (`run`) берёт блокировку и ведёт команду ПОДПРОЦЕССОМ:
  процесс, держащий блокировку, сам ничего не мигрирует и соединений не теряет.

Срок ожидания — `OPS_LOCK_TIMEOUT` секунд (по умолчанию 900) либо `--lock-timeout`.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
import sys
import time

from django.db import DEFAULT_DB_ALIAS, connections

logger = logging.getLogger(__name__)

#: Ключ advisory-блокировки (общие на всю базу; в коде других ключей-констант нет — прочие
#: блокировки берутся `hashtext(...)` в пределах транзакции).
KEY = 3390_2026_1121
#: «Блокировка у родителя» — порождённым процессам её брать не надо.
ENV_HELD = "SITEADAPTOR_OPS_LOCK_HELD"
ENV_TIMEOUT = "OPS_LOCK_TIMEOUT"
DEFAULT_TIMEOUT = 900
#: Код выхода `run_locked`, когда блокировку не дождались (EX_TEMPFAIL): deploy.sh отличает
#: «занято» от сбоя самой команды.
EXIT_BUSY = 75
_APP_PREFIX = "ops-lock: "


#: Соединение блокировки часами молчит, пока идут миграции: без keepalive его срезал бы
#: сетевой экран между приложением и базой — и блокировка пропала бы без единой ошибки.
_KEEPALIVE = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}


class Busy(Exception):
    """Блокировку держит другая операция и за срок ожидания она не освободилась."""


class SessionChanged(RuntimeError):
    """Запросы соединения блокировки попали в разные сессии Postgres (между приложением
    и базой — пулер в режиме transaction): сессионная блокировка так не работает."""


def _connect():
    """Отдельное соединение под блокировку (не открыто). Настройки базы — копией: общий
    словарь `settings_dict` рабочих соединений не трогаем."""
    conn = connections.create_connection(DEFAULT_DB_ALIAS)
    options = {**_KEEPALIVE, **(conn.settings_dict.get("OPTIONS") or {})}
    conn.settings_dict = {**conn.settings_dict, "OPTIONS": options}
    return conn


def _backend_pid(cursor) -> int:
    cursor.execute("SELECT pg_backend_pid()")
    return cursor.fetchone()[0]


def default_timeout() -> int:
    raw = os.environ.get(ENV_TIMEOUT, "")
    try:
        return max(0, int(raw)) if raw.strip() else DEFAULT_TIMEOUT
    except ValueError:
        return DEFAULT_TIMEOUT


def _holder(cursor) -> str:
    """Кто держит блокировку (подпись его соединения) — для сообщения; "" если не узнать."""
    try:
        cursor.execute(
            "SELECT a.application_name FROM pg_locks l"
            " JOIN pg_stat_activity a ON a.pid = l.pid"
            " WHERE l.locktype = 'advisory' AND l.granted AND l.objsubid = 1"
            " AND l.classid = %s AND l.objid = %s AND l.database ="
            " (SELECT oid FROM pg_database WHERE datname = current_database())",
            [KEY >> 32, KEY & 0xFFFFFFFF],
        )
        row = cursor.fetchone()
    except Exception:  # noqa: BLE001 — подпись необязательна, сообщение выйдет и без неё
        logger.debug("ops lock: holder lookup failed", exc_info=True)
        return ""
    name = (row[0] if row else "") or ""
    return name[len(_APP_PREFIX) :] if name.startswith(_APP_PREFIX) else name


def _busy_message(what: str, holder: str, timeout: float) -> str:
    return (
        f"Блокировка операций над схемами занята{f' ({holder})' if holder else ''}: "
        f"«{what or 'операция'}» не дождалась её за {int(timeout)} с. Одновременно деплой и "
        f"пересев демо не идут. Дождитесь конца идущей операции и запустите снова "
        f"(срок ожидания — {ENV_TIMEOUT}, секунды). Кто держит: SELECT pid, application_name, "
        f"backend_start FROM pg_stat_activity WHERE application_name LIKE '{_APP_PREFIX.strip()}%'; "
        f"зависшего держателя снимает SELECT pg_terminate_backend(<pid>)."
    )


@contextlib.contextmanager
def session_lock(timeout: float | None = None, what: str = "", poll: float = 2.0, log=None):
    """Взять блокировку на отдельном соединении (ждать до `timeout` с) либо `Busy`.

    `what` — подпись операции: её увидит тот, кто не дождётся. `log(текст)` — куда сказать
    «жду» (один раз). Переменную окружения не трогает — для этого `hold`."""
    timeout = default_timeout() if timeout is None else max(0.0, float(timeout))
    conn = _connect()
    try:
        conn.ensure_connection()
        conn.set_autocommit(True)
        deadline = time.monotonic() + timeout
        told = False
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('application_name', %s, false)",
                [f"{_APP_PREFIX}{what or 'операция'}"[:63]],
            )
            pid = _backend_pid(cursor)
            while True:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [KEY])
                if cursor.fetchone()[0]:
                    break
                holder = _holder(cursor)
                if time.monotonic() >= deadline:
                    raise Busy(_busy_message(what, holder, timeout))
                if not told and log is not None:
                    log(
                        f"Блокировка операций над схемами занята"
                        f"{f' ({holder})' if holder else ''} — жду до {int(timeout)} с…"
                    )
                    told = True
                time.sleep(min(poll, max(0.0, deadline - time.monotonic())))
            if _backend_pid(cursor) != pid:
                # блокировка взята в чужой сессии и ничего не защищает; снимать её нечем —
                # она уйдёт вместе с той сессией (закрываем соединение ниже)
                raise SessionChanged(
                    "Блокировка операций над схемами не работает: запросы одного соединения "
                    "попадают в разные сессии Postgres (пулер соединений в режиме "
                    "transaction?). Соединение блокировки должно идти в базу напрямую — "
                    f"«{what or 'операция'}» не начата."
                )
        try:
            yield
        finally:
            _release(conn, what, pid)
    finally:
        conn.close()


def _release(conn, what: str, pid: int) -> None:
    """Снять блокировку; если соединение за время операции пропало либо сессия сменилась —
    блокировки уже не было, и об этом надо сказать громко (операция шла без защиты)."""
    try:
        with conn.cursor() as cursor:
            same = _backend_pid(cursor) == pid
            cursor.execute("SELECT pg_advisory_unlock(%s)", [KEY])
            held = cursor.fetchone()[0] and same
    except Exception:  # noqa: BLE001 — обрыв соединения: блокировку Postgres снял сам
        held = False
    if not held:
        logger.error(
            "ops lock: блокировка потеряна во время «%s» (соединение с базой оборвалось "
            "или сменилась сессия) — операция шла без защиты от параллельной; проверьте "
            "migration_state",
            what or "операция",
        )


@contextlib.contextmanager
def hold(timeout: float | None = None, what: str = "", poll: float = 2.0, log=None):
    """Блокировка на время операции. Если её уже держит родитель (`ENV_HELD`) — сразу
    внутрь; иначе берёт сама и помечает окружение для порождённых процессов."""
    if os.environ.get(ENV_HELD) == "1":
        # видно в выводе: переменная, случайно попавшая в .env, выключила бы блокировку молча
        logger.warning(
            "ops lock: «%s» идёт без своей блокировки — %s=1 (её держит родительский процесс)",
            what or "операция",
            ENV_HELD,
        )
        yield
        return
    with session_lock(timeout=timeout, what=what, poll=poll, log=log):
        os.environ[ENV_HELD] = "1"
        try:
            yield
        finally:
            os.environ.pop(ENV_HELD, None)


def _terminate(signum, _frame):
    raise SystemExit(128 + signum)


def run(argv: list[str], timeout: float | None = None, log=None) -> int:
    """`manage.py <argv>` подпроцессом под блокировкой; код выхода команды. `Busy` — если
    блокировку не дождались (команда не запускалась)."""
    what = " ".join(argv)
    with hold(timeout=timeout, what=what, log=log):
        proc = subprocess.Popen([sys.executable, sys.argv[0], *argv])  # noqa: S603 — argv оператора
        previous = None
        try:
            # SIGTERM (docker stop) по умолчанию убивает без finally — команда осталась бы
            # без родителя и без блокировки; гасим её вместе с собой
            previous = signal.signal(signal.SIGTERM, _terminate)
        except ValueError:  # не главный поток (тесты) — обработчик не ставится
            previous = None
        try:
            return proc.wait()
        except BaseException:
            _stop(proc)
            raise
        finally:
            if previous is not None:
                signal.signal(signal.SIGTERM, previous)


def _stop(proc) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=30)
    except Exception:  # noqa: BLE001 — уже завершилась либо не отвечает: добиваем
        with contextlib.suppress(Exception):
            proc.kill()
