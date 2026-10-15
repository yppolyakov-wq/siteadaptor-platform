"""Локальный агрегатор (SHARED): материализованные активные акции для городских
страниц на основном домене.

Акции живут в TENANT-схемах; здесь — денормализованный снимок в public-схеме
(см. tasks.sync_listing), чтобы выдавать предложения по городу/типу бизнеса без
кросс-схемных запросов. Phase 2 расширит до мульти-доменных порталов
(AggregatorPortal).
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import I18nMixin
from apps.tenants.models import Tenant

from . import search_index


def apply_city_filters(qs, city_category=None, city_tag=None):
    """T-8.13a: единая категория каталога города (раздел или категория) и признак.

    Одна реализация для ленты (`views.listings_for`) и главной портала (T-8.19).
    Неизвестное значение фильтр не включает.
    """
    from apps.core import city_categories

    if city_category:
        keys = city_categories.keys_for_filter(city_category)
        if keys:
            qs = qs.filter(city_category__in=keys)
    if city_tag and city_categories.normalize_tags([city_tag]):
        qs = qs.filter(city_tags__contains=[city_tag])
    return qs


class ListingQuerySet(models.QuerySet):
    def public(self):
        """T-8.6: то, что видит посетитель каталога города (единственная точка чтения).

        Активные, не скрытые модерацией и не принадлежащие бизнесу, который СЕЙЧАС не
        может быть в каталоге (приостановлен, выключен, без согласия, почта не
        подтверждена) — фильтр по живому состоянию тенанта, без ресинка: правка в
        админке действует сразу. Сироты без тенанта не отбрасываются (их чистит синк).
        """
        from django.db.models import Q
        from django.utils import timezone

        from .visibility import withheld_schemas

        # Истёкшее не показываем в момент запроса: beat снимает листинг с задержкой
        # до нескольких минут (а при сбое — дольше), ТЗ 2.0 §8 требует проверки сразу.
        return (
            self.filter(is_active=True, hidden_at__isnull=True)
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()))
            .exclude(tenant_schema__in=withheld_schemas())
        )


class AggregatorListing(I18nMixin, models.Model):
    # Вид листинга (A5/A6): акция / размещение по ночам / событие. Один пул, один
    # шаблон карточки; цена/дата/detail_url наполняются по-разному в sync-задачах.
    KIND_PROMOTION = "promotion"
    KIND_STAY = "stay"
    KIND_EVENT = "event"
    KIND_MENU = "menu"  # MEN-5: набор меню (кейтеринг/гастро) — Combo
    # T-8.11: каталог города = все предложения бизнеса, не только акции.
    KIND_PRODUCT = "product"
    KIND_SERVICE = "service"
    KIND_BUSINESS = "business"
    KINDS = [
        (KIND_PROMOTION, _("Promotion")),
        (KIND_STAY, _("Stay")),
        (KIND_EVENT, _("Event")),
        (KIND_MENU, _("Menu")),
        (KIND_PRODUCT, _("Produkt")),
        (KIND_SERVICE, _("Dienstleistung")),
        (KIND_BUSINESS, _("Unternehmen")),
    ]
    # Виды «предложений» — лента портала по умолчанию (без ?kind=): товары одного
    # магазина иначе вытеснили бы акции всех остальных.
    OFFER_KINDS = (KIND_PROMOTION, KIND_STAY, KIND_EVENT, KIND_MENU)

    AVAILABILITY_SOLD_OUT = "sold_out"
    AVAILABILITY_ON_REQUEST = "on_request"

    # --- источник (тенант + объект) ---
    tenant_schema = models.CharField(max_length=63)
    tenant_slug = models.SlugField(max_length=100)
    business_name = models.CharField(max_length=200)
    business_type = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=100, blank=True)
    # T-8.17: slug района (apps.core.districts) — чипы и страницы районов портала.
    district = models.CharField(max_length=100, blank=True)
    # T-8.15: листинг демо-бизнеса — скрыт на настоящих порталах, бейдж «Demo».
    is_demo = models.BooleanField(default=False)
    # R2b: направление/тема для event-листингов (yoga/meditation/…; пусто у
    # promotion/stay). Фильтр «по каталогам/направлениям» в агрегаторе.
    category = models.CharField(max_length=30, blank=True)
    # T-8.13a: ЕДИНАЯ категория каталога города (слаг `core/city_categories`) и
    # признаки — у всех видов листинга. `category` выше остаётся темой события.
    city_category = models.CharField(max_length=40, blank=True, default="", db_index=True)
    city_tags = models.JSONField(default=list, blank=True)
    listing_kind = models.CharField(max_length=20, choices=KINDS, default=KIND_PROMOTION)
    # str(pk) объекта-источника: promo_uuid / StayUnit.pk / Event.pk. Единый ключ
    # листинга вместе с (tenant_schema, listing_kind).
    source_ref = models.CharField(max_length=64, blank=True)
    # Legacy-ключ акций (== source_ref для promotion); nullable — у stay/event пусто.
    promo_uuid = models.UUIDField(null=True, blank=True)

    # --- денормализованная карточка ---
    title = models.JSONField(default=dict)  # {"de": "...", "en": "..."}
    teaser = models.JSONField(default=dict)
    image = models.JSONField(default=dict, blank=True)  # FileRef-envelope
    currency = models.CharField(max_length=3, default="EUR")
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    detail_url = models.URLField()

    # Гео (G8c): denorm координат бизнеса из Tenant (для карты + «рядом»).
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # MEN-5 (kind=menu): атрибуты набора меню для карточки и фильтров агрегатора.
    # Решения владельца 2026-08-13: цена = базовая сборка «ab X €/Gast», мин.
    # заказ ПОКАЗЫВАЕМ прямо в карточке, блюда отдаём в поиск.
    price_per_person = models.BooleanField(default=False)
    min_persons = models.PositiveSmallIntegerField(default=0)
    event_types = models.JSONField(default=list, blank=True)  # поводы («Hochzeit»)
    diets = models.JSONField(default=list, blank=True)  # объединение диет состава
    # Названия блюд состава — «блюда наружу»: `?q=Rinderfilet` находит карточку
    # набора, не плодя отдельный kind="dish".
    dish_names = models.JSONField(default=list, blank=True)

    # T-8.11: наличие товара («" — есть или не учитывается) и бейдж «Neu».
    availability = models.CharField(max_length=20, blank=True, default="")
    is_new = models.BooleanField(default=False)

    is_surprise = models.BooleanField(default=False)  # Überraschungstüte (Track B2)
    # Платное продвижение (P2.4a): до этого момента листинг закреплён сверху
    # выдачи с бейджем «Empfohlen». Срок ставит супер-админ (P2.4b добавит
    # самообслуживание через Stripe). sync_listing поле не трогает.
    featured_until = models.DateTimeField(null=True, blank=True, db_index=True)
    # Персистентная идемпотентность featured-платежа: ref последнего применённого
    # платежа (payment_intent). Тот же платёж не продлевает срок повторно даже при
    # потере Redis-дедупа по event.id (аудит 2026-07-01).
    featured_payment_ref = models.CharField(max_length=255, blank=True, default="")
    # D2.3: owner-аналитика продвижения — считаем ТОЛЬКО пока позиция featured
    # (показы: рендер блока split_featured; клики: редирект-счётчик). Кумулятивно
    # по всем оплаченным окнам — владелец видит суммарный эффект.
    featured_impressions = models.PositiveIntegerField(default=0)
    featured_clicks = models.PositiveIntegerField(default=0)
    # T-8.20: поисковый индекс (apps/aggregator/search_index.py) — вектор с весами A–D
    # и свёрнутый текст для поиска опечаток. Пишутся только индексатором (save()).
    search_vector = SearchVectorField(null=True, editable=False)
    search_text = models.TextField(default="", blank=True, editable=False)
    is_active = models.BooleanField(default=True)
    # T-8.6: скрыто модерацией (вручную или авто — три жалобы). Синк поле НЕ трогает
    # (как featured_until), поэтому скрытие переживает правки акции владельцем.
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_reason = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ListingQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_schema", "listing_kind", "source_ref"],
                name="agg_listing_src_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["city", "is_active"], name="agg_city_active_idx"),
            models.Index(fields=["business_type", "city"], name="agg_btype_city_idx"),
            models.Index(fields=["listing_kind", "is_active"], name="agg_kind_active_idx"),
            models.Index(fields=["category", "is_active"], name="agg_category_active_idx"),
            GinIndex(fields=["search_vector"], name="agg_search_vector_gin"),
            # T-8.20: «часть слова» (LIKE) и опечатки (%>) — по trigram-индексу.
            GinIndex(
                fields=["search_text"], name="agg_search_text_trgm", opclasses=["gin_trgm_ops"]
            ),
        ]

    def __str__(self):
        return f"{self.business_name}: {(self.title or {}).get('de') or self.promo_uuid}"

    def save(self, *args, **kwargs):
        # Инвариант: source_ref — единый ключ источника. У акций он равен
        # str(promo_uuid); выводим автоматически, если задан только legacy-uuid.
        if not self.source_ref and self.promo_uuid:
            self.source_ref = str(self.promo_uuid)
        # T-8.20: индекс поиска — после каждой записи индексируемых полей, в той же
        # транзакции (сбой не оставит листинг без вектора). Массовые .update() этих полей
        # обязаны звать search_index.refresh (refresh_tenant_fields).
        from django.db import router, transaction

        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        fields = kwargs.get("update_fields")
        with transaction.atomic(using=using):
            super().save(*args, **kwargs)
            if fields is None or set(fields) & search_index.INDEXED_FIELDS:
                search_index.refresh_listing(self, using=using)

    @property
    def title_text(self) -> str:
        return self.get_i18n("title")

    @property
    def teaser_text(self) -> str:
        return self.get_i18n("teaser")

    @property
    def district_name(self) -> str:
        """T-8.17: подпись района для карточки (slug → «Gräfrath»)."""
        if not self.district:
            return ""
        from apps.core import districts

        return districts.label(self.city, self.district)

    def with_channel(self, ch: str) -> str:
        """T-8.8: ссылка на сайт бизнеса с атрибуцией канала `?ch=<ch>`.

        Витрина кладёт канал в сессию (`_capture_channel`), он доезжает до резерва,
        купона и счётчика просмотров по каналам. Уже заданный канал не дублируем.
        Для JSON-LD/SEO — чистый detail_url."""
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        url = self.detail_url or ""
        if not url:
            return url
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        if any(k == "ch" for k, _v in query):
            return url
        query.append(("ch", ch))
        return urlunsplit(parts._replace(query=urlencode(query)))

    @property
    def portal_url(self) -> str:
        """T-8.6: ссылка с каталога города на бизнес с атрибуцией `?ch=portal`."""
        return self.with_channel("portal")

    @property
    def is_featured_now(self) -> bool:
        from django.utils import timezone

        return bool(self.featured_until and self.featured_until > timezone.now())


class ListingReport(models.Model):
    """T-8.6 «Melden»: жалоба посетителя на карточку каталога города.

    Постмодерация: жалобы копятся в очереди админки; три открытые жалобы с разных
    адресов скрывают карточку до решения модератора (`AUTO_HIDE_AT`).
    """

    AUTO_HIDE_AT = 3

    REASON_WRONG = "wrong"
    REASON_EXPIRED = "expired"
    REASON_OFFENSIVE = "offensive"
    REASON_SPAM = "spam"
    REASON_OTHER = "other"
    REASONS = [
        (REASON_WRONG, _("Falsche Angaben")),
        (REASON_EXPIRED, _("Angebot gibt es nicht mehr")),
        (REASON_OFFENSIVE, _("Anstößig oder rechtswidrig")),
        (REASON_SPAM, _("Spam oder Betrug")),
        (REASON_OTHER, _("Sonstiges")),
    ]
    STATUS_OPEN = "open"
    STATUS_RESOLVED = "resolved"
    STATUSES = [(STATUS_OPEN, _("Offen")), (STATUS_RESOLVED, _("Erledigt"))]

    listing = models.ForeignKey(AggregatorListing, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=20, choices=REASONS)
    message = models.TextField(blank=True, default="", max_length=1000)
    # Хэш IP (не сам адрес) — только чтобы считать РАЗНЫЕ голоса для автоскрытия.
    ip_hash = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"], name="agg_report_queue_idx")]

    def __str__(self):
        return f"{self.get_reason_display()} — {self.listing}"


class SearchQueryLog(models.Model):
    """T-8.21: журнал поиска каталога города — АГРЕГАТ «день × запрос × город × поверхность».

    Без персональных данных: ни IP, ни пользователя, ни сессии, ни времени внутри дня
    (план Р-2; замок `test_model_has_no_personal_fields`). Только для платформы (админка
    public, суперпользователь). Пишет `search_log.log()`, чистит beat `purge_search_log`.
    """

    SURFACE_PORTAL = "portal"
    SURFACE_ENTDECKEN = "entdecken"
    SURFACES = [(SURFACE_PORTAL, _("Stadtportal")), (SURFACE_ENTDECKEN, _("Entdecken"))]
    MODES = [
        ("none", _("Nur Filter")),
        ("fts", _("Volltext")),
        ("trigram", _("Ähnliche Schreibweise")),
        ("empty", _("Leere Anfrage")),
    ]

    day = models.DateField(verbose_name=_("Tag"))
    surface = models.CharField(max_length=12, choices=SURFACES, verbose_name=_("Oberfläche"))
    # Строка, не FK: NULL в unique-ключе ломал бы агрегацию, а история переживает портал.
    portal_host = models.CharField(max_length=253, blank=True, default="", verbose_name=_("Portal"))
    city = models.CharField(max_length=100, blank=True, default="", verbose_name=_("Stadt"))
    lang = models.CharField(max_length=8, blank=True, default="", verbose_name=_("Sprache"))
    query_norm = models.CharField(
        max_length=100, blank=True, default="", verbose_name=_("Suchbegriff")
    )
    filters_key = models.CharField(max_length=255, blank=True, default="")
    filters = models.JSONField(default=dict, blank=True, verbose_name=_("Filter"))
    searches = models.PositiveIntegerField(default=0, verbose_name=_("Suchen"))
    zero_results = models.PositiveIntegerField(default=0, verbose_name=_("Ohne Treffer"))
    # Нашлось только по похожему написанию — кандидат в словарь синонимов.
    trigram_hits = models.PositiveIntegerField(default=0, verbose_name=_("Nur Tippfehler-Treffer"))
    last_mode = models.CharField(
        max_length=10, choices=MODES, default="none", verbose_name=_("Modus")
    )
    last_results = models.PositiveIntegerField(default=0, verbose_name=_("Treffer (zuletzt)"))

    class Meta:
        verbose_name = _("Suchanfrage (Stadtkatalog)")
        verbose_name_plural = _("Suchanfragen (Stadtkatalog)")
        ordering = ["-day", "-searches"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "day",
                    "surface",
                    "portal_host",
                    "city",
                    "lang",
                    "query_norm",
                    "filters_key",
                ],
                name="agg_searchlog_uniq",
            )
        ]
        # Индекс только по дню: purge и сортировка админки; второй колонки (zero_results)
        # нет осознанно — она меняется в каждом «ничего не найдено» и ломала бы HOT-апдейты.
        indexes = [models.Index(fields=["-day"], name="agg_searchlog_day_idx")]

    def __str__(self):
        return f"{self.day} «{self.query_norm}» ×{self.searches}"


class AggregatorPortal(I18nMixin, models.Model):
    """Брендированный мульти-доменный портал над пулом AggregatorListing (P2.1).

    Привязан к своему хосту (поддомен *.siteadaptor.de или custom-домен) и сужает
    выдачу по городу и/или типу бизнеса. Резолвер (apps.aggregator.middleware)
    сопоставляет request.get_host() → портал: кладёт его в request.portal и
    подменяет request.urlconf на config.urls_portal (страницы — portal_views).
    SHARED (public-схема), как и листинги.
    """

    KIND_CITY = "city"
    KIND_VERTICAL = "vertical"
    KIND_COMBO = "combo"
    KINDS = [
        (KIND_CITY, _("City")),
        (KIND_VERTICAL, _("Vertical")),
        (KIND_COMBO, _("City + type")),
    ]

    host = models.CharField(max_length=253, unique=True)  # полный хост — ключ резолвера
    kind = models.CharField(max_length=20, choices=KINDS, default=KIND_CITY)

    # Фильтры выдачи. Любой может быть пустым (тогда портал шире по этой оси).
    city = models.CharField(max_length=100, blank=True)
    business_type = models.CharField(max_length=50, blank=True, choices=Tenant.BUSINESS_TYPES)

    # Брендинг (i18n-JSON {"de": "...", "en": "..."}).
    title = models.JSONField(default=dict)
    tagline = models.JSONField(default=dict, blank=True)
    intro = models.JSONField(default=dict, blank=True)
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=7, default="#111827")
    # T-8.15: показывать листинги демо-бизнесов (превью для партнёров до запуска).
    # Новый портал по умолчанию честный — только настоящие бизнесы.
    show_demo = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["host"]
        indexes = [
            models.Index(fields=["is_active"], name="agg_portal_active_idx"),
        ]

    def __str__(self):
        scope = self.city or (self.get_business_type_display() if self.business_type else "") or "—"
        return f"{self.host} ({scope})"

    @property
    def title_text(self) -> str:
        return self.get_i18n("title")

    @property
    def tagline_text(self) -> str:
        return self.get_i18n("tagline")

    @property
    def intro_text(self) -> str:
        return self.get_i18n("intro")


class PortalBot(models.Model):
    """Telegram-бот портала агрегатора (TG4, SHARED/public).

    Один бот на портал; webhook на хосте портала /tg/<secret>/. На /start бот
    открывает выдачу портала как Telegram Mini App. Токен из @BotFather задаётся
    в unfold-админке (порталы — admin/команда-managed, кабинета у них нет).
    """

    portal = models.OneToOneField(
        AggregatorPortal, on_delete=models.CASCADE, related_name="telegram_bot"
    )
    token = models.CharField(max_length=100, blank=True)
    bot_username = models.CharField(max_length=64, blank=True)
    webhook_secret = models.CharField(max_length=48, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.portal.host}: {self.bot_username or 'bot'}"

    def save(self, *args, **kwargs):
        if not self.webhook_secret:
            import secrets

            self.webhook_secret = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)


class PortalUser(models.Model):
    """Клиентская идентичность на порталах (P2.3, SHARED/public).

    Конечный потребитель агрегатора — НЕ django.contrib.auth.User (те — владельцы
    бизнесов в tenant-схемах). Входит по magic-link (apps.aggregator.auth):
    пароля нет, переход по ссылке из письма = подтверждение email. Живёт в
    лёгкой сессии (request.session["portal_user_id"]). Cross-tenant: один
    аккаунт видит свои данные по всем бизнесам (брони подтянутся в P2.3c по
    email-связке с per-tenant Customer).
    """

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    # Центральная отписка от писем бизнесов (P2.3d): источник истины для
    # порталов; синхронизируется в per-tenant Customer.unsubscribed задачей
    # apply_marketing_opt_out. Транзакционные письма (бронь) идут всегда.
    marketing_opt_out = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class FavoriteListing(models.Model):
    """Избранное клиента портала (P2.3b, SHARED/public).

    CASCADE по листингу сознательно: листинг исчезает из агрегатора вместе с
    завершением акции — «сохранённое предложение» по природе временное.
    """

    user = models.ForeignKey(PortalUser, on_delete=models.CASCADE, related_name="favorites")
    listing = models.ForeignKey(
        AggregatorListing, on_delete=models.CASCADE, related_name="favorited_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "listing"], name="favorite_uniq"),
        ]

    def __str__(self):
        return f"{self.user.email} → {self.listing_id}"


class BusinessReview(models.Model):
    """Отзыв клиента портала о бизнесе (G8, SHARED/public).

    Привязан к бизнесу (tenant_schema), а не к отдельной акции — один автор
    (PortalUser) оставляет один отзыв на бизнес. Авто-публикация; супер-админ
    может скрыть (status=hidden, модерация). Агрегат — BusinessRating.
    """

    STATUS_PUBLISHED = "published"
    STATUS_HIDDEN = "hidden"
    STATUSES = [(STATUS_PUBLISHED, _("Published")), (STATUS_HIDDEN, _("Hidden"))]

    tenant_schema = models.CharField(max_length=63)
    tenant_slug = models.SlugField(max_length=100)
    business_name = models.CharField(max_length=200, blank=True)  # снимок для админки
    author = models.ForeignKey(PortalUser, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()  # 1..5 (валидируется во вьюхе)
    comment = models.TextField(blank=True)
    # I18N-12: перевод ПОКАЗА (только демо; отзывы реальных гостей не переводим).
    comment_i18n = models.JSONField(default=dict, blank=True)
    # Решение 1а (2026-08-06): публичный ответ владельца — как у entity-отзывов
    # (CM-6.2); пишется из кабинета (вкладка «Über den Betrieb»), виден на портале.
    reply_text = models.TextField(blank=True, default="")
    replied_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_PUBLISHED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["author", "tenant_schema"], name="review_author_business_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_schema", "status"], name="review_business_status_idx"),
        ]

    def __str__(self):
        return f"{self.business_name or self.tenant_slug}: {self.rating}★"

    def comment_localized(self, locale: str | None = None) -> str:
        """I18N-12: показ отзыва на локали (заполняет только демо-сидер)."""
        from apps.core.models import resolve_overlay

        return resolve_overlay(self.comment, self.comment_i18n, locale)

    @property
    def stars(self) -> str:
        return "★" * self.rating + "☆" * (5 - self.rating)


class BusinessRating(models.Model):
    """Денормализованный агрегат рейтинга бизнеса (G8) — быстрые звёзды в выдаче.

    Одна строка на tenant_schema; пересчитывается при создании/модерации отзыва
    (apps.aggregator.reviews.recompute_rating). Листинги джойнятся по схеме.
    """

    tenant_schema = models.CharField(max_length=63, unique=True)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)  # 0.00–5.00
    review_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tenant_schema}: {self.avg_rating} ({self.review_count})"
