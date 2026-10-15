# План реализации T-8.7 «Folgen + сводка + сортировки»

> Сохранить как `docs/t8-7-folgen-plan-2026-10-15.md`. Задача — `docs/t8-roadmap-2026-10-10.md:42`. Решения владельца Р-1…Р-8 (2026-10-15) зафиксированы в запросе. Ниже: Р-П* — мои рекомендации по открытым развилкам. Ссылки `файл:строка` даны по состоянию `main` на 2026-10-15.

## 0. Кратко

Житель подписывается на **бизнес**, **раздел справочника** (15 `city_categories.SECTIONS`) или **район** города. Для подписки нужен только e-mail, подтверждение — Double-Opt-In без входа. До подтверждения в БД **не пишется ничего**: состояние живёт в подписанном токене. После подтверждения появляются `PortalUser` (если его не было) и строка `FollowSubscription`.

Раз в день в 8:00 по Europe/Berlin (или раз в неделю, в понедельник) житель получает **одно** письмо с секциями по своим подпискам. На подписку не больше 5 элементов, у каждой секции ссылка «Alle anzeigen» на область портала с `?ch=digest`. Пустых писем не бывает. Подписка на конкретный бизнес может быть «мгновенной»: beat раз в 15 минут, с тихими часами. Подписками управляют по ссылке из письма или в `/konto/`. Отписка от одной подписки и от всех — в один клик, плюс заголовки `List-Unsubscribe` по RFC 8058.

Отдельно: сортировки «Neu / Endet bald / Jetzt geöffnet / Nähe» и фильтр «im Umkreis N km» в `search.py`, на портале и на `/entdecken/`.

Миграция `aggregator/0026` (SHARED, аддитивная). Канал Telegram — только шов (`channel`).

---

## 1. Текущее состояние (разведка)

| Что | Где | Вывод для T-8.7 |
|---|---|---|
| Видимость листинга | `apps/aggregator/models.py:38-58` `ListingQuerySet.public()` (активен, не скрыт, не истёк, `withheld_schemas`) | Сводка читает **только** через `listings_for(...)` (`views.py:57-137`): `public()` + демо-фильтр + прошедшие события вон. Это одна точка истины |
| Виды предложений | `models.py:83` `OFFER_KINDS = (promotion, stay, event, menu)` | Р-2: для раздела и района — ровно они |
| `created_at` листинга | `models.py:166` (`auto_now_add`) | Ловушка: при паузе/реактивации акции или после возврата бизнеса в каталог (`visibility.apply_visibility` → `reconcile_schema`, `tasks.py:590-681`) синк **удаляет и заново создаёт** строку → новый `created_at`. Нужна защита от повторной отправки (Р-П5) |
| PortalUser | `models.py:455-480`: `email` unique, `is_active`, `marketing_opt_out` | Полей `locale` и токена управления нет — добавляем |
| Magic-link | `auth.py:31-58`: токен в Redis, rate-limit на e-mail, `login()` делает `get_or_create` | Образец rate-limit на e-mail и неявного создания пользователя |
| Отправка писем с public | `tasks.py:460-483` `send_magic_link_email` — прямой `send_mail`, без `notify` | `apps.notifications.Notification` — TENANT-модель, `notify()` в public-схеме **не годится**. `email_locale()` (`notifications/services.py:15-35`) берёт язык ТЕНАНТА по `connection.schema_name` — для жителя портала неверно → свой `PortalUser.locale` |
| DOI у тенанта | `promotions/newsletter.py:18-31` (`signing.dumps`, salt, `max_age` 14 дней), `:83-104` (письмо в `translation.override`), `:185-188` (заголовки `List-Unsubscribe`) | Переиспользуем паттерн |
| Honeypot + метка времени | `apps/tenants/quickstart.py:111-121` `form_stamp()` / `too_fast()` | Переиспользуем как есть |
| Кэш публичных страниц | `apps/core/pagecache.py:193-222`: анониму без query отдаётся из кэша, страница с `{% csrf_token %}` в кэш **не попадает** (P0-1) | **Кнопка «Folgen» на кэшируемых страницах — ссылка (GET), не форма.** Иначе главная, страницы района и раздела перестанут кэшироваться. Форма с CSRF живёт на отдельной странице `/folgen/` — как «Melden» (`reports.py:47-74`) |
| Лента портала | `portal_views.py:121-375`: `parse_filters` `:176`, `broad = execute(...)` `:198-209`, ветка «рядом» `:248-261`, `page_carry` `:353-360`, `search_hidden` `:338-346` | Сюда — сорт и радиус |
| Фильтр-панель | `portal_views.py:378-435` + `templates/aggregator/_portal_filters.html:28-35` (селект сортировки «Relevanz/Neueste», чекбокс `offen`) | Расширяем селект, пилюля «≤ N km» |
| Поиск | `search.py:157-180` `SearchFilters` (`sort: "" \| "neu"`), `:183` `FILTER_PARAMS`, `:186-214` `parse_filters`, `:246-275` `apply_filters`, `:278-296` `carry`, `:312-358` `execute` (без q — `ranked=False` и keyset по `created_at`; с q — порядок `:354`) | Сорт ложится сюда |
| Порядок «срочное первым» | `portal_home_blocks.py:266-273` `_order("urgent")` | Это и есть «Endet bald» → вынести в `search.py` как общую точку истины |
| FEED_PARAMS | `portal_home_blocks.py:31-50` (уже есть `lat`, `lng`, `sort`) | Добавить `umkreis` |
| Гео | `geo.py:21-30` `parse_latlng`, `:33-42` `nearest` (в памяти, limit 50, без радиуса) | Добавить радиус |
| «Jetzt geöffnet» | `views.py:179-198` `_open_now_schemas(schemas)` | Сорт «открытые первыми» строится на нём |
| Журнал поиска | `search_log.py:69-97` `filters_key()` собирает ключ через `search.carry()` | **lat/lng в `carry()` класть нельзя** — точные координаты в журнале = персональные данные (Р-2 T-8.21). Радиус (`umkreis=5`) — можно |
| Страница бизнеса | `reviews_views.py:36-82`, не кэшируется; шаблон `portal_business.html:21` (h1) | Кнопка и состояние «Sie folgen» |
| /entdecken/ | `views.py:335-512` `discover_index` (execute `:408`, пагинация `:448-459`, `base_qs` `:461-478`) | Сорт приходит из `search.py` бесплатно; нужен UI в `search.html` / `_search_form.html` |
| **Находка (пред-существующий дефект)** | `config/urls_public.py:84-89` catch-all `entdecken/<city>/<business_type>/` стоит **выше** `:92-96` `entdecken/unternehmen/<slug>/` → `/entdecken/unternehmen/x/` резолвится в `city_listing(city="unternehmen")`. Тест `test_reviews.py:212-231` зовёт вьюху напрямую и дефект не видит | Чиним в этом батче (кнопка Folgen живёт на этой странице) + замок через `resolve()` |
| Beat | `config/settings/base.py:358-…` `CELERY_BEAT_SCHEDULE`, интервалы-float; прецедент «час + гейт локального часа» — `owner-digests` `:377-380`; `purge-search-log` `:483-486`; `CELERY_TIMEZONE = TIME_ZONE = Europe/Berlin` (`:285`, `:354`) | Добавить 3 записи |
| Robots | `portal_views.py:584` `PORTAL_DISALLOW`, `views.py:680` `PLATFORM_DISALLOW` | + `/folgen/` |
| Админка | `admin.py` (PortalUser не зарегистрирован) | Регистрируем PortalUser и FollowSubscription (удаление по запросу DSGVO) |
| Канал атрибуции | `promotions/public_views.py:144-149` `_capture_channel` принимает любой `?ch=` | `with_channel("digest")` (`models.py:228-244`) работает без правок |

