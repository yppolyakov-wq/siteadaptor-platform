/* FB-33 M3-1b (ревью 2): сбой правки виден всегда — сообщение в блоке сообщений экрана,
   без него — в панели блока, без неё — обычным окном браузера; молчаливой перезагрузки нет.
   Отключённая (подменённая) форма уходит своей копией обычной отправкой — с теми же полями
   (ref нажатого блока, токен открытия окна). */
function aufbauError(text) {
  var box = document.querySelector("[data-schema-messages]");
  text = text || (box && box.getAttribute("data-schema-error")) || "";
  if (!text) return;
  var host = box || document.querySelector("[data-schema-panel]");
  if (!host) { window.alert(text); return; }
  var p = document.createElement("p");
  p.setAttribute("role", "alert");
  p.className = "rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800";
  p.textContent = text;
  host.appendChild(p);
  host.scrollIntoView({ block: "start" });
}

function aufbauSubmitCopy(form, submitter) {
  var copy = form.cloneNode(true);
  copy.hidden = true;
  if (submitter && submitter.name) {
    var op = document.createElement("input");
    op.type = "hidden"; op.name = submitter.name; op.value = submitter.value;
    copy.appendChild(op);
  }
  document.body.appendChild(copy);
  HTMLFormElement.prototype.submit.call(copy);
}

/* FB-27 R1: «Seitenaufbau». Экран работает без JS; здесь только фокус.
   Тип страницы меняется кнопкой «Öffnen», не по change: стрелки в списке на Windows
   сразу шлют change, и страница перезагружалась бы при просмотре списка (WCAG 3.2.2). */
(function () {
  "use strict";
  // После выбора блока или действия фокус — в панель (на телефоне она под схемой).
  if (location.hash === "#schema-panel") {
    var panel = document.getElementById("schema-panel");
    if (panel) panel.focus();
  } else if (location.hash.indexOf("#schema-tab-") === 0) {
    // FB-33 M3-1: переход по вкладке окна блока — фокус во вкладку (скринридер читает её имя)
    var tab = document.getElementById(location.hash.slice(1));
    if (tab && !tab.hidden) tab.focus();
  }
})();

/* FB-27 (макет Main): правка в панели блока сразу уходит в черновик — без «Übernehmen».
   Поверх работающей формы: без скриптов кнопка остаётся; при сбое запроса форма
   отправляется обычным путём, правка не теряется. */
