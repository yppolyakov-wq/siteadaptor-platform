"""PH-2: SVG-иконки разделов каталога города для портала (вместо эмодзи).

Путь `d` для `<svg viewBox="0 0 24 24" stroke="currentColor">`. Эмодзи `Section.icon`
остаётся для бота и кабинета. Замок: у каждого раздела справочника есть иконка."""

ALL = "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"

SECTION_ICONS: dict[str, str] = {
    "lebensmittel-getraenke": "M5 10a7 4 0 0 1 14 0v8a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2zM9 10v4M13 10v4",
    "essen-gastronomie": "M4 3v8a3 3 0 0 0 6 0V3M7 3v18M17 3c-2 2-3 5-3 8h3v10",
    "mode-accessoires": "M8 3l-5 4 3 4 2-1v11h8V10l2 1 3-4-5-4a4 4 0 0 1-8 0z",
    "elektronik-technik": "M3 5h18v11H3zM8 20h8M12 16v4",
    "haus-garten": "M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6",
    "beauty-pflege": "M6 3l3 9M18 3l-3 9M9 12a3 3 0 1 0 0 6 3 3 0 0 0 0-6M15 12a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
    "gesundheit-fitness": "M3 12h3M18 12h3M6 8v8M18 8v8M9 10v4M15 10v4M9 12h6",
    "freizeit-erlebnisse": "M3 7h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4zM14 7v12",
    "kinder-familie": "M12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6M6 21v-6a6 6 0 0 1 12 0v6",
    "auto-mobilitaet": "M6 17a3 3 0 1 0 0-6 3 3 0 0 0 0 6M18 17a3 3 0 1 0 0-6 3 3 0 0 0 0 6M6 14l4-7h4l4 7M10 7l2 7",
    "handwerk-reparatur": "M14 6a4 4 0 0 0 5 5l-9 9a2 2 0 0 1-3-3l9-9a4 4 0 0 0-2-2z",
    "dienstleistungen": "M4 8h16v11H4zM9 8V5h6v3M4 13h16",
    "reisen-uebernachten": "M3 18V8M3 14h18v4M7 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4M11 10h8a2 2 0 0 1 2 2v2",
    "tiere": "M5 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4M19 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4M9 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4M15 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4M12 12c-3 0-5 3-5 5.5S9 21 12 19c3 2 5 1 5-1.5S15 12 12 12",
    "kunst-geschenke": "M3 9h18v4H3zM5 13v8h14v-8M12 9v12M12 9c-2-4-6-4-6-1s6 1 6 1M12 9c2-4 6-4 6-1s-6 1-6 1",
}


def icon_for(key: str) -> str:
    return SECTION_ICONS.get(key, ALL)
