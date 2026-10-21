# T-8.30g «Погашение только кнопкой» — план (2026-10-21)

Порядок владельца «2, 3, 1» — пункт 3. Разведка и план — агент planner; вариант B по
рекомендации. Закрывает «Известный долг» T-8.30e (`t8-30e-counter-plan-2026-10-21.md`).

## Проблема
При включённой настройке `Tenant.auto_redeem_on_scan` три GET-экрана гасили код сами:
`redeem_detail` (купон и бронь) и `voucher_redeem` (ваучер). GET вызывают не только люди:
превью ссылки в мессенджере, prefetch браузера, перезагрузка, «назад». Любой из них
погашал купон/выдавал бронь без участия владельца.

## Решение (вариант B)
- **GET никогда не меняет состояние.** Страница кода показывает одну большую кнопку в
  фокусе (`data-redeem-primary`, `autofocus`): камера телефона = скан → один тап.
- **Смысл настройки — «Sofort einlösen beim Scannen in der Kasse»:** встроенный сканер
  страницы «Einlösen» (браузер или Telegram) гасит в самом своём POST (CSRF): купон,
  бронь и ваучер (`kind=voucher`). Сессионный разовый допуск T-8.30e больше не нужен.
- **Двойной тап:** формы `data-once` (общий партиал `_submit_once.html`); на сервере —
  повторная выдача брони = info «Already handed out.», у ваучера кнопка несёт `expect`
  (счётчик, который видел владелец) → многоразовый ваучер не списывается дважды
  (`services.redeem_voucher(expect_used=…)` под `select_for_update`).
- Ручной ввод без `expect` работает как раньше.

## Файлы
`apps/promotions/views.py` (`_scan_redeems`, `_auto_fulfill`, `_redeem_voucher_scan`,
`redeem_home`/`redeem_detail`/`redeem_action`/`voucher_redeem`), `services.redeem_voucher`,
шаблоны `redeem.html`/`redeem_detail.html`/`voucher_redeem.html`/`_submit_once.html`,
подпись и подсказка настройки в `apps/tenants/forms.py` (2 msgid × 5 каталогов).

## Замки
`test_t830g_redeem_button.py` (GET ничего не меняет · POST сканера гасит только с
настройкой · ваучер из сканера ведёт на свою страницу · повторная выдача = info ·
одинаковый `expect` списывает один раз · ручной ввод без `expect` · кнопка в фокусе ·
сканеры не переходят GET-ом · подсказка настройки не обещает погашение по ссылке);
осознанно переписаны `test_auto_redeem.py` (2) и `test_t830e_counter.py` (2).
Миграций нет.