---

## 2. Решения

### Р-П1. Модель называется `FollowSubscription`, не `Subscription`
В проекте «подписка» уже означает биллинг (`Tenant.subscription_status`, `apps/billing`). `FollowSubscription` / related_name `follows` снимают путаницу в коде и в админке.

### Р-П2. DOI: только токен, без pending-записи ✅
| | Pending-строка в БД | Подписанный токен (рекомендую) |
|---|---|---|
| Неподтверждённые e-mail в БД | да → нужна retention-задача | **нет** — минимизация DSGVO по построению |
| Боты/спам | плодят строки | ничего не пишут |
| Дедуп повторных запросов | unique-индекс | rate-limit на e-mail (как `auth.issue_magic_link`) |
| Состояние «ожидает подтверждения» в UI | можно показать | нет (и не нужно: ответ всегда «проверьте почту» — анти-энумерация) |

Токен: `signing.dumps({"e": email, "k": kind, "t": key, "c": city, "f": freq, "p": portal_id, "l": locale}, salt="portal-follow-doi", compress=True)`, `max_age = 7 дней`.

Подтверждение **идемпотентно** (`update_or_create`). Повторный клик по ссылке после отписки в течение 7 дней подпишет заново — это осознанное действие владельца ящика, риск принят.

**Защита от сканеров ссылок** (Outlook Safe Links и др. делают GET): ссылка из письма ведёт на страницу с кнопкой «Bestätigen» (POST + CSRF). GET ничего не меняет.

