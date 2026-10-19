"""Фоновые задачи inbox."""

from apps.core.jobs import idempotent_task


@idempotent_task()
def ai_reply_draft(*, schema: str, user_pk, job: str) -> None:
    """T-8.10g: черновик ответа клиенту — вне веб-воркера."""
    from . import ai_reply

    ai_reply.run_job(schema=schema, user_pk=user_pk, job=job)
