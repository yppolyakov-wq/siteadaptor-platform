# KA-12 E6.7d — экран выдачи прав на «Team & Zugriff» (2026-10-25)

Сервер готов с E6.7c (`perm_grants.set_member_permissions`, `invite_perms`, `team_view`
принимает `action=perms` + `perms_present=1` + `perm[]` + `perms_state`). Не хватает UI и
подписей. Шаблоны ролей / Verlauf / 403 с именем права — E6.7f, не здесь. Без миграций.

## Найденные пробелы
1. `team_view` вызывает `issue_invite` без `perms=` — выбор прав инвайта не доходит до сервера.
2. В `permissions.py` нет подписей ключей и групп.
3. `PermsDenied("scope")` в UI показывается как «Mitglied nicht gefunden» — нужен нейтральный
   текст «Rechte außerhalb Ihres Bereichs».

## Экран
- Строка участника → `<details>` «Rechte (N)» → своя форма (`action=perms`, `membership_id`,
  `perms_present=1`, `perms_state`), `<fieldset>`/`<legend>` на группу, чекбоксы `perm`.
- Недоступный ключ — `disabled` + видимая причина через `aria-describedby`:
  `role_limit` (нет в ROLE_LIMIT роли), `no_grant` (не отмечен и вне grant-scope),
  `no_revoke` (отмечен и вне revoke-scope).
- 🔒 у SENSITIVE (`aria-hidden` + sr-only «sensibles Recht»).
- Строка владельца и своя строка — только текст (`_scopes` бросает target_owner / self).
- requires: истина — сервер; JS — прогрессивное улучшение (отметил edit → отмечен view;
  снял view → сняты зависимые).
- Инвайт: `<details>` «Rechte anpassen (optional)», по умолчанию пресет роли; `perms_present=1`
  только при изменении секции, иначе `perms=None` (= пресет). Пресеты через `json_script`.

## Код
- `apps/core/perm_ui.py`: `LABELS`, `GROUP_LABELS` (gettext_lazy, канон. `_`),
  `perm_form(actor_m, target_m)`, `invite_form(actor_m)`.
- `perm_grants.scopes_for(actor, target)` — публичная обёртка `_scopes`.
- `team.py`: контекст строк, `perms=` в инвайт, текст для «scope».
- `templates/tenant/_perm_fieldsets.html` (общий), `team.html`.

## Тесты сначала (`apps/core/tests/test_team_perms_ui.py`)
Полнота подписей; владелец видит формы admin/staff, не своей и не owner; admin с team.edit —
формы только у staff, 🔒-неотмеченный disabled `no_grant`, `team.edit` у staff `role_limit`;
без team.edit — нет формы; сквозной POST: снятый отзывает, disabled-отмеченные вне scope
сохраняются; stale-токен; подделка ключа вне scope — отказ; инвайт без presence = пресет,
с набором = набор + requires.

## ECC-прогоны
- Скиллы до кода: django-patterns, django-tdd, django-security, accessibility, e2e-testing.
- `a11y-architect` — разметка партиала до стенда.
- `django-reviewer` — после локальных тестов; `security-reviewer` — до мержа (подделка формы,
  disabled-поля, раскрытие e-mail/прав, оракул в текстах отказа, perms инвайта).
- Playwright-стенд (Python, Chromium `/opt/pw-browsers`): снять право → после перезагрузки
  снято; admin не может отметить 🔒; edit отмечает view; 390/1440 px; ru; 0 JS-ошибок.

## Грабли (docs/pitfalls.md)
W0 — снятые/disabled не отправляются → сентинел `perms_present`; новые Tailwind-классы →
`npm run build:css`; многострочный `{# #}` запрещён; `i18n_quickcheck` + сверка с `i18n_gap`;
уникальные пробные строки в тестах; `ruff format --check .` целиком.
