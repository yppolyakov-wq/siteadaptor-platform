"""Тестовый помощник: поля формы так, как их отправит браузер (UX-D D3.1).

Ищет форму по id, отдаёт {имя: [значения]}: флажок без value — «on», невыбранный — не
шлётся, файл — не шлётся, поля в `<fieldset disabled>` — не шлются. Считает вложенные
формы и собирает мини-формы страницы (их скрытые поля)."""

from html.parser import HTMLParser


class FormFields(HTMLParser):
    def __init__(self, form_id):
        super().__init__()
        self.form_id = form_id
        self.in_main = False
        self.disabled = []
        self.fields = []
        self.names = set()
        self.nested_forms = 0
        self.mini_forms = []
        self._mini = None
        self._textarea = None
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            if self.in_main:
                self.nested_forms += 1
            elif a.get("id") == self.form_id:
                self.in_main = True
            else:
                self._mini = {}
            return
        if tag == "fieldset" and self.in_main:
            self.disabled.append("disabled" in a)
            return
        name = a.get("name")
        if self._mini is not None and tag == "input" and name:
            self._mini[name] = a.get("value", "")
        if not self.in_main:
            return
        if tag == "option" and self._select is not None:
            if self._select[2] is None:
                self._select[2] = a.get("value", "")
            if "selected" in a:
                self._select[1] = a.get("value", "")
            return
        if not name:
            return
        self.names.add(name)
        if any(self.disabled):
            return
        if tag == "input":
            kind = a.get("type", "text")
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            if kind == "file":
                return
            default = "on" if kind in ("checkbox", "radio") else ""
            self.fields.append((name, a.get("value", default)))
        elif tag == "textarea":
            self._textarea = [name, ""]
        elif tag == "select":
            self._select = [name, None, None]

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1] += data

    def handle_endtag(self, tag):
        if tag == "form":
            if self.in_main:
                self.in_main = False
            elif self._mini is not None:
                self.mini_forms.append(self._mini)
                self._mini = None
        elif tag == "fieldset" and self.in_main and self.disabled:
            self.disabled.pop()
        elif tag == "textarea" and self._textarea is not None:
            self.fields.append(tuple(self._textarea))
            self._textarea = None
        elif tag == "select" and self._select is not None:
            name, sel, first = self._select
            self.fields.append((name, sel if sel is not None else first))
            self._select = None


def form_post(html, form_id):
    """(данные POST {имя: [значения]}, парсер) для формы с id `form_id`."""
    parser = FormFields(form_id)
    parser.feed(html)
    data = {}
    for name, value in parser.fields:
        data.setdefault(name, []).append(value)
    return data, parser
