# M21.8 — визуальный редактор во всех текстовых полях витрины (2026-11-10)

Запрос владельца (haanerteeladen): «Impressum/Datenschutz/AGB тоже в страницах; расширь
визуальный редактор для всех мест с текстовой областью — описание товара, категорий,
текстовых страниц, доставки/оплаты; если что-то забыл — укажи».

## 1. Что уже есть
- Редактор `templates/catalog/_richtext_editor.html` (contenteditable поверх textarea —
  textarea остаётся в DOM, W0). Режим «text» — B/I/U, списки, ссылка; режим «page»
  (`data-rte="page"`) — плюс H2/H3/¶ и картинка.
- Санитайзер `apps/core/richtext.py`: `sanitize` (описания), `sanitize_page` (страницы),
  `to_plain` (M21.8, текст для фидов/PDF/писем/JSON-LD). Фильтры `rich_text`/`is_rich`.
- Работает только на описании товара и своих страницах (M21.6).

## 2. Инвентаризация (разведка 2026-11-10)
Поля, которые владелец пишет в кабинете и которые видит покупатель:

| Поле | Кабинет | Витрина сегодня |
|---|---|---|
| Product.description | product_form | ✅ rich; `_dish_info` — ❌ показывал теги текстом |
| Category.description | category_form | pre-line |
| Service.description, Resource.bio | service_page, resource_page | pre-line |
| StayUnit.description, StaySettings.house_rules | unit_page, stay_settings | pre-line |
| Event.description, Tour.description, Teacher.bio | event/tour/teacher_form | pre-line |
| BlogPost.body | blog_new/blog_edit | pre-line |
| Promotion.description | promotion_form | pre-line |
| Combo.description | combo_form | pre-line |
| LegalDoc.text (Impressum/Datenschutz/Widerruf/AGB) | legal_docs | pre-line |
| site about_text | site_home (Studio) | pre-line |

**Доставка/оплата — свободного описания НЕТ** (ответ на вопрос владельца): у способа доставки
только однострочное «Liefergebiet» (`area_text`), у оплаты — реквизиты. Текст про доставку и
оплату живёт в своих страницах «Versand» / «Zahlungsarten» (M21.6) — там редактор уже есть.

Не трогаем (не «текст для чтения»): построчные списки (зоны, тарифы веса, отзывы, команда,
FAQ-пары), внутренние заметки, однострочные поля, SEO-мета, hero/слайды (короткие).

## 3. Правила
1. Хранение: форма чистит `richtext.sanitize` при сохранении; рендер санитайзит повторно
   (второй рубеж, легаси/обходные записи).
2. Рендер — один тег `{% rich_block text %}`: rich → санитайзнутый HTML (`.rich-text`), иначе
   прежний pre-line (легаси-текст выглядит как раньше, байт-в-байт по содержимому).
3. Всё, что уходит наружу текстом (фиды, PDF, письма, JSON-LD, og, Telegram/соцсети,
   агрегатор) — через `richtext.to_plain`.
4. Правовые тексты: автотекст из данных бизнеса остаётся плоским; свой текст владельца может
   быть rich.
5. Переводы (`*_i18n`, textarea на локаль) получают редактор вместе с базой.
6. Таблицы, цвета, шрифты, `style`, видео — нет (единый дизайн; таблица — по решению владельца).

## 4. Батчи
- **B0 ✅** «Rechtliche Seiten» строками в «Seiten» (`?tab=` открывает вкладку «Recht»);
  фид Google/PDF-меню без HTML (`to_plain`).
- **B1–B3 ✅ (2026-11-10, одним батчем)** тег `rich_block` + каталог/акции/наборы: Category, Promotion, Combo, `_dish_info`;
  `to_plain` в JSON-LD/og акции и публикациях.
  B2 услуги/номера/события: Service, Resource.bio, StayUnit, house_rules, Event, Tour,
  Teacher, BlogPost.
  правовые тексты. «Über uns» (about_text в Студии) — ещё нет: правится на канве инлайн
  (плоский текст), визуальный редактор там — отдельный шаг.
- **Security-review ✅:** HIGH — редактор клал сохранённое значение в `innerHTML` без
  очистки (с SR-3) → DOMParser + белый список; `is_rich` с границей тега.
- **B4 ✅ (2026-11-11)** режим «page»: «🖼» грузит картинку с компьютера (POST
  `content-page-image`: право Website-Bearbeiten, лимит 60/ч, проверка формата/размера,
  EXIF снимается, папка `pages/` — публичная), «↔» центрирует абзац (`sf-center`),
  «▥» — две колонки (`sf-grid` + `sf-col-8`, курсор в первую колонку). Медиатека
  знает картинки внутри страниц и правовых текстов — не даст удалить занятую (дыра M21.6:
  картинки импорта CS-Cart считались свободными). Таблица — не делали, ждёт решения.

## 5. ECC-прогоны
- Скиллы до кода: `django-security` (XSS: санитайз на записи и рендере), `django-tdd`,
  `accessibility` (кнопки панели — aria-label, клавиатура).
- Агенты: `security-reviewer` после B1 (новые места вывода HTML) и после B4 (загрузка файла);
  `django-reviewer` перед мержем; `a11y-architect` на панель редактора (B4);
  Playwright-стенд: редактор в формах категории/акции/услуги/Recht + рендер витрины (JS).
- Замок: «каждый `{{ x.description_text }}` / `whitespace-pre-line` поля из таблицы §2
  рендерится через `rich_block`» (скан шаблонов).
