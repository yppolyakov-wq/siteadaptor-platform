from apps.core.jobs import idempotent_task


@idempotent_task()
def purge_ai_usage():
    """Beat (раз в сутки): удалить учёт ИИ старше AI_USAGE_RETENTION_DAYS (AI-0b)."""
    from . import usage

    return usage.purge()
