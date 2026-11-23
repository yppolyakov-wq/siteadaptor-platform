# Правки ревью диффа P0 (M5d-2) и K — задание исполнителю (снять после стопки)
Ревью: django-reviewer, security-reviewer, silent-failure-hunter, a11y-architect (CRITICAL 0). Порядок: замок
(красный) → правка. Каждая находка — строка в отчёте для `docs/skill-feedback.md` («Когда» = дифф).

## Ядро (`apps/core/window_parts.py`, `site_schema.py`, `nav_registry.py`, `_bw_inhalt.html`)
1. **HIGH (SFH-H1)** сводка строки с `source`: не брать `selected["summary"]` (у строки объекта это статус «Standard:
   sichtbar»): `source.shows`, иначе `section.label`. Замок: строка объекта с `source` без `shows` — в сводке нет
   «Standard:» / «nur hier». Замок реестра: у каждого `ContentSource` задан `shows`.
2. **MEDIUM (DJ-M1, SFH-M1)** `_filled`: не вызывать callable; только поля модели и ключи словаря; нединамический путь
   (нет атрибута, значение не dict там, где ждём dict) — `logger.error` и пустое `filled`. «0 = leer» — в докстринг.
   Замок реестра: каждый путь `fields` существует у модели вида (`_meta.get_field`), не связь и не метод.
3. **MEDIUM (SEC, SFH-L2)** `screen_closed(target_url=…)`: у цели нет правила в `view_perms` (`rule_for` → None) —
   закрыто ("module") и `logger.error`. Замок: каждая цель `_OBJECT_EDIT_URLS` и адреса `content_pages.edit_url_for_code`
   имеет правило.
4. **MEDIUM (SFH-M2, M3, DJ-L1, SFH-L3)** журнал: `NoReverseMatch` в `object_back`; `Resolver404` в `screen_closed`;
   ветка «obj есть, back нет» в `_content_link`; неизвестный код причины. Замки с `caplog`.
5. **MEDIUM (SFH-M4)** замок реестра: `source.kind != "auto"` требует `content_nav`, и `entry_by_url` его находит.
6. **LOW (DJ-L2)** строка объекта: «sichtbar — bei allen …» только у типа; у объекта без `summary` — «sichtbar.».
7. **LOW (DJ-L3)** `object_field_label`: не строить форму на каждый показ — кэш словаря `{field: lazy_label}` на процесс.
8. **LOW (DJ-L4)** якоря-комментарии модулей в `detail_sections.py` — над своими абзацами (реестр не менять).
   ВНИМАНИЕ: параллельные срезы правят кортежи этого файла — менять ТОЛЬКО строки комментариев-якорей, минимально.
9. **MEDIUM (DJ-M2)** замки устройства файла: из `test_registry_is_written_out_for_parallel_slices` убрать условие «ни у
   одного раздела нет source» (срезы его заводят); `test_registry_equals_the_base` оставить (сравнивает ключи, подписи,
   флаги — не `source`; проверь).
10. **a11y M2** `lang` у имени объекта/страницы: ставить только когда язык содержимого (сейчас `settings.LANGUAGE_CODE`)
    отличается от языка интерфейса (`translation.get_language()`); замок: de-интерфейс — без `lang`, ru — `lang="de"`.
11. **a11y M3, M4** ссылка «Inhalt bearbeiten»: подпись одним `<span>` внутри `<a>` (иначе `inline-flex` режет пробелы:
    «Seiten ›Über uns»); `break-words` у абзаца ссылки и абзаца причины. G2 байт-в-байт СОХРАНИТЬ (эталон
    `golden_fb33m5d2/g2`): новая разметка — только при `source`; если иначе нельзя — стоп и вопрос в отчёте.
12. **a11y H1** скрытая строка: окно открыто из «Ausgeblendet», закрыто «Fertig»/Esc без правок → `details[data-schema-hidden]`
    открыт и фокус на ссылке строки. Проверь по коду (`site_schema_views.py` ~801 `last_hidden`/`anchor`), добавь
    серверный замок; если не так — исправь минимально на сервере. Случай в стенд `scripts/fb33_m5d_inhalt_stand.py`
    (общая функция, используемая случаями со скрытой строкой; сами случаи добавит срез G4).
13. **a11y (стенд, Y7)**: в стенд — 320×568 без горизонтальной прокрутки документа и окна; `html{font-size:200%}` на
    1440 и 390 — «Fertig» и × достижимы; 844×390 — окно прокручивается, ссылка при фокусе видна.

## K (`apps/events`)
14. **MEDIUM (SFH-M5, было и до среза — потеря данных)**: сохранённый ответ select, которого нет среди вариантов (старый
    или ручной) — не терять: в `participants.slots` дорисовать вариант `(value, value)`; замок: значение в HTML как
    `selected` и переживает повторный POST.
