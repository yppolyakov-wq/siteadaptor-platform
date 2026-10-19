from django.core.cache import cache

from apps.core.jobs import idempotent_task


def dedupe_key(update_id) -> str:
    return f"tgplat:{update_id}"


# T-8.10h: апдейт общего бота. Дедуп по update_id (Telegram повторяет доставку); сутки.
@idempotent_task(lock_timeout=86400)
def platform_bot_update(*, update):
    from . import handler

    try:
        return {"result": handler.handle(update)}
    except Exception:
        # Сбой обработки (БД, сеть) не должен на сутки «съесть» апдейт: повтор Celery или
        # Telegram обязан пройти мимо дедупа. Обработчики идемпотентны (bind/mark_*).
        cache.delete(f"job_lock:{dedupe_key(update.get('update_id'))}")
        raise