(function () {
  "use strict";
  if (!window.fetch || !window.DOMParser || !window.FormData) return;
  if (!HTMLFormElement.prototype.requestSubmit) return;
  // FB-30.2: настройки типа страницы (вид баннера, шаблон, карточка) — тоже без «Übernehmen».
  // Настройка вывода списка (галочка «и для других списков») остаётся с кнопкой: галочка
  // переписала бы другие страницы раньше, чем владелец выбрал вид.
  var FORMS = "[data-schema-fields],[data-schema-list],[data-schema-setting]:not([data-schema-manual])";
  var APPLY = 'button[value="update"],button[data-schema-apply]';
  var chain = Promise.resolve();
  var pending = 0;

  // Для сценариев и стилей: сколько правок ещё в пути.
  function busy() { document.documentElement.setAttribute("data-schema-busy", String(pending)); }

  function hideApply() {
    document.querySelectorAll(FORMS).forEach(function (form) {
      var btn = form.querySelector(APPLY);
      if (btn) btn.style.display = "none";
    });
  }

  function swap(doc, selector) {
    var now = document.querySelector(selector);
    var next = doc.querySelector(selector);
    if (now && next) now.replaceWith(document.importNode(next, true));
  }

  function refocus(target) {
    var el = null;
    if (target.id) el = document.getElementById(target.id);
    if (!el && target.name) {
      document.querySelectorAll(FORMS).forEach(function (form) {
        Array.prototype.forEach.call(form.elements, function (item) {
          if (!el && item.name === target.name && (target.type !== "radio" || item.value === target.value)) el = item;
        });
      });
    }
    if (el) el.focus({ preventScroll: true });
    return el;
  }

  function fallback(form) {
    var btn = form.isConnected && form.querySelector(APPLY);
    if (!btn) { aufbauError(); return; }  // ревью 2: не перезагружаем молча
    btn.style.display = "";
    form.requestSubmit(btn);
  }

  function apply(form, target) {
    var data = new FormData(form);
    // у настройки типа страницы своя операция (`op=setting` в скрытом поле формы)
    if (!form.matches("[data-schema-setting]")) data.set("op", "update");
    // Список и переключатель меняют состав полей панели — её перерисовываем целиком;
    // при правке текста панель не трогаем: владелец может уже печатать в соседнем поле.
    var whole = target.tagName === "SELECT" || target.type === "radio";
    pending += 1;
    busy();
    chain = chain
      .then(function () {
        // FB-33 M3-1b: правка не висит вечно — через 10 с запрос снимается (обычная отправка)
        var ctl = window.AbortController ? new AbortController() : null;
        if (ctl) setTimeout(function () { ctl.abort(); }, 10000);
        return fetch(location.href, {
          method: "POST", body: data, credentials: "same-origin", signal: ctl ? ctl.signal : undefined,
        });
      })
      .then(function (resp) {
        if (!resp.ok) throw new Error("status " + resp.status);
        return resp.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        if (!doc.querySelector("[data-schema-map]")) throw new Error("no schema");
        // Сообщения сервера (отказ, конфликт) — на своём месте; при отказе панель
        // показывает то, что действительно записано.
        swap(doc, "[data-schema-messages]");
        var refused = !!doc.querySelector('[data-schema-messages] [role="alert"]');
        if (refused) whole = true;
        swap(doc, "[data-schema-status]");
        swap(doc, "[data-schema-map]");
        if (whole) {
          // Фокус остаётся там, где владелец сейчас; набранный, но ещё не отправленный
          // текст соседнего поля переносится в новую панель.
          var panel = document.querySelector("[data-schema-panel]");
          var at = panel && panel.contains(document.activeElement) ? document.activeElement : null;
          var FOCUSABLE = "a,button,summary,input,select,textarea";
          var index = at ? Array.prototype.indexOf.call(panel.querySelectorAll(FOCUSABLE), at) : -1;
          var typed = at && (at.tagName === "TEXTAREA" || at.type === "text") ? at.value : null;
          swap(doc, "[data-schema-panel]");
          hideApply();
          var el = at ? refocus(at) : null;
          if (at && !el) {
            // У ссылок и кнопок панели нет ни id, ни имени — возвращаемся по месту в панели.
            panel = document.querySelector("[data-schema-panel]");
            var same = panel ? panel.querySelectorAll(FOCUSABLE)[index] : null;
            if (same && same.offsetParent !== null) same.focus({ preventScroll: true });
            else if (panel) panel.focus({ preventScroll: true });
          }
          if (!at && (!document.activeElement || document.activeElement === document.body)) refocus(target);
          if (el && typed !== null && el.value !== typed) {
            el.value = typed;
            el.dispatchEvent(new Event("change", { bubbles: true }));
          }
        } else {
          swap(doc, "#schema-result");
        }
        var live = document.querySelector("[data-schema-live]");
        if (refused) {
          // Отказ читает сам role="alert"; на телефоне лист не должен его закрывать.
          if (live) live.textContent = "";
          var box = document.querySelector("[data-schema-messages]");
          if (box) box.scrollIntoView({ block: "start" });
        } else if (live) {
          // Тот же текст подряд диктор не повторяет — сначала очищаем.
          live.textContent = "";
          setTimeout(function () { live.textContent = live.getAttribute("data-done") || ""; }, 100);
        }
      })
      .catch(function () { fallback(form); })
      .then(function () { pending -= 1; busy(); });
  }

  function panelForm(target) {
    var form = target && target.closest ? target.closest(FORMS) : null;
    // Поля поиска и кнопки ручного состава стоят внутри, но принадлежат своим формам.
    return form && target.form === form ? form : null;
  }

  // WCAG 3.2.2: стрелки в списке на Windows шлют change на каждый пункт. Список, который
  // листают с клавиатуры, применяется по Enter или при уходе из него; мышью — сразу.
  var byKeys = new WeakSet();
  var waiting = new WeakSet();

  function flush(target) {
    if (!waiting.has(target)) return;
    waiting.delete(target);
    var form = panelForm(target);
    if (form) apply(form, target);
  }

  document.addEventListener("keydown", function (e) {
    var t = e.target;
    if (!t || t.tagName !== "SELECT" || !panelForm(t)) return;
    if (e.key === "Enter") { e.preventDefault(); flush(t); } else { byKeys.add(t); }
  });
  document.addEventListener("pointerdown", function (e) {
    if (e.target && e.target.tagName === "SELECT") byKeys.delete(e.target);
  });
  document.addEventListener("focusout", function (e) { if (e.target) flush(e.target); });

  var radioTimer = null;
  document.addEventListener("change", function (e) {
    var target = e.target;
    var form = panelForm(target);
    if (!form) return;
    if (target.tagName === "SELECT" && byKeys.has(target)) { waiting.add(target); return; }
    if (target.type === "radio") {
      // FB-29 R4: стрелки в группе переключателей шлют change на каждый шаг — отправляем
      // один раз, когда выбор остановился.
      clearTimeout(radioTimer);
      radioTimer = setTimeout(function () { apply(form, target); }, 350);
      return;
    }
    apply(form, target);
  });

  // Пока правка в пути, «Speichern» и другие действия ждут её — иначе запись могла бы
  // обогнать правку, и та осталась бы в черновике.
  document.addEventListener("submit", function (e) {
    if (!pending || e.defaultPrevented) return;
    var form = e.target;
    var submitter = e.submitter;
    e.preventDefault();
    // Enter в поле панели: правка уже в пути (change), вторая отправка не нужна.
    if (form.matches(FORMS) && (!submitter || submitter.value === "update")) return;
    if (form.hasAttribute("data-window-actions")) { afterPending(form, submitter); return; }
    chain.then(function () {
      if (!form.isConnected) { aufbauSubmitCopy(form, submitter); return; }  // ревью 2
      form.requestSubmit(submitter && submitter.isConnected ? submitter : undefined);
    });
  });

  // FB-33 M3-1b: «Abbrechen/Fertig» окна ждут правку в пути, но не дольше WAIT мс (иначе —
  // видимая ошибка). Панель могли подменить: уходит исходная форма — с ref того блока, на
  // котором нажали, — обычной отправкой (без молчаливой перезагрузки).
  var WAIT = 12000;
  function afterPending(form, submitter) {
    var timer = null;
    var late = new Promise(function (resolve) { timer = setTimeout(function () { resolve("late"); }, WAIT); });
    Promise.race([chain.then(function () { return "ok"; }), late]).then(function (how) {
      clearTimeout(timer);
      if (how === "late") { aufbauError(form.getAttribute("data-wait-error")); return; }
      if (form.isConnected) { form.requestSubmit(submitter && submitter.isConnected ? submitter : undefined); return; }
      aufbauSubmitCopy(form, submitter);
    });
  }

  hideApply();
})();

