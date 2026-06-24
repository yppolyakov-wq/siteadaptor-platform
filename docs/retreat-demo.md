# Демо-кит «Ретрит» (Waldlicht Retreat)

Полноценное демо архетипа «Ретрит» (A6 ⊕ A5). Сидер:

```bash
python manage.py seed_demo_tenants --kit retreat --recreate
# субдомен: retreat.<TENANT_DOMAIN_BASE>  (напр. retreat.siteadaptor.de / .localhost)
```

Бизнес: **Waldlicht Retreat** (Freiburg) — Yoga/Achtsamkeit-ретриты. Тип `other`,
модули: `events, booking, orders, customer_account, stays, jobs`.

## Что показывает (R1–R6)

| Фича | Где смотреть | Что в демо |
|---|---|---|
| **Каталог + фильтры** (R2) | `/veranstaltung/` | 6 событий; фильтры: направление (Yoga/Ayurveda/Klang/Achtsamkeit), город, длительность, уровень, язык, месяц, **преподаватель** |
| **Таксономия в агрегаторе** (R2b) | `/entdecken/?cat=yoga` | event-листинги с направлением; фильтр по направлению/городу/месяцу |
| **Преподаватели** (R3a) | меню «Lehrer» → `/lehrer/` | Mara Lind, Felix Sturm (фото, био, ближайшие ретриты); ссылки с карточки события |
| **Календарь + iCal** (R3b) | `/veranstaltung/kalender/` | события по месяцам (на ~полгода вперёд); «Subscribe (iCal)» + «Add to calendar» на событии |
| **Лист ожидания + анкета** (R1) | страница события | структурная анкета (страна/экстренный контакт/питание/опыт/мед.); waitlist на sold-out |
| **Ценовые тиры билета** (A6) | страница события | Frühbucher / Standard / Mehrbettzimmer |
| **Депозит / частичная оплата** (R4) | Wochenend-Retreat | онлайн-депозит 30 % (Ayurveda — 40 %), остаток на месте |
| **Подарочный/промо-код** (R4) | форма брони | поле «Gutscheincode»; покупка сертификата — `/gutschein/` (нужна онлайн-оплата) |
| **Проживание** (R5) | Wochenend/Frauen/Ayurveda | выбор типа номера (Mehrbett 35 € / Doppel 70 € / Einzel 95 €), наличие по датам, цена за срок |
| **Карта** (R6) | страница события | OSM-карта (без трекинг-куки) + «Route planen» |
| **Памятка-PDF** (R6) | после брони | «Teilnehmer-Infoblatt» (`/e/<code>/memo.pdf`): программа, что взять, проживание |
| **Корп/групповой запрос** (R6) | страница события | «Für Gruppen & Firmen» → `/anfrage/` (движок Angebote, jobs) |
| **Extras** (#7) | форма брони | Bio-Mittagessen / Einzelzimmer-Zuschlag / Yogamatte |
| **Отзывы / Trust / FAQ / Team** | главная | блоки витрины (Site Builder) |
| **Shop** (мерч) | `/sortiment/` | йога-мат, чай, благовония, журнал |
| **1:1-услуги** (booking) | `/termin/` | Einzel-Yogastunde, Coaching, Schnupperstunde |

## События (6)
1. **Waldlicht Wochenend-Retreat** (+21 дн) — флагман: тиры, депозит 30 %, проживание, гео, лендинг, анкета.
2. **Yoga & Achtsamkeit — Tagesworkshop** (+10) — дневной, Anfänger.
3. **Klangschalen-Meditation am Abend** (+7) — вечер, Klang.
4. **Sommer-Festival der Achtsamkeit** (+45) — без лимита мест, гео (Stadtpark).
5. **Frauen-Retreat: Kraft & Ruhe** (+90) — женский, проживание, депозит 30 %.
6. **Ayurveda-Detox-Wochenende** (+160) — 3 дня, Ayurveda, депозит 40 %.

## Заметки
- Онлайн-оплата (депозит/сертификат-покупка) требует подключённого Stripe Connect
  у тенанта; без него бронь остаётся pending / `/gutschein/` отдаёт 404 (как у hotel).
- Карта — OpenStreetMap embed (cookieless), в духе UX-принципа «без трекинг-куки».
- План архетипа и статус подзадач — `docs/retreat-archetype-plan.md`; хронология —
  `docs/build-log.md`.
