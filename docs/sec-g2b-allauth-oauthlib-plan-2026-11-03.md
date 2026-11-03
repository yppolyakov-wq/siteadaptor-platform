# SEC-G2b — django-allauth 65.21 + oauthlib 4 (2026-11-03)

Продолжение SEC-G2a (Django 5.2 LTS, Pillow 13 — в `main` с 2026-11-02, коммит `95ebeca`).
Сверка `uv.lock` с базой уязвимостей (`uvx pip-audit`, разово, в проект не ставим) нашла
одну оставшуюся: **oauthlib 3.3.1** — CVE-2026-49272 / PYSEC-2026-4114 (тайминг-атака на
сравнение PKCE `code_verifier`, CWE-208), исправлено только в 4.0.0.

## 1. Диагноз
- У нас oauthlib — зависимость extra `socialaccount` django-allauth. Уязвима серверная
  часть OAuth2 (выдача токенов с PKCE); OAuth-сервера в проекте нет, allauth работает
  клиентом, соцпровайдеры не настроены → **практически не эксплуатируемо**.
- Поднять oauthlib отдельно нельзя: allauth 65.18 пинит `oauthlib<4`. С 65.21.1 allauth
  требует `oauthlib>=4,<5`.
- allauth 65.19.7–65.21.1 сами несут исправления безопасности: общий кэш лимитов при
  нескольких окнах (обход длинного окна — затрагивает вход/сброс пароля), состояние OAuth
  привязано к провайдеру, отменённый многошаговый вход больше не смешивает записи
  аутентификации, MFA/WebAuthn (у нас не включены).

## 2. Ломающие изменения и наш код
| Изменение 65.19–65.21 | Затрагивает нас? |
|---|---|
| Python 3.10 больше не поддерживается | нет (3.12) |
| `SocialLogin.stash_state()/unstash_state()` удалены | нет: своих провайдеров нет (grep пуст) |
| Недавний вход не заменяет повторную аутентификацию | нет: reauth-вьюх allauth не используем |
| Открытие signup отменяет незаконченный вход | ожидаемо; signup кабинета — свой (`/registrieren/`) |

Интеграция: `ACCOUNT_ADAPTER = apps.tenants.adapters.AccountAdapter` (наследник
`DefaultAccountAdapter`), `ACCOUNT_LOGIN_METHODS={"email"}`, `ACCOUNT_SIGNUP_FIELDS`,
`ACCOUNT_EMAIL_VERIFICATION`. Ни MFA, ни headless, ни socialaccount-провайдеров.

## 3. Шаги
1. `uv lock --upgrade-package django-allauth --upgrade-package oauthlib` (диапазон
   `django-allauth[socialaccount]>=65.0` в pyproject не трогаем).
2. `manage.py check` + `makemigrations --check` (allauth может принести миграции —
   они применятся `migrate_schemas` при деплое, свои миграции не пишем).
3. Локально — тесты входа/регистрации/сброса пароля/адаптера/магической ссылки.
4. Повторный `pip-audit` — ноль уязвимостей.
5. Пуш после зелёного CI предыдущего батча (иначе concurrency отменит его прогон);
   CI целиком — финальный гейт; мерж FF в `main`.

## 4. ECC-прогоны
| Когда | Что | Зачем |
|---|---|---|
| до кода | скиллы `django-security`, `django-verification`, `deployment-patterns` | чек-лист обновления auth-зависимости, проверки перед деплоем |
| после `uv lock` | `security-reviewer` | диф `uv.lock` + changelog allauth против наших настроек входа; нет ли новых дефолтов, ослабляющих защиту |
| после тестов | `django-reviewer` | миграции allauth в TENANT/SHARED-схемах, совместимость адаптера |
| перед мержем | CI на git целиком | финальный гейт |
| ops | — | деплой `./scripts/deploy.sh single` (миграции allauth, если есть, проходят штатно) |
