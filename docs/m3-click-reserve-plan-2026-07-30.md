# M3 Click&Reserve «In der Anprobe zurücklegen» (2026-07-30)

Волна M3 плана `mode-boutique-plan-2026-07-30.md`. Разведка (агент, 56 tool-uses):
вариант (а) — Order + метка + TTL — покрывает ~90% (anti-oversell per-variant,
restore при cancelled с леджером/FEFO, письма-словарь, канбан через kind=order);
промо-Reservation НЕ трогает каталог-сток вовсе (обобщение = переписывание);
новая модель = 7-й kind в transactions/registry/pipeline (дорого до видимости).

## Решения
- **Order + `reserve_expires_at`** (миграция `orders/0016`, DateTimeField null;
  `is_anprobe` = поле не NULL) + `source_channel="anprobe"` (аналитика).
- **Правовой риск (главный из разведки)**: свои письма `anprobe_created` /
  `anprobe_expired` — «unverbindliche Reservierung, KEIN Kaufvertrag; Kauf und
  Bezahlung erst im Geschäft» (обычные order_created/cancelled ПОДАВЛЯЮТСЯ
  ветвлением по is_anprobe).
- **TTL 48 ч** (v1 константа сервиса; поле даёт точный дедлайн). Beat-таск
  `expire_due_anprobe` — клон паттерна `expire_due_reservations` (5 мин):
  status new/confirmed + unpaid + просрочен → OrderSM cancelled (restore стока
  уже подключён) + письмо anprobe_expired.
- **Витрина**: details-форма ПОСЛЕ `_buybox` (образец M2-Warteliste — вторая
  форма с другим action, замки buybox целы): размер (только доступные) + имя +
  email → POST `/sortiment/<pk>/anprobe/` (honeypot+RL) → заказ + сообщение
  «Bis <дата> zurückgelegt». Гейт: `site_config["anprobe"]` presence-minimal
  (кит mode включает; кабинет-тумблер — по спросу) + orders_enabled + in_stock.
- **Кабинет**: бейдж «🛍 Anprobe bis <дата>» в списке заказов + детали заказа
  (фильтр-шум решается бейджем в v1).
- Демо: кит mode `anprobe=True`. Тесты: сервис (сток снят/возвращён), beat-экспайр,
  письма (НЕ order_created), витрина (кнопка/гейты), замки buybox целы.
После кода — адверсариальное ревью-workflow (правовой текст/гонки/письма/замки).
