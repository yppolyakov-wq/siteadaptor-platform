"""T-8.10f F-5: проверка MCP-сервера каталога по адресу (после деплоя).

    python manage.py mcp_smoke --url https://solingen.<base>/mcp/ [--query Brot]

Шаги — те же, что делает Claude/ChatGPT при подключении: initialize → tools/list →
tools/call search_offers. Код выхода 1, если хоть один шаг не прошёл.
"""

from __future__ import annotations

import json

import requests
from django.core.management.base import BaseCommand, CommandError

EXPECTED_TOOLS = {"search_offers", "get_offer", "get_business", "list_categories", "list_districts"}


class Command(BaseCommand):
    help = "Проверить MCP-сервер каталога города: initialize, tools/list, search_offers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url", required=True, help="Адрес эндпоинта, например https://solingen.<base>/mcp/"
        )
        parser.add_argument("--query", default="", help="Текст поиска (пусто — свежие предложения)")
        parser.add_argument("--timeout", type=float, default=15.0)

    def handle(self, *args, **opts):
        url = opts["url"]
        if not url.startswith(("https://", "http://")):
            raise CommandError("--url должен начинаться с https:// или http://")
        session = requests.Session()
        version = None
        msg_id = 0

        def call(method, params=None):
            nonlocal msg_id
            msg_id += 1
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if version:
                headers["MCP-Protocol-Version"] = version
            body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
            if params is not None:
                body["params"] = params
            resp = session.post(
                url, data=json.dumps(body), headers=headers, timeout=opts["timeout"]
            )
            if resp.status_code != 200:
                raise CommandError(f"{method}: HTTP {resp.status_code} — {resp.text[:200]}")
            data = resp.json()
            if "error" in data:
                raise CommandError(f"{method}: {data['error']}")
            return data["result"]

        init = call(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "mcp_smoke", "version": "1"},
            },
        )
        version = init["protocolVersion"]
        info = init.get("serverInfo", {})
        self.stdout.write(
            f"✓ initialize: {info.get('title') or info.get('name')} (протокол {version})"
        )

        names = {tool["name"] for tool in call("tools/list")["tools"]}
        missing = EXPECTED_TOOLS - names
        if missing:
            raise CommandError(f"tools/list: нет инструментов {sorted(missing)}")
        self.stdout.write(f"✓ tools/list: инструментов {len(names)}")

        args = {"limit": 5}
        if opts["query"]:
            args["query"] = opts["query"]
        res = call("tools/call", {"name": "search_offers", "arguments": args})
        if res.get("isError"):
            raise CommandError(f"search_offers: {res['content'][0]['text']}")
        data = res["structuredContent"]
        self.stdout.write(f"✓ search_offers: найдено {data['total']}")
        for item in data["items"]:
            flags = " ".join(
                flag
                for flag, on in (("[реклама]", item["sponsored"]), ("[демо]", item["demo"]))
                if on
            )
            price = f"{item['price']} {item['currency']}" if item.get("price") else "—"
            self.stdout.write(f"   · {item['title']} — {price} {flags}".rstrip())
        self.stdout.write(self.style.SUCCESS("MCP-сервер отвечает корректно."))
