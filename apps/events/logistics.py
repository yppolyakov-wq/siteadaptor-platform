"""Закупка услуг по точкам маршрута (MT-4) — «книга броней» гида.

Что бронирует организатор тура: ночи в чужих отелях, места в транспорте,
экскурсии, пермиты, локальных гидов. Существующие механизмы не подошли:

* `apps/stays` смотрит ВНУТРЬ (гость бронирует у нас) — исходящих броней там нет;
* закупки склада (`inventory.Bestellung`) требуют товар из каталога и двигают
  остаток — для услуги это бессмысленно;
* швы `Order.parent_order`/`supplier_tenant_schema` пассивны (без резолвера).

Поэтому — своя лёгкая модель. Справочник поставщиков переиспользуем как есть
(`inventory.Lieferant`): у отеля, автобусной компании и гида одни и те же поля.

**Закупочная цена наружу не отдаётся никогда** — ни при каком флаге видимости:
`visible_to_participants` открывает участнику факт («Ночь 3: Hotel X,
подтверждено»), а не то, сколько это стоило гиду.
"""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel


class SupplierBooking(TimestampedModel):
    KIND_HOTEL = "hotel"
    KIND_TRANSPORT = "transport"
    KIND_EXCURSION = "excursion"
    KIND_PERMIT = "permit"
    KIND_GUIDE = "guide"
    KIND_OTHER = "other"
    KINDS = [
        (KIND_HOTEL, _("Unterkunft")),
        (KIND_TRANSPORT, _("Transport / Tickets")),
        (KIND_EXCURSION, _("Ausflug")),
        (KIND_PERMIT, _("Permit / Genehmigung")),
        (KIND_GUIDE, _("Guide vor Ort")),
        (KIND_OTHER, _("Sonstiges")),
    ]

    STATUS_TO_BOOK = "to_book"
    STATUS_REQUESTED = "requested"
    STATUS_CONFIRMED = "confirmed"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_TO_BOOK, _("Zu buchen")),
        (STATUS_REQUESTED, _("Angefragt")),
        (STATUS_CONFIRMED, _("Bestätigt")),
        (STATUS_PAID, _("Bezahlt")),
        (STATUS_CANCELLED, _("Storniert")),
    ]
    #: Статусы, которые ещё требуют действия гида перед стартом.
    OPEN_STATUSES = (STATUS_TO_BOOK, STATUS_REQUESTED)

    # MX-4: закупка живёт не только у заезда — event стал nullable, generic-ссылка
    # ref_kind/ref_id указывает на любую сделку/опцию (пусто = общая закупка).
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="supplier_bookings",
    )
    ref_kind = models.CharField(max_length=20, blank=True, default="")
    ref_id = models.CharField(max_length=64, blank=True, default="")
    kind = models.CharField(max_length=20, choices=KINDS, default=KIND_HOTEL)
    supplier = models.ForeignKey(
        "inventory.Lieferant", null=True, blank=True, on_delete=models.SET_NULL
    )
    # Свободное имя, пока поставщика не завели в справочник (гид в дороге).
    supplier_name = models.CharField(max_length=200, blank=True)
    day = models.PositiveSmallIntegerField(default=0)  # день маршрута (0 = не привязан)
    date = models.DateField(null=True, blank=True)
    stop = models.CharField(max_length=200, blank=True)  # точка: «Jispa», «Leh»
    qty = models.PositiveSmallIntegerField(default=1)  # комнат/мест
    # Закупочная цена. Владелец решил (§0b.6): EUR обязателен, оригинал — рядом.
    cost_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, blank=True)  # INR/NPR — оригинал
    amount_original = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_TO_BOOK)
    confirmation_ref = models.CharField(max_length=120, blank=True)  # номер брони у поставщика
    note = models.CharField(max_length=300, blank=True)
    # Показывать ли участникам (без цен!) — решает гид, дефолт «нет».
    visible_to_participants = models.BooleanField(default=False)
    # Ваучер/подтверждение — приватный файл досье (MT-2), не публичный URL.
    document = models.ForeignKey(
        "documents.SecureDocument", null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["day", "date", "created_at"]
        indexes = [
            models.Index(fields=["event", "status"], name="supbook_event_status_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.supplier_label}"

    @property
    def supplier_label(self) -> str:
        if self.supplier_id and self.supplier:
            return self.supplier.name
        return self.supplier_name or str(_("Ohne Anbieter"))

    @property
    def cost_eur(self) -> Decimal:
        return Decimal(self.cost_cents) / 100

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    def participant_view(self) -> dict:
        """Что видит участник: факт и статус, БЕЗ закупочной цены.

        Отдельный метод, а не фильтр в шаблоне: так «цену не показываем» —
        свойство модели, а не привычка вёрстки.
        """
        return {
            "kind": self.get_kind_display(),
            "stop": self.stop,
            "day": self.day,
            "date": self.date,
            "supplier": self.supplier_label,
            "confirmed": self.status in (self.STATUS_CONFIRMED, self.STATUS_PAID),
            "note": self.note,
        }


class TourTask(TimestampedModel):
    """Чек-лист подготовки заезда (MT-6): пермиты, ТО техники, брифинг.

    Намеренно НЕ новый вид карточек Kanban: доска работает со сделками, у которых
    есть FSM и деньги, а здесь нужен простой список «сделано/не сделано» с
    дедлайном и ответственным.
    """

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="prep_tasks")
    title = models.CharField(max_length=200)
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="tour_tasks"
    )
    done_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "due_date", "created_at"]

    def __str__(self):
        return self.title

    @property
    def is_done(self) -> bool:
        return self.done_at is not None

    def is_overdue(self, today=None) -> bool:
        """Просрочена = есть срок, он прошёл, и задача не закрыта."""
        if self.done_at is not None or self.due_date is None:
            return False
        from django.utils import timezone

        return self.due_date < (today or timezone.localdate())