**Вошедший житель** (почта уже подтверждена magic-link'ом) подписывается сразу, без DOI.

### Р-П3. Токены управления
- `FollowSubscription.token` — `secrets.token_urlsafe(32)`, unique. Отписка от **одной** подписки (ссылка у каждой секции письма).
- `PortalUser.follow_token` — то же, nullable unique, создаётся при первой подписке. Даёт страницу управления всеми подписками и «от всего» (`List-Unsubscribe`). Подписанный токен без срока отозвать нельзя, поэтому храним случайный.
- Страницы с токеном в пути: `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, robots Disallow.

### Р-П4. Отписка «в один клик» (Р-8)
- Заголовки письма: `List-Unsubscribe: <https://…/folgen/abmelden/<follow_token>/?alle=1>` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. Приёмник POST — `@csrf_exempt`; токен в пути и есть авторизация. Это нативная кнопка Gmail/Apple Mail, один клик.
- Ссылка в подвале письма (GET): страница с **одной** кнопкой «Abmelden» (POST). Прямая отписка по GET отключала бы подписки сканерами ссылок. Если владелец хочет «GET = сразу отписка», это одна строка в вьюхе (Р-П4b, вынести на решение).

### Р-П5. Что считается «новым» (защита от повторов) ✅
`since = max(last_sent_at, confirmed_at, now − NEW_DAYS)`; кандидаты — `created_at > since`.
- Нижняя граница `now − 14 дней` (`NEW_DAYS`, `portal_home_blocks.py:26`) нужна, чтобы гарантировать «Alle anzeigen ⊇ элементы письма»: ссылка ведёт на `?neu=1`, а там окно ровно 14 дней.
- **Повторная отправка** того же источника, когда синк пересоздал строку (пауза → реактивация, возврат в каталог): исключаем ключи `"{tenant_schema}|{listing_kind}|{source_ref}"`, отправленные этому жителю за последние 30 дней. Они лежат в `FollowDigest.item_keys` — 1 запрос на жителя, сравнение в Python. Отдельная таблица «увиденного» не нужна.
- Наплыв (бизнес вернулся в каталог с 200 товарами): кап 5 элементов + «Alle anzeigen (N)». Остаточный риск записан в §8.

### Р-П6. Мгновенный режим: beat раз в 15 минут, не on-commit хук ✅
Хук в `sync_*` пришлось бы вставить в 7 синк-функций. Он срабатывал бы и на реконсиляции (`reconcile_schema` пересоздаёт всё) и связал бы синк с почтой. Beat-сканер проще и надёжнее:
- одна выборка «новые листинги бизнесов с instant-подписчиками с `last_sent_at`»;
- несколько новинок одного бизнеса уходят **одним** письмом;
- те же гейты (`listings_for`: демо, withheld, истёкшее).

Задержка ≤ 15 минут — «мгновенно» для жителя. Тихие часы 21:00–07:00 (локально): письмо копится до 07:00.

### Р-П7. Расписание: «час + гейт», не crontab ✅
Прецедент — `owner-digests` (`base.py:377-380`). Задача `send_follow_digests` бежит раз в час. Житель «должен» получить письмо, если локальное время ≥ 08:00 и письма за ключ периода `d:YYYY-MM-DD` ещё не было. Если beat в 8:00 лежал, письмо уйдёт в 9:00, а не потеряется (crontab `hour=8` потерял бы его).

Еженедельная подписка «созрела», если сейчас ≥ понедельник 08:00 текущей ISO-недели и `last_sent_at` раньше этого момента. У жителя максимум **одно** письмо в день: daily-подписки + созревшие weekly. Instant-подписки в дневную сводку не входят.

### Р-П8. Персистентный дедуп письма
`FollowDigest(user, period_key)` unique. Строка вставляется **до** отправки: `IntegrityError` → письмо уже ушло или уходит, выходим. При ошибке SMTP строка удаляется, следующий часовой прогон повторит. Redis-лок `idempotent_task` — только оптимизация, как и везде в проекте (`core/jobs.py:1-9`).

### Р-П9. Где показываем «Folgen»
| Поверхность | Цель | Как |
|---|---|---|
| `/unternehmen/<slug>/` (портал и `/entdecken/`) | business | кнопка у h1. Скрыта у демо-бизнеса (`Tenant.is_demo`): ему никогда ничего не придёт |
| Лента портала с `?kat=<раздел или категория>` | section (у категории — её раздел) | кнопка у заголовка |
| `/stadtteil/<slug>/` | district | кнопка у заголовка |
| Плитки разделов на главной | — | **не добавляем** (шум на главной; плитка ведёт на страницу раздела, там есть кнопка). Альтернатива «🔔 на плитке» — на решение владельца (Р-П9b) |
| `/entdecken/` (кроме страницы бизнеса) | — | v1 нет: раздел и район там не привязаны к городу из реестра |

Состояние «✓ Sie folgen» видит только вошедший (у него непустая сессия → страница идёт мимо кэша, `pagecache.py:199-201`). Аноним всегда видит ссылку «🔔 Folgen».

### Р-П10. Сортировки и радиус (Р-5, Р-6)
- `sort ∈ {"", "neu", "endet", "offen", "naehe"}`. `""` с `q` — релевантность, без `q` — новые (как сейчас).
- `endet` = порядок `urgent` (`ends_at ASC NULLS LAST, discount DESC, -created_at, -pk`), вынесен из `portal_home_blocks._order` в `search.ORDERINGS`. Блоки главной импортируют оттуда — одна точка истины.
- `offen` — сорт «открытые сейчас первыми» (`Case(When(tenant_schema__in=open_set, then 0))`). Фильтр `?offen=1` (только открытые) остаётся отдельно.
- `naehe` действует только при `lat/lng`; без точки сорт сбрасывается в `""`. Обратная совместимость: `lat/lng` без явного `sort` = «Nähe» (так работает кнопка «📍 Near me», `_map.html:17-24`).
- Пагинация: `endet` и `offen` без `q` идут через offset-курсор (`paginate_ranked`, кап 240). На nullable `ends_at` keyset ломается. `neu` — прежний keyset, `naehe` — прежний `geo.nearest` без пагинации (limit 50).
- Радиус `?umkreis=` ∈ {1, 2, 5, 10, 25} км, только при `lat/lng`. Предфильтр bounding-box в SQL, точная проверка haversine в Python → `qs.filter(pk__in=…)`. Пагинация и сортировки не ломаются. Бизнес без координат в радиус не попадает (честно).
- **lat/lng не входят в `SearchFilters` / `carry()`**, иначе попали бы в журнал T-8.21. Переносятся отдельным `geo.carry(point)`, округлённые до 3 знаков (~100 м). Замок в тестах.
- UWG §5a: featured, как и сейчас, отделены (`split_featured`) с пометкой «Anzeige». Ни одна сортировка их органически не поднимает.

---

## 3. Модели и миграция `aggregator/0026_t8_7_follow` (SHARED, аддитивная)

`apps/aggregator/models.py`:

```python
class PortalUser(...):                       # models.py:455 — добавить после :471
    locale = models.CharField(max_length=10, blank=True, default="")      # язык писем портала
    follow_token = models.CharField(max_length=64, unique=True, null=True, blank=True)

class FollowSubscription(models.Model):      # после FavoriteListing (models.py:483-503)
    TARGET_BUSINESS, TARGET_SECTION, TARGET_DISTRICT = "business", "section", "district"
    FREQ_DAILY, FREQ_WEEKLY, FREQ_INSTANT = "daily", "weekly", "instant"
    CHANNEL_EMAIL, CHANNEL_TELEGRAM = "email", "telegram"   # Р-7: шов, telegram не реализуем
    user = FK(PortalUser, CASCADE, related_name="follows")
    target_kind = CharField(20, choices=…)
    target_key = CharField(100)        # schema_name | section key | district slug
    city = CharField(100, blank=True)  # область раздела/района (districts.city_label); у business пусто
    portal = FK(AggregatorPortal, SET_NULL, null=True, blank=True)  # для ссылок/бренда письма
    frequency = CharField(10, choices=…, default=FREQ_DAILY)
    channel = CharField(10, choices=…, default=CHANNEL_EMAIL)
    token = CharField(64, unique=True)
    confirmed_at = DateTimeField()     # доказательство согласия (UWG §7 / Art. 7 DSGVO)
    source_host = CharField(253, blank=True)   # где подписался (доказательство)
    last_sent_at = DateTimeField(null=True, blank=True)
    created_at / updated_at
    class Meta:
        constraints = [UniqueConstraint(fields=["user","target_kind","target_key","city","channel"],
                                        name="follow_uniq"),
                       CheckConstraint(~Q(frequency="instant") | Q(target_kind="business"),
                                       name="follow_instant_business_only")]
        indexes = [Index(fields=["frequency","channel"], name="follow_freq_idx"),
                   Index(fields=["target_kind","target_key"], name="follow_target_idx")]

class FollowDigest(models.Model):
    user = FK(PortalUser, CASCADE, related_name="follow_digests")
    period_key = CharField(40)         # "d:2026-10-16" | "i:2026-10-16T08:15"
    item_keys = JSONField(default=list)   # ["schema|kind|ref", …] ≤ 200 — дедуп Р-П5 + аудит
    sent_at = DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [UniqueConstraint(fields=["user","period_key"], name="follow_digest_uniq")]
        indexes = [Index(fields=["sent_at"], name="follow_digest_sent_idx")]
```

Плюс `AggregatorListing.Meta.indexes` (`models.py:179-189`): `Index(fields=["tenant_schema","created_at"], name="agg_schema_created_idx")` — выборка для business-подписок. Аддитивно.

`apps/aggregator/admin.py`: регистрация `PortalUser` (поиск по e-mail, read-only поля, удаление = каскад подписок и сводок; DSGVO «удалить по запросу») и `FollowSubscription` (list_filter kind/frequency, только superuser).

---

## 4. Модули и сигнатуры

### 4.1 `apps/aggregator/follow.py` (новый, домен)
```python
DOI_SALT = "portal-follow-doi"; DOI_TTL = 7 * 86400
EMAIL_RL = (3, 3600); EMAIL_RL_DAY = (10, 86400); IP_RL = (10, 600)
NEW_DAYS = portal_home_blocks.NEW_DAYS

@dataclass(frozen=True)
class Target:
    kind: str; key: str; city: str = ""
    @property
    def label(self) -> str: ...            # имя бизнеса / cc.section(key).label / districts.label
    @property
    def allows_instant(self) -> bool: ...  # только business

def parse_target(params, *, portal) -> Target | None
    # ?unternehmen=<slug> → schema_name (Tenant активен, не демо, visibility.listable)
    # ?bereich=<section|category> → section key (категория → её раздел); нужен portal.city
    # ?stadtteil=<slug> → districts.normalize(portal.city, slug)
def target_from_follow(sub) -> Target
def make_doi_token(*, email, target, frequency, portal, locale) -> str
def load_doi_token(token) -> dict | None
def confirm(payload, *, source_host) -> FollowSubscription      # atomic, идемпотентно
def follow_now(user, target, *, frequency, portal, source_host) -> FollowSubscription  # вошедший
def is_following(user, target) -> bool
def user_follows(user) -> list[FollowSubscription]               # с select_related("portal")
def set_frequency(sub, frequency) -> bool                        # instant только business
def unsubscribe(sub) -> None
def unsubscribe_all(user) -> int                                  # + forget_if_empty
def forget_if_empty(user) -> bool   # удалить PortalUser, если неявный: нет last_login_at, избранного, отзывов
def ensure_follow_token(user) -> str
def items_for(sub, *, since, now=None) -> QuerySet                # ЕДИНСТВЕННАЯ выборка письма
    # business: listings_for(include_demo=False).filter(tenant_schema=key)
    # section:  listings_for(city=city, kinds=OFFER_KINDS, city_category=key, include_demo=False)
    # district: listings_for(city=city, district=key, kinds=OFFER_KINDS, include_demo=False)
    # .filter(created_at__gt=since).order_by("-created_at", "-pk")
def since_for(sub, now) -> datetime          # max(last_sent_at, confirmed_at, now - NEW_DAYS)
def scope_url(sub, *, ch="digest") -> str    # «Alle anzeigen»: абсолютный, reverse(urlconf=…)
    # business → portal-business ; section → portal-home ?kat=<key>&neu=1&ch=digest ;
    # district → portal-district ?neu=1&ch=digest ; без портала → urls_public (/entdecken/…)
def base_url(sub) -> str                     # https://<portal.host> | https://TENANT_DOMAIN_BASE
```
Урок T-8.5: ссылки из Celery строятся `reverse(..., urlconf="config.urls_portal" | "config.urls_public")` явно, схема `http` при DEBUG (как `tasks._scheme`, `tasks.py:18-19`).

### 4.2 `apps/aggregator/follow_digest.py` (новый, письма)
```python
ITEMS_PER_FOLLOW = 5; MAX_FOLLOWS_PER_MAIL = 20; RECENT_SENT_DAYS = 30
DAILY_HOUR = 8; QUIET_HOURS = (21, 7)

@dataclass
class Section: sub; title: str; items: list; total: int; more_url: str; unsubscribe_url: str
@dataclass
class Digest: user; sections: list[Section]; manage_url: str; unsubscribe_all_url: str
    @property
    def item_keys(self) -> list[str]: ...

def period_key_daily(now) -> str                       # "d:YYYY-MM-DD" (локальная дата)
def period_key_instant(now) -> str                     # "i:YYYY-MM-DDTHH:MM" (слот 15 мин)
def daily_due(now) -> bool                             # localtime ≥ 08:00
def weekly_due(sub, now) -> bool                       # ≥ пн 08:00 текущей ISO-недели и last_sent_at раньше
def in_quiet_hours(now) -> bool
def recently_sent_keys(user, now) -> set[str]          # FollowDigest.item_keys за 30 дней, 1 запрос
def build_digest(user, subs, *, now) -> Digest | None  # пусто → None
def render(digest, *, locale) -> tuple[str, str, str]  # subject, text, html — translation.override
def send(digest, *, period_key, now) -> bool           # Р-П8: insert FollowDigest → send → last_sent_at
def run_daily(now=None) -> int                         # кандидаты → fan-out per user
def run_instant(now=None) -> int
def purge(now=None) -> int                             # FollowDigest старше 90 дней
```
Кандидаты дневного прогона: пользователи `is_active`, у которых есть `follows(channel=email, frequency∈{daily, weekly})` и нет `FollowDigest(period_key=today)`. Это один запрос, дальше fan-out.

Письмо: `EmailMultiAlternatives(subject, text, DEFAULT_FROM_EMAIL, [email], headers={List-Unsubscribe…})` + `attach_alternative(html)`. Отправитель — платформа (Р-8).

Шаблоны: `templates/emails/follow_confirm.txt` + `_subject.txt`, `follow_digest.txt` + `_subject.txt` + `follow_digest.html` (по конвенции `templates/emails/*`). Элементы ведут на `listing.with_channel("digest")` (`models.py:228`), featured в письме не отмечаем и не продвигаем (органический порядок по новизне).

### 4.3 `apps/aggregator/tasks.py` (добавить в конец, после `:1213`)
```python
@idempotent_task()
def send_follow_digests(): return {"queued": follow_digest.run_daily()}
@idempotent_task()
def send_follow_digest_user(*, user_id, period_key): ...   # dedupe_key=f"follow:{user_id}:{period_key}"
@idempotent_task()
def send_follow_instant(): return {"queued": follow_digest.run_instant()}
@idempotent_task()
def send_follow_confirm_email(*, email, url, locale): ...  # dedupe_key=f"follow-doi:{sha256(token)}"
@idempotent_task()
def purge_follow_digests(): return follow_digest.purge()
```

### 4.4 `config/settings/base.py` — `CELERY_BEAT_SCHEDULE` (после `:486`)
```python
"send-follow-digests":  {"task": "apps.aggregator.tasks.send_follow_digests",  "schedule": 3600.0},  # гейт 8:00 внутри
"send-follow-instant":  {"task": "apps.aggregator.tasks.send_follow_instant",  "schedule": 900.0},
"purge-follow-digests": {"task": "apps.aggregator.tasks.purge_follow_digests", "schedule": 86400.0},
```
Настройки: `AGGREGATOR_FOLLOW = {"daily_hour": 8, "items_per_follow": 5, "quiet_hours": (21, 7), "doi_ttl_days": 7, "digest_retention_days": 90}` рядом с `AGGREGATOR_SEARCH` (`base.py:253`).

### 4.5 `apps/aggregator/follow_views.py` (новый, HTTP)
```python
class FollowForm(forms.Form): email (EmailField), frequency (ChoiceField), website (honeypot), stamp (hidden)
def follow_page(request)                    # GET: форма; POST: DOI или прямая подписка вошедшего
def follow_confirm(request, token)          # GET: страница-кнопка; POST: confirm() → «Sie folgen jetzt …»
def follow_manage(request, token)           # по PortalUser.follow_token: список, частота, удалить
def follow_unsubscribe(request, token)      # @csrf_exempt (RFC 8058); token подписки или follow_token+?alle=1
def follow_toggle(request)                  # @require_POST, вошедший: подписка/отписка с кнопки
```
- POST `follow_page` — порядок проверок как в `account_views.login_view:42-58`:
  1. honeypot / `quickstart.too_fast(stamp)` → молча «проверьте почту»;
  2. `ratelimit.hit("follow_ip", ip, 10/600)`;
  3. `ratelimit.hit("follow_email", email, 3/3600)` и `10/86400`;
  4. валидная цель → `send_follow_confirm_email.delay(...)`.
  
  Ответ **одинаковый** при любом исходе (анти-энумерация). Частота `instant` для не-business отвергается в форме.
- `next`-редиректы: только через `url_has_allowed_host_and_scheme` (в `account_views.py:115-118` проверка `startswith("//")` не ловит `/\host` — новую вьюху так не писать).
- Ответы с токеном в пути: `response["Referrer-Policy"] = "no-referrer"`, `no_store`.

### 4.6 URL
`config/urls_portal.py` — после `:45`, **до** catch-all `:70`:
```
folgen/                          follow_views.follow_page        name="aggregator-follow"
folgen/bestaetigen/<str:token>/  follow_confirm                  name="aggregator-follow-confirm"
folgen/verwalten/<str:token>/    follow_manage                   name="aggregator-follow-manage"
folgen/abmelden/<str:token>/     follow_unsubscribe              name="aggregator-follow-unsubscribe"
konto/folgen/                    follow_toggle                   name="aggregator-follow-toggle"
```
`config/urls_public.py` — те же имена с префиксом `entdecken/folgen/…`, **до** catch-all `:84` (прецедент общих имён — `aggregator-report`, `:83`). Плюс **перенос** `entdecken/unternehmen/<slug>/` (`:92-96`) выше `:84` — фикс находки §1.

Robots: `PORTAL_DISALLOW` (`portal_views.py:584`) += `"/folgen/"`; `PLATFORM_DISALLOW` (`views.py:680`) += `"/entdecken/folgen/"`.

### 4.7 Шаблоны
- Новые: `aggregator/follow.html` (форма: цель, e-mail, частота; у business — ещё «sofort»; текст согласия + ссылка на Datenschutz платформы), `follow_check_inbox.html`, `follow_confirm.html`, `follow_manage.html`, `follow_done.html`, `_follow_button.html` (ссылка `?unternehmen=|bereich=|stadtteil=`; у вошедшего с подпиской — «✓ Sie folgen» с ссылкой в `/konto/`).
- `portal_business.html:21` — include кнопки рядом с h1 (не у `business.is_demo`).
- `portal_home.html:10-14` — кнопка у заголовка при `follow_target` в контексте. В `portal_home` вычисляется: раздел из `scope.kat` (`portal_views.py:189-190`), район из `district`. Только при `home.has_home(portal)`, то есть у городского портала.
- `portal_account.html` — после блока уведомлений `:10-25`: секция «Ich folge» (список, селект частоты, ✕) + POST на `aggregator-follow-toggle` / `follow_manage`. Вьюха `account_views.account` (`:74-96`) добавляет `follows=follow.user_follows(user)`.
- `_portal_filters.html:28-33` — сорт «Relevanz (при q) / Neueste / Endet bald / Jetzt geöffnet / In der Nähe (только при точке)»; новое поле «Umkreis» (только при точке, иначе подсказка «📍 Standort nutzen»). В `:6` hidden lat/lng.
- `_map.html:20-22` — кнопка «📍 Near me» ставит ещё `sort=naehe` и снимает `cursor` (уже снимает).
- `_search_form.html` / `search.html` (`/entdecken/`) — тот же селект сортировки.

---

## 5. Сортировки и радиус — точки изменения

**`apps/aggregator/geo.py`** (добавить после `:42`):
```python
RADIUS_CHOICES = (1, 2, 5, 10, 25)
RADIUS_CANDIDATE_CAP = 2000
def parse_radius(raw) -> int | None
def bbox(lat, lng, km) -> tuple[float, float, float, float]
def within_radius(qs, lat, lng, km) -> QuerySet   # bbox в SQL → haversine → qs.filter(pk__in=…)
def carry(lat, lng) -> list[tuple[str, str]]       # округление до 3 знаков; НЕ в search.carry
```

**`apps/aggregator/search.py`**:
- `:157-180` `SearchFilters` += `radius_km: int | None = None`; `active` учитывает `radius_km`.
- Новые константы: `SORTS = ("", "neu", "endet", "offen", "naehe")`, `OFFSET_SORTS = ("endet", "offen")`, `ORDERINGS = {"neu": [...], "endet": [... urgent ...]}`.
- `:183` `FILTER_PARAMS` += `"umkreis"`.
- `:186-214` `parse_filters(request, *, city="")`: сорт по whitelist; `naehe` и `radius_km` — только если `geo.parse_latlng(request)` дал точку, иначе `""` / `None`.
- `:246` `apply_filters(qs, f, *, now=None, point=None)` — радиус при `point and f.radius_km`.
- `:278-296` `carry` += `("umkreis", …)`; **lat/lng — нет** (замок).
- `:312` `execute(..., point=None)`:
  - без `q` и с `sort ∈ OFFSET_SORTS` → `order_for(...)` и `ranked=True` (поле по смыслу «→ paginate_ranked», `:307`; комментарий поправить);
  - с `q` → сорт перекрывает ранг (обобщение `:354` с `"neu"` на любой явный сорт кроме `naehe`).
- Новая `order_for(sort, qs) -> list` (для `offen` — `_open_now_schemas` по схемам пула + `Case`).

**`portal_home_blocks.py:266-273`** — `"urgent"` → `search.ORDERINGS["endet"]`, `"newest"` → `ORDERINGS["neu"]`. `:31-50` `FEED_PARAMS` += `"umkreis"`.

**`portal_views.py`**:
- `:176` `parse_filters` (сорт/радиус).
- `:198-209` `execute(..., point=point)`.
- `:248` условие «рядом»: `point and filters.sort in ("", "naehe")`.
- `:255` `if broad.ranked` (охватывает и offset-сорта).
- `:338-346` / `:353-360` — `+ geo.carry(*point)`.
- `_filter_panel` `:397-422` — пилюля «≤ N km», `:434` `open` учитывает радиус.

**`views.py` (`/entdecken/`)**: `discover_index` `:361` (`parse_filters` с точкой), `:408` (`point`), `:449` (то же правило `ranked`), `:461-478` / `:505-509` (geo.carry). Ветка «рядом» как на портале — по желанию (v1 достаточно сортов `neu/endet/offen`). `city_listing` (`:531-639`, свой `_LISTING_SORTS` `:155-158`): v1 добавляет `endet` и `offen` через `search.order_for` + `paginate_ranked`; `name` и `neueste` остаются.

---

## 6. DSGVO, правовое, i18n
- **Данные:** e-mail, язык, цели подписок, частота, отметки времени (`confirmed_at` — доказательство согласия, `source_host`), ключи отправленных элементов (90 дней). IP не храним, rate-limit — в Redis с TTL.
- **Неподтверждённые:** в БД нет (Р-П2), retention не нужен.
- **Удаление:** «Allen nicht mehr folgen» удаляет строки; `forget_if_empty` удаляет неявно созданного PortalUser без иных данных. По запросу — админка (каскад). Строки `FollowDigest` старше 90 дней удаляет beat.
- **UWG §7:** письмо подтверждения без рекламы; сводка только подтвердившим; в каждом письме отписка + RFC 8058. `PortalUser.marketing_opt_out` (письма бизнесов) — отдельная ось, сводку **не** гасит. В `/konto/` это разведено подписями.
- **На владельце (Р-8):** строка о подписках/сводке в Datenschutzerklärung платформы (вместе со статистикой поиска T-8.21).
- **i18n:** все новые строки — `gettext`/`{% trans %}` немецкими msgid; письма — `translation.override(user.locale or "de")`, язык сохраняется при подписке из `request.LANGUAGE_CODE` (в каталоге `CABINET_LANGUAGES` de/en/tr/ru/uk; прочее → de). Не применять `email_locale()` из notifications: там язык тенанта. Новые msgid × 5 `.po`, затем гейты `scripts/i18n_quickcheck.py` и `scripts/i18n_untranslated.py`. Никаких `gettext` внутри f-строк (урок I18N-7b).

---

## 7. Тесты — `apps/aggregator/tests/test_follow.py` (+ `test_sorts_radius.py`)

Фикстуры по образцу `test_portal_accounts.py` / `test_districts_portal.py`: `TenantFactory(auto_create_schema=False)`, `AggregatorPortal(host, city="Solingen")`, листинги напрямую, `RequestFactory` с `request.portal`, `settings.ROOT_URLCONF`, `mailoutbox`, у публичных POST уникальный IP (грабля `rl:*`).

**DOI и формы**
1. `test_post_follow_writes_nothing_until_confirmed` — POST → 0 `FollowSubscription`, 0 `PortalUser`, 1 письмо.
2. `test_confirm_get_is_side_effect_free` — GET ссылки ничего не создаёт (сканеры).
3. `test_confirm_post_creates_user_and_follow` — `confirmed_at`, `token`, `follow_token`, `locale`.
4. `test_confirm_is_idempotent` — повторный POST: одна строка.
5. `test_expired_or_tampered_token_400`.
6. `test_same_response_for_any_outcome` — honeypot / too_fast / rate-limit / невалидная цель: тот же ответ (анти-энумерация).
7. `test_rate_limit_per_email_and_ip`.
8. `test_logged_in_user_follows_without_doi`.
9. `test_instant_only_for_business` — форма и CheckConstraint.
10. `test_demo_business_cannot_be_followed` + `test_withheld_business_cannot_be_followed`.
11. `test_category_maps_to_parent_section`; `test_unknown_district_404_or_rejected`.
12. `test_follow_button_is_link_not_form_on_cached_pages` — в `portal_home` / районе нет `csrfmiddlewaretoken`, кэш P0-1 цел.
13. `test_logged_in_sees_following_state`.

**Сводка**
14. `test_digest_contains_new_items_per_follow_sections` — одно письмо на жителя с несколькими подписками.
15. `test_empty_digest_not_sent` и `last_sent_at` не меняется.
16. `test_cap_per_follow_and_alle_anzeigen_total`.
17. `test_section_and_district_only_offer_kinds` (товар раздела не попадает), `test_business_all_kinds`.
18. `test_demo_and_withheld_never_in_digest` (также `email_pending`, `in_city_catalog=False`, suspended, `hidden_at`, истёкший `ends_at`, прошедшее событие).
19. `test_items_after_confirmation_only` — бэклог до подписки не шлётся.
20. `test_recreated_listing_not_resent` — удалить и пересоздать листинг тем же `source_ref` → не повторяется (Р-П5).
21. `test_since_floor_keeps_alle_anzeigen_superset` — **замок**: каждый элемент секции присутствует в выдаче по `scope_url` (рендер ленты по ссылке, прецедент «блок ⊆ ленты» T-8.19).
22. `test_daily_gate_before_8_not_sent_after_8_sent_once`; `test_daily_catch_up_after_missed_hour`.
23. `test_weekly_monday_and_catch_up_tuesday_once_per_week`.
24. `test_one_mail_per_day_for_daily_plus_weekly`.
25. `test_digest_dedupe_period_unique` — двойной запуск → одно письмо; `test_smtp_failure_rolls_back_digest_row`.
26. `test_instant_batches_per_business_and_respects_quiet_hours`; `test_instant_not_in_daily`.
27. `test_list_unsubscribe_headers_present`; `test_links_absolute_with_portal_host_and_ch_digest` (Celery-контекст, явный urlconf).
28. `test_digest_rendered_in_user_locale` (ru-подписчик, de-портал).
29. `test_inactive_portal_user_gets_nothing`.

**Управление и отписка**
30. `test_manage_page_lists_only_own_follows`; чужой токен → 404.
31. `test_one_click_post_unsubscribe_all_csrf_exempt` (RFC 8058 тело).
32. `test_unsubscribe_single_follow`.
33. `test_footer_get_shows_button_does_not_unsubscribe`.
34. `test_unsubscribe_all_forgets_implicit_user` / `test_keeps_user_with_favorites`.
35. `test_token_pages_no_referrer_no_store`.
36. `test_konto_shows_and_changes_frequency`.
37. `test_purge_digest_rows_older_than_retention`.

**Сортировки и радиус** (`test_sorts_radius.py`)
38. `test_sort_endet_orders_by_end_nulls_last` (портал и `/entdecken/`), пагинация без дублей.
39. `test_sort_offen_open_first_closed_kept`.
40. `test_sort_naehe_requires_point_else_reset`; `test_latlng_without_sort_is_naehe` (обратная совместимость).
41. `test_sort_with_query_overrides_rank`.
42. `test_radius_filters_exact_distance_and_excludes_no_coords`; `test_radius_ignored_without_point`; `test_radius_invalid_value_ignored`.
43. `test_latlng_never_in_search_log` — **замок**: `SearchQueryLog.filters_key` не содержит lat/lng, `umkreis` содержит.
44. `test_featured_still_separate_under_all_sorts` (UWG §5a).
45. `test_blocks_use_shared_orderings` — `portal_home_blocks` и `search.ORDERINGS` совпадают.

**Прочее**
46. `test_entdecken_business_route_resolves_to_business_page` — `resolve("/entdecken/unternehmen/x/")` (фикс находки).
47. `test_robots_disallow_folgen` (портал и платформа).
48. Миграционный замок: `makemigrations --check` в CI уже есть.

---

## 8. Риски и меры

| Риск | Мера |
|---|---|
| Пересоздание листинга синком → «новое» повторно | Р-П5: исключение ключей источника за 30 дней + нижняя граница окна |
| Наплыв при возврате бизнеса в каталог (сотни товаров «новые») | Кап 5 + «Alle anzeigen (N)». Остаточный риск: письмо «Neu bei X: 200». v2 — поле `source_created_at` в снимке, если всплывёт |
| Страницы перестанут кэшироваться | Кнопка — ссылка; форма на отдельной странице; тест 12 |
| Сканеры ссылок подтверждают/отписывают | GET без побочных эффектов, POST-кнопки; RFC 8058 POST для клиентов |
| Ссылки из Celery на неверный хост/urlconf (урок T-8.5) | Явный `urlconf=` в `reverse`, тест 27 |
| Утечка координат в журнал поиска | lat/lng вне `SearchFilters`/`carry`, тест 43 |
| Доставка без Resend в проде (console-фолбэк, Stage 0) | Флоу работает, письма в лог; не включать подписки для жителей до `RESEND_API_KEY`. Bounce-обработка (Resend webhook → удалить подписки) — в roadmap §Отложено |
| Портал Solingen сейчас `show_demo=True` (до запуска) | Демо в сводку не идут никогда; кнопка скрыта у демо-бизнесов; полоса «Vorschau» остаётся |
| Нагрузка дневного прогона | Fan-out по жителю, 1 запрос на подписку + 1 на дедуп. При росте — группировать по цели с `min(since)` (заметка) |
| Пред-существующий shadowing `/entdecken/unternehmen/` | Перенос маршрута + тест 46 |
| `offen`-сорт без `q` — offset-пагинация с капом 240 | Задокументировать (как ранжированный поиск) |

---

## 9. Инкременты (один батч на ветке `claude/t8-7-folgen-…`, локальный гейт на каждом шаге, один CI на верхушке)

| # | Содержание | Файлы | Зависит от |
|---|---|---|---|
| **a** | Модели + миграция `0026` + админка + `follow.py` (цели, токены, confirm/unsubscribe, `items_for`, `scope_url`) + тесты 1–5, 9–11, 19, 21 (на уровне сервиса) | `models.py`, `migrations/0026_t8_7_follow.py`, `admin.py`, `follow.py` | — |
| **b** | Вьюхи, URL (портал + `/entdecken/` + фикс маршрута бизнеса), шаблоны, кнопки на бизнесе/разделе/районе, `/konto/`, robots + тесты 6–8, 12–13, 30–36, 46–47 | `follow_views.py`, `urls_portal.py`, `urls_public.py`, `account_views.py`, `portal_views.py` (контекст `follow_target`), шаблоны | a |
| **c** | Движок сводки + задачи + beat + письма (txt/html) + тесты 14–29, 37 | `follow_digest.py`, `tasks.py`, `base.py`, `templates/emails/follow_*` | a |
| **d** | Мгновенный режим + тихие часы (вынесен отдельно ради ревью) + тест 26 | `follow_digest.py`, `tasks.py`, `base.py` | c |
| **e** | Сортировки и радиус (независим от a–d, можно параллельно в worktree) + тесты 38–45 | `search.py`, `geo.py`, `portal_home_blocks.py`, `portal_views.py`, `views.py`, `_portal_filters.html`, `_search_form.html`, `_map.html` | — |
| **f** | i18n (msgid × 5 `.po`), `npm run build:css` при новых классах, `ruff format --check .` целиком, `test_template_comments`, `i18n_quickcheck`. Стенд Playwright: Folgen → письмо в console → подтверждение → `/konto/` → сводка через `run_daily(now=08:05)` → отписка RFC 8058; сорт/радиус в браузере. Доки: `build-log`, `task-catalog`, CLAUDE.md §3 + очередь миграций | `locale/*`, `docs/*` | a–e |

Перед мержем — ревью ветки агентами `django-reviewer` + `security-reviewer` (DOI, токены, csrf_exempt, rate-limit, redirect) + `database-reviewer` (миграция, индексы), как в T-8.19/20/21.

## 10. Ops
- Деплой: `./scripts/deploy.sh single` (миграция `aggregator/0026` SHARED, аддитивная). Проверка: `python manage.py migration_state`.
- Beat: `DatabaseScheduler` подхватит три новые записи из `CELERY_BEAT_SCHEDULE` при старте beat — перезапуск beat входит в deploy.
- До реальной рассылки нужен `RESEND_API_KEY` (Stage 0). Без него письма уходят в console-бэкенд.
- Владельцу: строка о подписках в Datenschutzerklärung платформы (Р-8).

## 11. Открыто владельцу (не блокирует старт a)
- **Р-П4b:** ссылка «Abmelden» в подвале — страница с кнопкой (рекомендую) или отписка сразу по GET.
- **Р-П9b:** «🔔» на плитках разделов главной — да/нет (рекомендую нет).
- Тихие часы instant 21–07 — подтвердить.
- `/entdecken/`: Folgen на разделе/районе — v2 (нужна привязка города из реестра).

## Ключевые файлы
- apps/aggregator/models.py
- apps/aggregator/search.py
- apps/aggregator/geo.py
- apps/aggregator/portal_views.py
- apps/aggregator/views.py
- apps/aggregator/portal_home_blocks.py
- apps/aggregator/account_views.py
- apps/aggregator/reviews_views.py
- apps/aggregator/tasks.py
- apps/aggregator/search_log.py
- apps/aggregator/visibility.py
- apps/aggregator/admin.py
- apps/core/pagecache.py
- apps/promotions/newsletter.py
- apps/tenants/quickstart.py
- config/urls_portal.py
- config/urls_public.py
- config/settings/base.py
- templates/aggregator/portal_home.html
- templates/aggregator/portal_business.html
- templates/aggregator/portal_account.html
- templates/aggregator/_portal_filters.html
- templates/aggregator/_map.html

Отдельная находка вне задачи, которую стоит подтвердить: в `config/urls_public.py:84-96` маршрут `entdecken/unternehmen/<slug>/` перекрыт catch-all `entdecken/<city>/<business_type>/`. Страница бизнеса на основном домене, судя по порядку маршрутов, сейчас недостижима. Тест `test_reviews.py:212-231` этого не видит, потому что вызывает вьюху напрямую.

---

## 9. Решения по открытым развилкам (2026-10-15, владелец: «всё по рекомендациям»)

- Р-П4b — отписка из подвала письма ведёт на страницу с кнопкой (GET показывает, POST отписывает); one-click RFC 8058 работает отдельно заголовками.
- Р-П9b — колокольчик на плитках разделов НЕ ставим; кнопка «Folgen» — на странице раздела (`?kat=`) и района (`/stadtteil/<slug>/`).
- Тихие часы мгновенных писем 21:00–07:00 Europe/Berlin — приняты.
