# SEC волна 4 «инфраструктура» — план (2026-11-02)

Решение владельца 2026-11-02: «делай по рекомендации».

| ID | Дефект | Фикс |
|---|---|---|
| SEC-C-M2 | `CSRF_TRUSTED_ORIGINS=*.siteadaptor.de` + кука `csrftoken` — страница любого поддомена (XSS у одного бизнеса) могла слать формы в кабинеты соседей; cookie tossing | wildcard только по `CSRF_TRUST_ALL_SUBDOMAINS=1`; кука `__Host-csrftoken` (нельзя поставить с соседнего поддомена) |
| SEC-C-M3 | `Tenant.is_active=False` не выключал витрину | `SuspendedTenantMiddleware`: витрина — 410 без данных бизнеса; кабинет, вход, оплата подписки, вебхуки работают |
| SEC-E-M3 | Нет CSP | `CSPReportOnlyMiddleware` — режим отчёта (`CSP_REPORT_ONLY`, `CSP_REPORT_URI`); блокирующий режим — после месяца отчётов |
| SEC-E-L1/G6 | Отписка и DOI рассылки на GET (сканеры почты отписывают/подписывают за человека) | GET — кнопка, POST — действие; отписка `csrf_exempt` (RFC 8058 one-click из почтового клиента теперь работает — раньше 403) |
| SEC-G11 | compose: `.env.prod` всем сервисам; Redis без пароля; нет лимита тела запроса | Postgres и Caddy без `env_file`; опциональный `REDIS_PASSWORD`; `request_body max_size 50MB` в Caddy |
| SEC-G12 | Бэкапов нет | `scripts/backup.sh [single]` — pg_dump + медиа, ротация 14 дней, опц. S3; cron-строка в шапке скрипта |

Не делаем без окна владельца: non-root пользователь в образе (права на существующий том
`media` принадлежат root — переход требует `chown` на сервере), фиксированные теги образов.

## Ops после деплоя
- `CSRF_COOKIE_NAME` меняется → открытые формы получат один 403 (перезагрузка страницы).
- Если какая-то форма шлёт POST с одного поддомена на другой и ломается — временно
  `CSRF_TRUST_ALL_SUBDOMAINS=1` в `.env.prod` и сообщить разработке.
- Бэкапы: `crontab -e` → строка из шапки `scripts/backup.sh`; проверить восстановление.
- Redis-пароль (опционально): `REDIS_PASSWORD=…` и `REDIS_URL=redis://:…@redis:6379/0`.
