# AIS AS-1 «Помощник: одно поле» — план (2026-11-06)

Фидбэк владельца (скриншоты шторки): «каша в помощнике, у нас же один мозг». Макет утверждён —
артефакт «Assistent — один вход» (3 экрана). Без миграций.

## Что было (проверено по коду)
1. Три входа: GET-поиск «Wo stelle ich das ein?» (до роутера A-5), поле вопроса (роутер),
   кнопка «Was möchten Sie anlegen?» (дубль: создание уже в поле).
2. Поле — в самом низу, под тремя списками проверок.
3. «Auf dieser Seite fehlt» печатает НАЗВАНИЕ проверки («Allergene bei allen Gerichten angegeben»).
4. Диагноз со сбоем проверки или только справкой (демо) — красный «prüfen».
5. Две строки про ИИ подряд.

## Как стало
- **Одно поле наверху** («Fragen oder sagen, was zu tun ist»), три подсказки-кнопки
  (`formnovalidate`, значение — поле `frage`). Ниже ответ, «Hilfe zu dieser Seite», свёрнутые
  карточки «Status Ihres Shops» (счётчики «N erledigen · N nicht geprüft») и «Verlauf».
- **«Wo stelle ich das ein?» — внутри ответа:** роутер (обработчик `answer`) ищет экраны по
  словам фразы (`assistant.where_for_text`, баллы по значимым словам, ≤ 3) и кладёт ссылки в
  запись задачи (`assistant_ai.WHERE` — как `ROUTE`), показ строит URL с правами смотрящего.
  GET `?q=` (старые ссылки) работает, формы поиска нет. Кнопка «Was möchten Sie anlegen?» снята.
- **Задачи вместо названий:** `readiness.Item.todo` у пунктов-причастий («Impressum
  vervollständigen», «E-Mail-Adresse bestätigen», «Allergene … angeben», «Anfrageformular
  anpassen»); помощник берёт `todo or label`.
- **Честные бейджи:** `tone` диагноза — ok (зелёный) · problem (красный, есть PROBLEM) ·
  unknown (серый «nicht geprüft») · info (синий «Hinweis»).
- **Одна пометка про ИИ:** `{% ai_notice %}` + «Bitte keine Kundendaten eingeben.»

## ECC
Скиллы: accessibility, django-patterns, django-tdd. Агенты: `a11y-architect` (порядок фокуса,
details/summary, бейджи не только цветом), `django-reviewer`; стенд Playwright 390/1440.
Замки: поле — первый элемент формы ввода в KI-вкладке; формы поиска и кнопки anlegen нет; где-
ссылки в ответе и истории; tone диагноза по четырём случаям; todo-подписи; счётчик состояния.
