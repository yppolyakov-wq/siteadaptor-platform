"""AIS A-5d: «Das funktioniert nicht / ich brauche einen Menschen» — из поля помощника прямо в
Support (план docs/ais-a5-one-brain-plan-2026-11-06.md §4 + правки архитектора §9 п. 9–10).

Помощник не отвечает выдумкой, а предлагает отправить обращение людям: карточка с ПРЕВЬЮ
(свои последние вопросы этого пользователя, без ответов ИИ, без данных клиентов; контакты уже
вычищены `prepare_question` → `pii.scrub`, и ещё раз при отправке). Отправляется только по
кнопке; текст владелец может поправить. Один тред «[Assistent]» на неделю — новые обращения
дописываются в него. Платформу уведомляет сам `support.services.add_message` (второго
уведомления нет).
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

SUBJECT_PREFIX = "[Assistent]"
BODY_MAX = 2000
RECENT = 3
RECENT_WINDOW = timedelta(hours=1)
THREAD_WINDOW = timedelta(days=7)
LIMIT_USER, LIMIT_TENANT, WINDOW = 3, 10, 3600

_W, _E = r"(?<!\w)", r"(?!\w)"
#: явная ПРОСЬБА о человеке/поддержке или жалоба «не работает» на пяти языках кабинета.
#: Голые «Mensch/человек/Mitarbeiter/support» — обычная лексика («pro Mensch», «на 20
#: человек», «supported») и сюда не входят (ревью безопасности A-5d).
_HUMAN = re.compile(
    _W + r"(?:"
    r"funktioniert\s+(?:gar\s+)?nicht|klappt\s+(?:gar\s+)?nicht|geht\s+(?:gar\s+)?nicht"
    r"|(?:mit\s+)?(?:einem|einer)\s+menschen?\s+sprechen|echte[nr]?\s+(?:person|menschen?)"
    r"|support\s+(?:kontaktier\w*|schreiben|anschreiben|fragen)|an\s+den\s+support"
    r"|kundendienst\w*"
    r"|(?:does\s*n[o']?t|is\s+not|isn'?t)\s+working|doesn'?t\s+work|not\s+working"
    r"|talk\s+to\s+(?:a\s+)?(?:human|person|someone)|real\s+person|contact\s+support"
    r"|не\s+работает|не\s+получается|живы\w*\s+человек\w*|позов\w*\s+человек\w*"
    r"|(?:свяж\w*|напиш\w*)\s+(?:с\s+|в\s+)?поддержк\w*|оператор\w*"
    r"|не\s+працює|не\s+виходить|жив\w*\s+людин\w*"
    r"|(?:зв.яж\w*|напиш\w*)\s+(?:з\s+|в\s+)?підтримк\w*"
    r"|çalışmıyor|olmuyor|bir\s+insanla|destek(?:le|e)\s+\w+|destek\s+ekibi\w*"
    r")" + _E,
    re.IGNORECASE,
)


def intent(request, q: str) -> bool:
    """Просьба о человеке/«не работает». Фраза создания («Mitarbeiter anlegen», «Support-Seite
    anlegen») — не эскалация: её разбирают правила создания."""
    from apps.core import assistant_changes

    if not q or assistant_changes._CREATE.search(q):
        return False
    return bool(_HUMAN.search(q))


def _recent_questions(request, q: str) -> list[str]:
    from apps.core.models import AssistantTurn

    since = timezone.now() - RECENT_WINDOW
    rows = (
        AssistantTurn.objects.filter(user=request.user, created_at__gte=since)
        .order_by("-created_at")
        .values_list("question", flat=True)[:RECENT]
    )
    out = [r for r in reversed(list(rows)) if r and r != q]
    return [*out, q]


def preview(request, q: str, seite: str = "") -> str:
    lines = [f"– {line}" for line in _recent_questions(request, q)]
    text = "\n".join(lines)
    if seite:
        text += "\n\n" + _("Seite: %(seite)s") % {"seite": seite}
    return text[:BODY_MAX]


def handle(request, q: str, seite: str = "") -> dict:
    """Карточка «An den Support senden?» с превью (ничего не отправляет)."""
    import uuid

    job = uuid.uuid4().hex
    entry = {
        "state": "done",
        "outcome": "escalate",
        "job": job,
        "preview": preview(request, q, seite),
        "question": q,  # тема треда — из текущего вопроса
    }
    return _put(request, job, entry, q)


def _put(request, job: str, entry: dict, q: str) -> dict:
    from apps.core import assistant_ai, ratelimit

    schema, user_pk = assistant_ai._schema_name(), request.user.pk
    if ratelimit.hit(
        "assistant-ask-req",
        f"{schema}:{user_pk}",
        limit=assistant_ai.REQ_LIMIT,
        window=assistant_ai.RATE_WINDOW,
    ):
        return {"code": "quota"}
    try:
        assistant_ai._put(schema, user_pk, entry, assistant_ai.RESULT_TTL, job=job, q=q)
    except Exception:  # noqa: BLE001 — Redis недоступен: спокойное сообщение
        logger.warning("assistant escalate: entry not stored", exc_info=True)
        return {"code": "unavailable"}
    return {"job": job}


class SendError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def send(request, entry: dict, text: str):
    """Отправить в Support. Возвращает тред. Бросает SendError(quota|empty)."""
    from apps.ai import guard
    from apps.core import ratelimit
    from apps.core.pii import scrub

    # нормализация как у вопроса (full-width «＠» и т. п.), затем маскер контактов
    body = scrub(guard.normalize(str(text or ""))).strip()[:BODY_MAX]
    if not body:
        raise SendError("empty")
    tenant = request.tenant
    user_scope = ("assistant-support", f"{tenant.schema_name}:{request.user.pk}")
    tenant_scope = ("assistant-support-t", tenant.schema_name)
    if ratelimit.hit(*user_scope, limit=LIMIT_USER, window=WINDOW):
        raise SendError("quota")
    if ratelimit.hit(*tenant_scope, limit=LIMIT_TENANT, window=WINDOW):
        ratelimit.refund(*user_scope)
        raise SendError("quota")
    try:
        return _write(tenant, request.user, entry, body)
    except Exception:
        ratelimit.refund(*user_scope)  # обращение не ушло — попытки назад
        ratelimit.refund(*tenant_scope)
        raise


def _write(tenant, user, entry: dict, body: str):
    from apps.support import services
    from apps.support.models import SupportMessage, SupportThread

    who = getattr(user, "email", "") or str(user.pk)
    # треды — общие для команды бизнеса: в тексте видно, кто написал
    body = body + "\n\n— " + _("Aus dem Assistenten gesendet von %(who)s") % {"who": who}
    since = timezone.now() - THREAD_WINDOW
    thread = (
        SupportThread.objects.filter(
            tenant=tenant,
            status=SupportThread.STATUS_OPEN,
            subject__startswith=SUBJECT_PREFIX,
            last_message_at__gte=since,
        )
        .order_by("-last_message_at")
        .first()
    )
    if thread is not None:
        services.add_message(thread, body=body, author_role=SupportMessage.AUTHOR_OWNER)
        return thread
    # тема — из ТЕКУЩЕГО вопроса (в превью первым может стоять более ранний)
    topic = services.one_line(entry.get("question") or "")[:80]
    subject = f"{SUBJECT_PREFIX} {topic}".strip()
    return services.open_thread(tenant=tenant, subject=subject, body=body)
