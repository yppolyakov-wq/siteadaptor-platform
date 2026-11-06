"""AIS A-6a: эталонные фразы помощника (5 языков кабинета × каждый обработчик роутера).

Источник правды для теста `test_assistant_phrases` и команды `assistant_eval`. Магазин —
фикстура: категория «Kuchen» (в ней «Käsekuchen»), товар «Apfelstrudel».

`mode`: rules — без ИИ; ai — с включённой задачей `assistant_actions` (модель не зовётся,
проверяется маршрут); followup — после хода `PREV`. `note`: synthetic | real (фразы из
реальной обратной связи владельцев — отдельная отметка против подгонки правил под набор) |
negative (похоже на действие, но это вопрос — ждём `answer`).
"""

from __future__ import annotations

from dataclasses import dataclass

LANGS = ("de", "en", "ru", "uk", "tr")
PREV = "скрой Apfelstrudel"


@dataclass(frozen=True)
class Phrase:
    text: str
    lang: str
    route: str
    mode: str = "rules"
    note: str = "synthetic"


def _p(route, mode="rules", **by_lang):
    return [Phrase(text, lang, route, mode) for lang, text in by_lang.items()]


PHRASES: tuple[Phrase, ...] = tuple(
    [
        *_p(
            "bulk",
            de="alle Kuchen 10 % teurer",
            en="all products in Kuchen 10 % cheaper",
            ru="все товары категории Kuchen подними на 10 %",
            uk="усі товари Kuchen підвищ на 10 %",
            tr="Kuchen tüm ürünler %10 artır",
        ),
        *_p(
            "changes",
            de="Preis Käsekuchen auf 3,50 €",
            en="change the price of Käsekuchen to 3.50 €",
            ru="скрой Käsekuchen",
            uk="сховай Käsekuchen",
            tr="Käsekuchen gizle",
        ),
        *_p(
            "pages",
            de="Produkte 4 pro Reihe anzeigen",
            en="show products 4 per row",
            ru="покажи товары 4 в ряд",
            uk="покажи товари 4 в ряд",
            tr="ürünleri 4 per satıra göster",
        ),
        *_p(
            "escalate",
            de="Die Bezahlung funktioniert nicht",
            en="payment is not working",
            ru="оплата не работает",
            uk="оплата не працює",
            tr="ödeme çalışmıyor",
        ),
        *_p(
            "create",
            de="Kategorie Torten anlegen",
            en="create category Torten",
            ru="создай категорию Торты",
            uk="створи категорію Торти",
            tr="Torten kategorisi oluştur",
        ),
        *_p(
            "answer",
            de="Wie ändere ich die Öffnungszeiten?",
            en="How do I change the opening hours?",
            ru="Как изменить часы работы?",
            uk="Як змінити години роботи?",
            tr="Çalışma saatlerini nasıl değiştiririm?",
        ),
        # отрицательные: вопрос с именем товара или словом действия — НЕ действие (route answer)
        *[
            Phrase(text, lang, "answer", note="negative")
            for lang, text in (
                ("de", "Kann ich den Käsekuchen auch als Gutschein verkaufen?"),
                ("de", "Was kostet der Käsekuchen?"),
                ("en", "Which payment methods are supported?"),
                ("ru", "сколько стоит Käsekuchen?"),
                ("uk", "Скільки коштує Käsekuchen?"),
                ("tr", "Käsekuchen ne kadar?"),
            )
        ],
        *_p(
            "ai_actions",
            "ai",
            de="Den Apfelstrudel bitte erstmal nicht mehr anbieten",
            en="please stop offering the Apfelstrudel for now",
            ru="Apfelstrudel пока не предлагать",
            uk="Apfelstrudel поки не пропонувати",
            tr="Apfelstrudel şimdilik sunulmasın",
        ),
        *_p(
            "mixed",
            "ai",
            de="Kategorie Torten anlegen und Apfelstrudel ausblenden",
            en="create category Torten and hide Apfelstrudel",
            ru="создай категорию Торты и скрой Apfelstrudel",
            uk="створи категорію Торти і сховай Apfelstrudel",
            tr="Torten kategorisi oluştur ve Apfelstrudel gizle",
        ),
        *_p(
            "followup",
            "followup",
            de="und den Käsekuchen auch",
            en="Käsekuchen too",
            ru="и Käsekuchen тоже",
            uk="і Käsekuchen теж",
            tr="Käsekuchen de",
        ),
    ]
)
