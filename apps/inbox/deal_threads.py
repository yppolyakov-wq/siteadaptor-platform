"""C1/C2 (план deal-comms-plan-2026-08-25): тред «сделка ↔ клиент».

C1 — owner-first тред с карточки сделки (кнопка «Nachricht an den Kunden»);
C2 — авто-склейка «запрос с сайта → сделка» при однозначности.

Канонический ref: ``ref_kind`` = kind сделки, ``ref_id`` = reference_code —
как у problem-гейта LS-6 и problem-полосы доски (transactions). Легаси-треды
LS-3 писали ``ref_id = UUID заказа`` (нормализовано той же волной) — поиск
существующего треда принимает оба значения фолбэком.

Подписи сделок (``ref_label``, system-сообщения) — НЕМЕЦКИЕ строки данных, не
gettext: это запись в тред (прецедент offers «✅ Angebot angenommen …»),
инвариант «переводится показ, а не запись».
"""

from .models import Conversation, Message

# Единственное число для подписи сделки в треде (KIND_LABEL транзакций — множественное).
KIND_WORD = {
    "order": "Bestellung",
    "booking": "Termin",
    "stay": "Buchung",
    "ticket": "Ticket",
    "job": "Auftrag",
    "reservation": "Reservierung",
}


def deal_ref_label(kind: str, reference_code: str) -> str:
    """«Bestellung B-123» — подпись сделки для subject/ref_label треда."""
    word = KIND_WORD.get(kind, kind)
    return f"{word} {reference_code}".strip()


def find_thread(kind: str, reference_code: str, pk=None):
    """Существующий тред сделки (свежайший): ref_id = reference_code (канон)
    или str(pk) (легаси LS-3). None — треда нет."""
    ids = [v for v in (str(reference_code or ""), str(pk or "")) if v]
    if not ids:
        return None
    return Conversation.objects.filter(ref_kind=kind, ref_id__in=ids).first()


def adopt_open_thread(customer, *, ref_kind: str, ref_id: str, ref_label: str = "") -> None:
    """C2: склейка «запрос → сделка» — если у клиента ровно ОДИН открытый тред
    без привязки (обычный вопрос с сайта), свежая сделка прикрепляется к нему:
    история «спросил → купил» остаётся одной беседой. Только при однозначности
    (0 или ≥2 открытых треда → ничего). Fail-soft: любая ошибка глотается —
    создание сделки важнее склейки.

    Ревью 2026-08-25 (три правки):
    - НЕ трогаем high-треды: problem-полоса доски ищет open/pending+high по ref
      сделки — склейка превратила бы жалобу «вообще» в «проблему по этому заказу»,
      а свежий заказ получил бы красную полосу ни за что;
    - НЕ трогаем тред с предложением (offers): accept_offer сам проставит ref и
      напишет свою отметку — иначе две одинаковые системные строки подряд;
    - `unread_for_staff` восстанавливаем после system-отметки: post_message гасит
      флаг для любой не-клиентской роли, и неотвеченный вопрос молча исчезал бы
      из бейджа, списка тредов, карточки CRM и дайджеста владельца.
    """
    try:
        if customer is None or not ref_id:
            return
        open_threads = list(
            Conversation.objects.filter(
                customer=customer,
                status__in=(Conversation.STATUS_OPEN, Conversation.STATUS_PENDING),
                ref_kind="",
            ).exclude(priority=Conversation.PRIORITY_HIGH)[:2]
        )
        if len(open_threads) != 1:
            return
        conv = open_threads[0]
        if conv.offers.exists():
            return  # тред предложения — ref проставит accept_offer
        was_unread = conv.unread_for_staff
        conv.ref_kind = (ref_kind or "")[:20]
        conv.ref_id = str(ref_id)[:64]
        conv.ref_label = (ref_label or str(ref_id))[:200]
        conv.save(update_fields=["ref_kind", "ref_id", "ref_label", "updated_at"])
        # Отметка в ленте — system-роль не порождает письма (как у offers).
        from .services import post_message

        post_message(conv, body=f"🔗 {conv.ref_label}", author_role=Message.AUTHOR_SYSTEM)
        if was_unread:
            # Вопрос клиента остаётся непрочитанным — на него ещё не ответили.
            Conversation.objects.filter(pk=conv.pk).update(unread_for_staff=True)
    except Exception:  # noqa: BLE001 — склейка best-effort
        pass
