# Точка входа следующей сессии (обновлён 2026-06-27)

Рабочая ветка: **`claude/archetype-platform-ux-editor-x9bzzp`**. Отвечаем по-русски.
Цикл: ветка → `ruff check` + `ruff format --check` (раздельно) → `npm run build:css`
при правке шаблонов → `uv run pytest <модули>` → push → **CI на git зелёный** →
FF-merge в `main` (`git push origin <sha>:main`) → строка в `docs/build-log.md`.
Коммиты: `Co-Authored-By: Claude <noreply@anthropic.com>` + `Claude-Session: …`.
Идентификатор модели в артефакты НЕ светим.

## Активный трек: on-canvas редактор на витрине
**SOURCE OF TRUTH — `docs/storefront-onsite-editor-plan.md`** (подзадачи SE-1…SE-5,
принципы, режимы «Обычный/Эксперт», нагрузка). Идём строго по нему.
- **SE-1a ✅** кнопка «Edit design» на витрине (владельцу) → home_builder. Тест
  `test_owner_edit_button`.
- **SE-1b ✅** инспектор блока перенесён **ВЛЕВО** (`bld-block-popup` в `site_home.html`)
  + подсветка выбранной секции на канве. Контролы (колонки/число/скрыть/переместить/
  источник) уже работают — попап переносит реальную строку формы секции.
- **Дальше:** SE-1c (довести инспектор), **SE-1f** (тумблер «Обычный/Эксперт», localStorage),
  **SE-3d** (визуальные параметры блока: скругление углов — простой вкл/выкл, эксперт —
  точное значение radius; тень/фон/отступы), затем SE-2 (редактор на каталоге/категории/
  событиях), SE-3 (микрошаблоны/шрифты/устройства), SE-4 (блоки/шаблоны), SE-5 (кэш+версии).

### Что переиспользуем (НЕ писать заново)
home_builder (`/dashboard/site/home/`, `templates/tenant/site_home.html`): форма-контролы
+ live-iframe превью (`?preview=1` из `site_preview_draft`), обёртки `data-sf-section` на
секциях витрины, клик-попап E.2 (теперь слева), инсертер «+» E.3, drag E.4, Undo/Redo E.1,
пресеты раскладки, `sitetemplates`, пары шрифтов, переключатель устройств, per-page layouts,
инлайн-правка текста (`site_inline_edit`).

## Статус merge / deploy
- `main` сейчас: `9fe1ec8` (автоподключение доменов).
- **Ждут FF-merge в `main`** (проверить CI зелёный): `7dbc786` (превью: не уводить по клику
  на ссылку) · `ee30179` (SE-1a + план) · `d79cd03` (SE-1b). Слить `git push origin d79cd03:main`.
- **Деплой (владелец, один раз):** `git pull origin main && ./scripts/deploy.sh single`
  (миграция `events/0021`) + `python manage.py seed_demo_tenants --kit pranasy --recreate`.
  **Кастомный домен добавлять/держать ПОСЛЕ последнего `--recreate`** (иначе привязка
  `Domain` удаляется). Автоподключение домена заработает после деплоя; до деплоя разовый
  обход — `ALLOWED_HOSTS=*` в `.env.prod` + `docker compose --profile single up -d web`.

## Сделано в этой сессии (хронология — build-log)
Pranasy полноценный двуязычный кит (PR-A…H: i18n site_config/Event, локальные демо-фото
SVG, подкатегории, Restaurant+Shop как отдельные сущности, 6 ретритов, кетеринг, лояльность,
«О нас»). Спринт G анти-Битрикс (AB1–AB5). Фиксы: инлайн-редактор (contenteditable +
заголовки секций + не уводить по ссылкам), загрузка фото баннера раздела, **автоподключение
кастомных доменов** (middleware из таблицы Domain + авто-verify beat).

## Перед боевым запуском (владелец)
Stripe live, инфра (отд. Postgres/бэкапы/секреты/Sentry/Resend), право DACH.