/* FB-29.5b (макет A): строку схемы можно перетащить мышью — она встаёт перед строкой, на
   которую её бросили, или после неё. Поверх кнопок «Nach oben / Nach unten»: с клавиатуры,
   на телефоне и без скриптов перестановка — ими. */
(function () {
  "use strict";
  if (!window.fetch || !window.DOMParser || !window.FormData) return;
  var dragged = null;

  function item(target) {
    // FB-30.8: свободное место ряда — тоже цель броска
    return target && target.closest ? target.closest("[data-schema-drag],[data-schema-slot]") : null;
  }

  function arm() {
    document.querySelectorAll("[data-schema-drag]").forEach(function (li) {
      li.setAttribute("draggable", "true");
      li.style.cursor = "grab";
      var grip = li.querySelector(".schema-grip");
      if (grip) { grip.classList.remove("hidden"); grip.style.touchAction = "none"; }
    });
  }

  function clear() {
    document.querySelectorAll("[data-schema-drop]").forEach(function (li) {
      li.removeAttribute("data-schema-drop");
      li.style.boxShadow = "";
    });
  }

  function side(li, e) {
    var box = li.getBoundingClientRect();
    // ряд бывает и вертикальным (вид «Telefon», узкий экран) — смотрим на действующую ось
    var inRow = li.parentElement && li.parentElement.children.length > 1 &&
      getComputedStyle(li.parentElement).flexDirection.indexOf("row") === 0;
    var after = inRow ? e.clientX > box.left + box.width / 2 : e.clientY > box.top + box.height / 2;
    return { after: after, inRow: inRow };
  }

  document.addEventListener("dragstart", function (e) {
    var li = item(e.target);
    if (!li || !li.hasAttribute("data-schema-drag")) return;  // место в ряду не перетаскивают
    dragged = li.getAttribute("data-schema-drag");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragged);
  });
  document.addEventListener("dragover", function (e) {
    var li = item(e.target);
    if (!dragged || !li || li.getAttribute("data-schema-drag") === dragged) return;
    e.preventDefault();
    clear();
    var s = side(li, e);
    li.setAttribute("data-schema-drop", s.after ? "after" : "before");
    var edge = s.inRow ? (s.after ? "3px 0 0 #4338ca" : "-3px 0 0 #4338ca") : (s.after ? "0 3px 0 #4338ca" : "0 -3px 0 #4338ca");
    li.style.boxShadow = edge;
  });
  document.addEventListener("dragend", function () { dragged = null; clear(); });
  function mark(li, point) {
    clear();
    var s = side(li, point);
    li.setAttribute("data-schema-drop", s.after ? "after" : "before");
    li.style.boxShadow = s.inRow ? (s.after ? "3px 0 0 #4338ca" : "-3px 0 0 #4338ca") : (s.after ? "0 3px 0 #4338ca" : "0 -3px 0 #4338ca");
  }
  // FB-29: перетаскивание пальцем (и пером) — за ручку строки. У сенсорных экранов нет
  // событий drag/drop, поэтому строку ведём по pointer-событиям; бросок шлёт то же
  // действие `move`, что мышь. Кнопки «nach oben / nach unten» остаются.
  var touch = null;
  document.addEventListener("pointerdown", function (e) {
    if (e.pointerType === "mouse" || !e.target.closest) return;
    var grip = e.target.closest(".schema-grip");
    var li = grip ? item(grip) : null;
    if (!li) return;
    e.preventDefault();
    touch = { ref: li.getAttribute("data-schema-drag"), id: e.pointerId, over: null };
    // события жеста идут к ручке, даже когда палец/перо ушли с неё
    try { grip.setPointerCapture(e.pointerId); } catch (err) { /* нет поддержки — не страшно */ }
    li.style.opacity = "0.6";
  });
  document.addEventListener("pointermove", function (e) {
    if (!touch || e.pointerId !== touch.id) return;
    e.preventDefault();
    var li = item(document.elementFromPoint(e.clientX, e.clientY));
    if (!li || li.getAttribute("data-schema-drag") === touch.ref) { touch.over = null; clear(); return; }
    touch.over = li;
    mark(li, e);
  }, { passive: false });
  function endTouch(e, cancelled) {
    if (!touch || e.pointerId !== touch.id) return;
    var t = touch;
    touch = null;
    document.querySelectorAll("[data-schema-drag]").forEach(function (li) { li.style.opacity = ""; });
    if (cancelled || !t.over) { clear(); return; }
    dragged = t.ref;
    dropOn(t.over, e);
  }
  document.addEventListener("pointerup", function (e) { endTouch(e, false); });
  document.addEventListener("pointercancel", function (e) { endTouch(e, true); });

  document.addEventListener("drop", function (e) {
    dropOn(item(e.target), e);
  });
  function dropOn(li, e) {
    var ref = dragged;
    dragged = null;
    // пока прошлая правка в пути (перетаскивание или поле панели) — новый бросок не шлём
    var busy = +document.documentElement.getAttribute("data-schema-busy") > 0;
    if (!ref || !li || busy || li.getAttribute("data-schema-drag") === ref) { clear(); return; }
    document.documentElement.setAttribute("data-schema-busy", "1");
    if (e.preventDefault) e.preventDefault();
    var slot = li.getAttribute("data-schema-slot");
    var where = slot ? "" : (side(li, e).after ? "after" : "before");
    clear();
    var keep = document.querySelector("[data-schema-draft] input[name=csrfmiddlewaretoken], form input[name=csrfmiddlewaretoken]");
    var data = new FormData();
    data.set("csrfmiddlewaretoken", keep ? keep.value : "");
    data.set("seite", new URLSearchParams(location.search).get("seite") || "home");
    data.set("op", slot ? "beside" : "move");
    data.set("ref", ref);
    data.set("value", slot ? slot : where + ":" + li.getAttribute("data-schema-drag"));
    if (new URLSearchParams(location.search).get("ansicht") === "telefon") data.set("ansicht", "telefon");
    fetch(location.pathname, { method: "POST", body: data, credentials: "same-origin" })
      .then(function (resp) { if (!resp.ok) throw new Error("status"); return resp.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        ["[data-schema-status]", "[data-schema-messages]", "[data-schema-map]", "[data-schema-panel]"].forEach(function (sel) {
          var now = document.querySelector(sel), next = doc.querySelector(sel);
          if (now && next) now.replaceWith(document.importNode(next, true));
        });
        document.querySelectorAll('[data-schema-fields] button[value="update"],[data-schema-list] button[value="update"]').forEach(function (b) { b.style.display = "none"; });
        arm();
        // фокус — на перенесённую строку (после замены схемы он иначе уходил в начало страницы)
        var moved = document.querySelector("[data-schema-drag]")
          ? Array.prototype.find.call(document.querySelectorAll("[data-schema-block]"), function (a) { return a.getAttribute("data-schema-block") === ref; })
          : null;
        if (moved) moved.focus({ preventScroll: true });
        var live = document.querySelector("[data-schema-live]");
        if (live) { live.textContent = ""; setTimeout(function () { live.textContent = live.getAttribute("data-done") || ""; }, 100); }
      })
      .catch(function () { aufbauError(); })  // ревью 2: перетаскивание не удалось — видно
      .then(function () { document.documentElement.setAttribute("data-schema-busy", "0"); });
  }
  // после правки из панели схема перерисовывается — перевооружаем строки
  new MutationObserver(arm).observe(document.body, { childList: true, subtree: true });
  arm();
})();
