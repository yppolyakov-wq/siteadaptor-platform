# MCP-каталог города: как включить и подключить к Claude / ChatGPT (T-8.10f, 2026-10-19)

Каталог Золингена можно подключить к ассистенту жителя (Claude, ChatGPT) как MCP-сервер.
Ассистент ищет предложения, открывает карточки и бизнесы и даёт человеку ссылку на
страницу бизнеса («отложить», «купон», «купить», «записаться» — человек завершает сам).
Оплаты через ассистента нет. ИИ на нашей стороне нет: всё отвечает база тем же
движком, что портал. План — `docs/t8-10-rest-plan-2026-10-19.md`.

## 1. Включить на сервере

В `.env.prod` добавить и перезапустить (`./scripts/deploy.sh single` или рестарт web):

```
MCP_ENABLED=1
MCP_PORTAL_HOSTS=solingen.<ваш домен>
```

`MCP_PORTAL_HOSTS` — список хостов пилота через запятую (пусто = все активные порталы;
для пилота лучше явно). Без `MCP_ENABLED=1` адрес `/mcp/` отвечает 404. Строка о MCP в
`llms.txt` портала появляется/пропадает с задержкой до ~2 минут (кэш страниц).

Необязательно (значения по умолчанию разумные): `MCP_RATE_PER_IP` (300 запросов/мин на
адрес), `MCP_RATE_GLOBAL` (3000/мин на сервер), `MCP_MAX_BODY` (64 КБ),
`PORTAL_STATS_MACHINE_LIMIT` (3000 учтённых показов/ч на адрес платформы ассистента).

## 2. Проверить

На сервере:

```
docker compose --env-file .env.prod -f docker-compose.prod.yml --profile single \
  run --rm web python manage.py mcp_smoke --url https://solingen.<ваш домен>/mcp/ --query Brot
```

Ожидаемо: три строки «✓» (initialize, tools/list, search_offers) и до пяти предложений.
Демо-бизнесы помечены «[демо]», платные размещения — «[реклама]».

С своего компьютера можно открыть MCP Inspector (`npx @modelcontextprotocol/inspector`),
транспорт «Streamable HTTP», адрес тот же, без авторизации. Inspector, работающий в
браузере, шлёт заголовок `Origin` — сервер отвечает 403, пока этот Origin не добавлен в
`MCP_ALLOWED_ORIGINS` (например `MCP_ALLOWED_ORIGINS=http://localhost:6274`). Серверные
клиенты Claude/ChatGPT Origin не шлют — им переменная не нужна.

## 3. Подключить в Claude

Настройки → Connectors → «Add custom connector» → адрес
`https://solingen.<ваш домен>/mcp/`, без авторизации. В новом чате включить коннектор и
спросить, например: «Was gibt es heute in Solingen-Ohligs unter 10 €?» или «Wo kann ich
in Gräfrath Brot kaufen?».

## 4. Подключить в ChatGPT

Настройки → Apps & Connectors → Advanced → Developer mode (доступность зависит от
тарифа) → Create → адрес `https://solingen.<ваш домен>/mcp/`, Authentication: «No
authentication».

## 5. Что видит ассистент

Инструменты: `search_offers` (текст + фильтры: раздел, признак, район, цена, дата,
«открыто сейчас», размер; условия из текста вроде «unter 10 €», «heute» применяются сами
и возвращаются в `applied_filters`), `get_offer`, `get_business`, `list_categories`,
`list_districts`. Правила те же, что на портале: скрытое/истёкшее/чужой город не видно,
секретная цена (mystery) не раскрывается, платные размещения в общем порядке с пометкой
«Anzeige», демо — только на превью-портале и с пометкой `demo`.

## 6. Статистика

Экран «Stadtportal» в кабинете бизнеса: показы и открытия от ассистентов — отдельной
строкой «Assistenten (KI): gezeigt · geöffnet» (это запросы ассистентов, не люди, в
воронку людей не входят). Резервы/купоны/заказы, сделанные по ссылке ассистента, идут
в обычную воронку с каналом «Assistenten (KI)».

## 7. Datenschutzerklärung платформы — строка для юриста (черновик)

