# X5 — настройки: два ряда, без телепорта, «Mein Geschäft» по секциям

Дата: 2026-08-19. Волна X5 программы `docs/cabinet-cleanup-plan-2026-08-19.md` §6.A5.
Без миграций.

## 1. Факты разведки

- Таб-бар `settings` имеет **9 главных вкладок** + ящик Erweitert из 5 →
  на ноутбуке уезжает в горизонтальный скролл (`overflow-x-auto` в
  `_hub_tabs.html`), правые вкладки (Abo/Team) не видны без прокрутки.
- **Карточка «Google Bewertungen» УЖЕ есть** на `integrations_home` (GK-11) —
  отдельная главная вкладка настроек была третьим входом в тот же экран.
  Достаточно снять её из таб-бара (`palette_only` из X4).
- «Abläufe» — ОДНА страница с двумя входами (подпункт Verkäufe и таб настроек).
  Записи есть в обоих хабах; `ANCHOR_BY_NAV` строится по порядку `ENTRIES`, и
  settings-запись перезаписывает board-запись → заход из «Verkäufe» подсвечивает
  «Einstellungen» и рисует таб-бар настроек = телепорт.
- «Mein Geschäft» — один `fieldset` на 13 полей (контакт + адрес + 5 соцсетей),
  дальше часы и ящик «Betrieb». Save — внизу длинной формы.

## 2. Инкременты

**X5-1. Два подписанных ряда вкладок.** Поле `NavEntry.group` (""/`basis`/
`verwaltung`); `hub_tabs` отдаёт `rows` = [(подпись, вкладки)] когда у хаба есть
группы, иначе прежний плоский `tabs` (все прочие хабы рендерятся байт-в-байт).
Состав: **Basis** — Mein Geschäft · Sprachen · Zahlung & Lieferung ·
Benachrichtigungen; **Verwaltung** — Recht & Steuern · Abläufe · Integrationen ·
Abo & Rechnung · Team. `flex-wrap` вместо горизонтального скролла: Abo/Team
видны всегда.

**X5-2. Google Bewertungen → только Integrationen** (`palette_only=True`).
Экран жив, входов остаётся два (карточка + Ctrl+K) вместо трёх.

**X5-3. Abläufe без телепорта.** `?from=board` → вьюха отдаёт
`nav_anchor_override="board"` и `back_url` на Verkäufe; шаблон при этом рисует
хлебную крошку «← Verkäufe» вместо таб-бара настроек. Подсветка якоря в
`_base_dashboard.html` берёт `nav_anchor_override|default:nav`. Страница одна.

**X5-4. «Mein Geschäft» по секциям.** Чипы-якоря (Kontakt · Öffnungszeiten ·
Social · Betrieb) + sticky-панель Save; соцпрофили выделены в свою секцию.
Инвариант W0 соблюдён: все поля остаются в DOM, ничего не прячется JS-ом.
Взаимные ссылки «часы бизнеса ↔ расписание слотов записи» (`booking:resources`)
— гейт по модулю booking.

## 3. Замки

- состав рядов таб-бара настроек (Basis/Verwaltung) + «прочие хабы плоские»;
- Google Bewertungen отсутствует в табах, присутствует в палитре и на карточке;
- заход `?from=board` подсвечивает «Verkäufe» и даёт back-ссылку, без него —
  прежний вид (таб-бар настроек);
- «Mein Geschäft»: все поля формы по-прежнему в DOM (регресс-класс W0).
