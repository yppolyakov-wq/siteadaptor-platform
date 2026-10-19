from apps.core.jobs import idempotent_task


# T-8.10h: апдейт общего бота. Дедуп по update_id (Telegram повторяет доставку); сутки.
@idempotent_task(lock_timeout=86400)
def platform_bot_update(*, update):
    from . import handler

    return {"result": handler.handle(update)}
