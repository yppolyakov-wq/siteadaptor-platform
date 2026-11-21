"""FB-33 M3-9b: `manage.py run_locked <команда> [аргументы…]` — команда под общей
блокировкой операций над схемами (`apps.core.ops_lock`).

    python manage.py run_locked migrate_schemas --tenant --executor=multiprocessing
    python manage.py run_locked --lock-timeout 60 migrate_schemas --shared

Блокировку держит этот процесс на отдельном соединении, команда идёт подпроцессом; код
выхода — код команды. Блокировку не дождались — команда НЕ запускается, код выхода
`ops_lock.EXIT_BUSY` (75), в stderr — кто держит и что делать.
"""

import argparse
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.core import ops_lock


class Command(BaseCommand):
    help = "Выполнить команду manage.py под блокировкой операций над схемами."
    requires_system_checks = []  # проверки делает сама команда в подпроцессе

    def add_arguments(self, parser):
        parser.add_argument(
            "--lock-timeout",
            type=int,
            default=None,
            help=f"сколько секунд ждать блокировку (по умолчанию ${ops_lock.ENV_TIMEOUT} "
            f"или {ops_lock.DEFAULT_TIMEOUT})",
        )
        parser.add_argument("argv", nargs=argparse.REMAINDER, help="команда и её аргументы")

    def handle(self, *args, **options):
        argv = list(options["argv"])
        if argv[:1] == ["--"]:
            argv = argv[1:]
        if not argv:
            raise CommandError("Нужна команда: manage.py run_locked <команда> [аргументы…]")
        if argv[0] == "run_locked":
            raise CommandError("run_locked внутри run_locked не нужен.")

        def log(text):
            self.stderr.write(text)
            self.stderr.flush()

        try:
            code = ops_lock.run(argv, timeout=options["lock_timeout"], log=log)
        except ops_lock.Busy as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            sys.exit(ops_lock.EXIT_BUSY)
        if code:
            sys.exit(code)