> **KI-Assistenten (MCP-Schnittstelle).** Der Stadtkatalog kann von KI-Assistenten
> (z. B. Claude, ChatGPT) über eine öffentliche Schnittstelle abgefragt werden. Dabei
> werden ausschließlich die öffentlich sichtbaren Angebote und Unternehmensprofile
> übermittelt. Suchbegriffe speichern wir zusammengefasst je Tag, ohne Kennung der
> anfragenden Person; E-Mail-Adressen, Telefonnummern und Kontonummern versuchen wir vorher
> automatisch zu entfernen. Da Suchbegriffe Freitext sind, können sie dennoch
> personenbezogene Angaben enthalten (z. B. einen Namen), wenn diese eingegeben werden.
> Diese Suchstatistik wird nach 180 Tagen gelöscht, einmalige Suchbegriffe nach 30 Tagen.
> Aufrufe und Anzeigen von Angeboten zählen wir je Angebot und Tag ohne Personenbezug;
> diese Zähler bewahren wir 400 Tage auf. Zum Schutz vor Missbrauch (Begrenzung der
> Anfragenrate) verarbeiten wir die IP-Adresse des anfragenden Systems kurzzeitig im
> Arbeitsspeicher (höchstens etwa eine Stunde); zusätzlich protokolliert unser Webserver
> Zugriffe technisch (Server-Logfiles, siehe oben). Rechtsgrundlage ist Art. 6 Abs. 1
> lit. f DSGVO. Die Verarbeitung Ihrer Anfrage beim jeweiligen Assistenten richtet sich
> nach dessen Datenschutzbestimmungen.

> Для юриста: сроки хранения взяты из настроек (`SEARCH_LOG_RETENTION_DAYS` 180, `…_SINGLE` 30,
> `PORTAL_STATS_RETENTION_DAYS` 400); срок хранения access-логов Caddy указать по факту сервера.

## 8. «Отложить» и «купон» из ассистента (F-4)

Ассистент может попросить бизнес отложить товар акции («Zurücklegen») или выдать
купон. Сам он ничего не создаёт: человек получает письмо со ссылкой, открывает страницу
бизнеса и нажимает кнопку — только тогда появляется резерв или купон (как с витрины,
канал «Assistenten (KI)»). В письме есть ссылка «Das war ich nicht»: она удаляет запрос
и 30 дней не присылает такие письма на этот адрес.

Включить — в `.env.prod` и рестарт:

```
MCP_ACTIONS_ENABLED=1
```

Работает только с настоящей почтой (Resend — `RESEND_API_KEY`, или SMTP — `EMAIL_HOST`
и др.). С тестовой (console) почтой инструментов `request_reservation`/`request_coupon`
у ассистента просто нет. `mcp_smoke` печатает строку «действия … включены/выключены».
Письмо шлёт фоновая задача — нужен работающий Celery worker (он уже есть в деплое).

Лимиты (меняются переменными, значения по умолчанию разумные): одно письмо в сутки на
адрес и акцию, 3 в сутки на адрес (`MCP_ACTION_RATE_EMAIL`), 50 в сутки на акцию
(`MCP_ACTION_RATE_OFFER`), 300 писем в час на всё (`MCP_ACTION_RATE_GLOBAL`), 20
запросов за 10 минут с адреса платформы ассистента (`MCP_ACTION_RATE_IP`). Ссылка живёт
не дольше суток и не дольше конца акции (`MCP_ACTION_TTL`).

Демо-бизнесы на превью-портале работают так же (резерв настоящий, с пометкой «Demo»),
но письмо владельцу демо не уходит. Демо-засев пишет адреса только в `example.com` —
после деплоя нужен пересев демо, тогда вход в кабинет демо — `<slug>@example.com`.

Для Datenschutzerklärung — дополнение к §7 (черновик для юриста):

> **Reservierung und Coupons über KI-Assistenten.** Bitten Sie einen KI-Assistenten,
> ein Angebot für Sie zurücklegen zu lassen oder einen Coupon anzufordern, senden wir an
> die angegebene E-Mail-Adresse einen Bestätigungslink. Bis zur Bestätigung speichern
> wir die Adresse (und, falls angegeben, Ihren Namen) verschlüsselt und höchstens 24
> Stunden, ausschließlich für diese Anfrage; ohne Bestätigung wird nichts weiter
> gespeichert. Erst mit Ihrer Bestätigung entsteht die Reservierung bzw. der Coupon beim
> jeweiligen Unternehmen (Art. 6 Abs. 1 lit. b DSGVO). Über den Link „Das war ich nicht"
> löschen Sie die Anfrage; wir senden dann 30 Tage lang keine solchen E-Mails an diese
> Adresse (dafür speichern wir einen nicht umkehrbaren Kennwert der Adresse). Werbung
> enthält die E-Mail nicht.

## 9. Дальше

F-6 — оценка пилота через 4 недели (вызовы, показы, переходы, сделки канала
«Assistenten (KI)», доля пустых выдач). Затем T-8.10g/d/b по плану
`docs/t8-10-rest-plan-2026-10-19.md`.
