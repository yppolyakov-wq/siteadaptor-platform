# FD-3 «Полный редактор дерева Finder» — план (2026-07-20)

ТЗ D4. Разведка (Explore, 2026-07-20): схема `site_config["finder"]` УЖЕ полная
({"enabled", "questions":[{key,label,chips:[{key,label,match}]}]}, match =
words/collection/category/price_min/price_max; капы 6×8×10 в normalize), движок
`finder.tree_for` уже читает кастом и скорит его. FD-3 = ЧИСТЫЙ UI поверх
существующего normalize. Без миграций, golden не трогается (finder
presence-minimal, замок test_normalize_finder_presence_minimal).

## §1 Редактор на /dashboard/finder/ (замена превью-блока)

- Форма «Eigene Fragen» (паттерн W5-строк + LS-3 getlist): до 6 вопрос-строк —
  `q_pos`/`q_label` (key автогенерится slugify(label) с суффиксом при
  коллизии); на вопрос до 8 чип-строк — `chip_label_<i>` (getlist), маппинг:
  `chip_words_<i>` (текст через запятую → words ≤10), `chip_slug_<i>` (СЕЛЕКТ
  из существующих Category (catalog) / Collection (booking/stays); для events
  селектор скрыт — slug-скоринг у них не работает), `chip_price_min/max_<i>`.
- POST `action=save_questions`: собрать сырой questions-dict → targeted-write
  в `cfg["finder"]["questions"]` (enabled не трогается — замок
  test_cabinet_toggle_preserves_custom_questions) → `siteconfig.normalize`
  (валидация/капы/presence-minimal бесплатно). Пустая форма → удалить
  questions (возврат к пресету архетипа).
- Кнопка «Branchen-Vorlage laden»: пишет пресет `finder._TREES`-дерева тенанта
  в questions как стартовую точку редактирования (после — редактируется).
- Живое превью справа/ниже: текущий `tree_for` (уже в контексте) остаётся.
- Уникальность q.key/chip.key гарантирует вьюха (slugify + суффикс -2/-3).

## §2 Ограничения (честно по движку)

- Маппинги — только реально исполняемые: words (+2/слово), collection/category
  slug (+3, по primary-kind), price min/max (жёсткий фильтр). video/фасеты —
  НЕ поддержаны движком, в UI не показываем.
- Свободный slug не вводится (селект из живых Collection/Category — принцип
  LS-3 «не доверять свободному вводу», мёртвых чипов не будет).
- Кастом-лейблы владельца — plain-текст, не переводятся (конвенция FD-1).

## §3 Замки

- Round-trip: POST формы → tree_for возвращает кастом; enabled цел; пустая
  форма → questions удалены (пресет вернулся); normalize-замки целы
  (presence-minimal, junk-дроп); чип со slug реальной коллекции скорит +3
  (существующий test_custom_tree_overrides_preset — паттерн).
- Существующие 17 test_finder зелёные.

## §4 Инкременты

1. FD-3a+b: форма (вопросы+чипы+маппинги+селекторы) + POST + пресет-кнопка +
   тесты. 2. Докблок (ТЗ D4 ✅, task-catalog FD, CLAUDE.md, build-log) + i18n
   хрома формы (немецкие строки кабинет-конвенции).
