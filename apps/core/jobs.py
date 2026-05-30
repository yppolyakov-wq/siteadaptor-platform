"""Идемпотентные Celery-задачи. Спецификация: docs/references/patterns/notification-dedupe.md.

idempotent_task отсекает повторный запуск по dedupe_key через атомарный
cache.add (SET-if-not-exists в Redis) ДО тяжёлой работы. Это оптимизация, не
гарантия — гарантию даёт UNIQUE dedupe_key в БД + проверка статуса перед
внешней отправкой.

Применять ко всем задачам с риском двойного запуска: notify_subscribers,
publish_to_channel, send_trial_reminder, sync_aggregator_listing.
"""

from celery import shared_task
from django.core.cache import cache

DEFAULT_LOCK_TIMEOUT = 3600  # 1 час


def idempotent_task(*task_args, lock_timeout: int = DEFAULT_LOCK_TIMEOUT, **task_kwargs):
    def decorator(fn):
        # Имя задачи по умолчанию — модуль.функция оборачиваемой fn, иначе ВСЕ
        # обёртки регистрируются в Celery как "apps.core.jobs.wrapped" и затирают
        # друг друга в реестре задач.
        task_kwargs.setdefault("name", f"{fn.__module__}.{fn.__qualname__}")

        @shared_task(*task_args, **task_kwargs)
        def wrapped(dedupe_key=None, **kwargs):
            if dedupe_key:
                lock = f"job_lock:{dedupe_key}"
                if not cache.add(lock, "1", timeout=lock_timeout):
                    return {"skipped": True, "reason": "duplicate", "dedupe_key": dedupe_key}
            return fn(**kwargs)

        return wrapped

    return decorator
