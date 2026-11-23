/* FB-33 M3-1b (ревью 2): сбой правки виден всегда — сообщение в блоке сообщений экрана,
   без него — в панели блока, без неё — обычным окном браузера. Нет и текста ошибки
   (`data-schema-error`) — причина в консоль и перезагрузка: страница покажет то, что записано.
   Отключённая (подменённая) форма уходит своей копией обычной отправкой — с теми же полями
   (ref нажатого блока, токен открытия окна). */
function aufbauError(text) {
  var box = document.querySelector("[data-schema-messages]");
  text = text || (box && box.getAttribute("data-schema-error")) || "";
  // ревью M5c (silent): без текста ошибки не молчать — страница покажет состояние сервера
  if (!text) {
    if (window.console) console.error("aufbau: Fehler ohne Meldungstext – Seite wird neu geladen");
    location.reload();
    return;
  }
  // FB-33 M3-2: при открытом окне блока фон под inert — сообщение пишется в само окно
  var inWindow = document.querySelector("dialog.ui-bwin[open] [data-bwin-msgs]");
  var host = inWindow || box || document.querySelector("[data-schema-panel]");
  if (!host) { window.alert(text); return; }
  // ревью M3-2 (L9): в окне — одна ошибка, прежняя снимается
  if (inWindow) inWindow.querySelectorAll("[data-bwin-error]").forEach(function (n) { n.remove(); });
  var p = document.createElement("p");
  p.setAttribute("role", "alert");
  if (inWindow) p.setAttribute("data-bwin-error", "");
  p.className = inWindow ? "ui-bwin-alert" : "rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800";
  p.textContent = text;
  host.appendChild(p);
  host.scrollIntoView({ block: "start" });
}

/* FB-33 M3-2: окно блока открывается со скриптами, если в панели есть «Fertig» окна
   (`window_done`: выбран блок с окном, и в подтверждении удаления). Не открывается, пока
   в адресе шторка кабинета (`?drawer=`). Без скриптов — прежняя панель колонкой. */
function aufbauWindowWanted() {
  var panel = document.querySelector("[data-schema-panel]");
  if (!panel || !panel.querySelector('button[value="window_done"]')) return false;
  if (typeof HTMLDialogElement !== "function" || !HTMLDialogElement.prototype.showModal) return false;
  if (!window.fetch || !window.DOMParser || !window.FormData || !HTMLFormElement.prototype.requestSubmit) return false;
  return !new URLSearchParams(location.search).has("drawer");
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
  // FB-33 M3-2: окно закрыли («Fertig», «Abbrechen», ×, Esc) — фокус на строку того же
  // блока (запись на 30 с, стирается при чтении); строки больше нет — на заголовок схемы.
  var back = null;
  try {
    back = JSON.parse(sessionStorage.getItem("aufbauWindowBack") || "null");
    sessionStorage.removeItem("aufbauWindowBack");
  } catch (err) { back = null; }
  if (aufbauWindowWanted()) return;  // фокус ставит само окно
  var seite = new URLSearchParams(location.search).get("seite") || "home";
  if (back && back.seite === seite && Date.now() - back.ts < 30000) {
    // FB-33 M5c-3: «Fertig» и × — на ⚙ строки блока (у ★ и скрытых строк — их ссылка)
    var row = Array.prototype.find.call(document.querySelectorAll("[data-schema-gear]"), function (a) {
      return a.getAttribute("data-schema-gear") === back.ref;
    }) || Array.prototype.find.call(document.querySelectorAll("[data-schema-block]"), function (a) {
      return a.getAttribute("data-schema-block") === back.ref;
    });
    if (!row) {
      row = document.getElementById("schema-title");
      if (row) row.setAttribute("tabindex", "-1");
    }
    if (row) {
      // FB-33 M5b-2 (стенд): адрес после «Fertig» несёт #schema-panel — браузер ставит фокус
      // на якорь уже после скрипта и уводит его со строки. Якорь снять; после load — вернуть.
      if (location.hash && window.history && history.replaceState) {
        history.replaceState(history.state, "", location.pathname + location.search);
      }
      row.focus();
      window.addEventListener("load", function () {
        var at = document.activeElement;
        if (at !== row && (!at || at === document.body || at.id === "schema-panel")) row.focus();
      }, { once: true });
      return;
    }
  }
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
  // обычная отправка (запасной путь правки) уже ушла — ничего больше не отправляем
  var navigating = false;

  // Для сценариев и стилей: сколько правок ещё в пути.
  function busy() { document.documentElement.setAttribute("data-schema-busy", String(pending)); }

  function hideApply() {
    document.querySelectorAll(FORMS).forEach(function (form) {
      var btn = form.querySelector(APPLY);
      if (btn) btn.style.display = "none";
    });
    // FB-33 M3-5a: со скриптами правки применяются сами — подсказка «erst übernehmen» не нужна
    document.querySelectorAll("[data-window-hint]").forEach(function (p) { p.hidden = true; });
  }

  var saidTimer = 0;

  function draftNote() {
    var n = document.querySelector("[data-schema-draft-note]");
    return n ? n.textContent.replace(/\s+/g, " ").trim() : "";
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
    if (!btn) { lastRefused = true; aufbauError(); return; }  // ревью 2: не перезагружаем молча
    btn.style.display = "";
    // FB-33 M3-2: правка ещё считается «в пути» — без флага её же обработчик отправки
    // ниже проглотил бы эту отправку (Enter в поле), и правка пропала бы молча
    navigating = true;
    // ревью M3-2 (M7): окно закрывали (Esc/×) — после перезагрузки закрыть его снова
    if (closing) intend();
    form.requestSubmit(btn);
    guard();
  }

  function apply(form, target) {
    var data = new FormData(form);
    // у настройки типа страницы своя операция (`op=setting` в скрытом поле формы)
    if (!form.matches("[data-schema-setting]")) data.set("op", "update");
    // Список и переключатель меняют состав полей панели — её перерисовываем целиком;
    // при правке текста панель не трогаем: владелец может уже печатать в соседнем поле.
    var whole = target.tagName === "SELECT" || target.type === "radio";
    var swapped = false;
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
        swapped = true;  // дальше правка записана: сбой отрисовки — не «nicht gespeichert»
        swap(doc, "[data-schema-messages]");
        var refused = !!doc.querySelector('[data-schema-messages] [role="alert"]');
        // ревью M3-2 (H3): отказ сервера «Fertig» по Esc не сжигает перезагрузкой
        lastRefused = refused;
        refusedShown = false;
        if (!refused) clearErrors();
        relay();
        // FB-33 M3-7: правка записана — «Vorschau» окна перерисует кадр
        if (!refused) document.dispatchEvent(new CustomEvent("aufbau:saved"));
        if (refused) whole = true;
        // ревью C3–C4 (a11y): счётчик черновика — в подменяемом узле; новое значение
        // говорит постоянная живая область вместе с «Übernommen.»
        var noteBefore = draftNote();
        swap(doc, "[data-schema-status]");
        var noteNow = draftNote();
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
          dress();
          var el = at ? refocus(at) : null;
          if (at && !el) {
            // У ссылок и кнопок панели нет ни id, ни имени — возвращаемся по месту в панели.
            panel = document.querySelector("[data-schema-panel]");
            var same = panel ? panel.querySelectorAll(FOCUSABLE)[index] : null;
            if (same && same.offsetParent !== null) same.focus({ preventScroll: true });
            else if (panel) panel.focus({ preventScroll: true });
          }
          if (!at && (!document.activeElement || document.activeElement === document.body)) refocus(target);
          // ревью M3-2 (a11y M3): фокус не остаётся на body под открытым окном
          if (win && !win.contains(document.activeElement)) {
            var title = win.querySelector("#schema-panel-title");
            if (title) title.focus({ preventScroll: true });
          }
          if (el && typed !== null && el.value !== typed) {
            el.value = typed;
            el.dispatchEvent(new Event("change", { bubbles: true }));
          }
        } else {
          swap(doc, "#schema-result");
        }
        langNote();
        var live = liveRegion();
        if (refused) {
          // Отказ читает сам role="alert"; на телефоне лист не должен его закрывать.
          clearTimeout(saidTimer);
          if (live) live.textContent = "";
          var box = (win && win.querySelector("[data-bwin-msgs]")) || document.querySelector("[data-schema-messages]");
          if (box) box.scrollIntoView({ block: "start" });
        } else if (live) {
          // Тот же текст подряд диктор не повторяет — сначала очищаем.
          live.textContent = "";
          var said = live.getAttribute("data-done") || "";
          if (noteNow && noteNow !== noteBefore) said = (said + " " + noteNow).trim();
          // ревью e2e: один таймер; живая область — та, что есть к его срабатыванию (окно могли
          // закрыть или подменить)
          clearTimeout(saidTimer);
          saidTimer = setTimeout(function () {
            var now = liveRegion();
            if (now) now.textContent = said;
          }, 100);
        }
      })
      .catch(function (err) {
        // ревью M3-2 (M6): причина — в консоль; ответ уже показан — правка записана, без
        // запасной отправки и без «nicht gespeichert»
        if (window.console) console.error("aufbau: Änderung", err);
        if (!swapped) fallback(form);
      })
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
  var radioFire = null;
  var radioForm = null;  // FB-33 M3-5a: форма отложенного переключателя
  // последний ответ на правку — отказ сервера (его alert виден в окне)
  var lastRefused = false;
  // ревью M3-2 (code-reviewer): отказ уже показан в окне — второй Esc/× подряд закрывает окно
  var refusedShown = false;
  document.addEventListener("change", function (e) {
    var target = e.target;
    var form = panelForm(target);
    if (!form) return;
    if (target.tagName === "SELECT" && byKeys.has(target)) { waiting.add(target); return; }
    if (target.type === "radio") {
      // FB-29 R4: стрелки в группе переключателей шлют change на каждый шаг — отправляем
      // один раз, когда выбор остановился.
      clearTimeout(radioTimer);
      radioForm = form;
      radioFire = function () {
        radioTimer = null;
        radioFire = null;
        radioForm = null;
        // ревью M3-2 (L15): панель за 350 мс подменили — та же кнопка в новой форме
        var now = target.isConnected ? target : refocus(target);
        var into = now ? panelForm(now) : null;
        if (into) apply(into, now);
        else aufbauError();
      };
      radioTimer = setTimeout(radioFire, 350);
      return;
    }
    apply(form, target);
  });

  // Пока правка в пути, «Speichern» и другие действия ждут её — иначе запись могла бы
  // обогнать правку, и та осталась бы в черновике.
  document.addEventListener("submit", function (e) {
    if (e.defaultPrevented || navigating) return;
    var form = e.target;
    var submitter = e.submitter;
    // Enter в поле панели: правка уже в пути (change), вторая отправка не нужна.
    var swallow = pending && form.matches(FORMS) && (!submitter || submitter.value === "update");
    // FB-33 M3-5a: форма уходит целиком (кнопка вкладки без окна) — отложенный переключатель
    // этой формы едет в ней же; своя отправка через 350 мс дала бы второй POST
    if (!swallow && radioTimer && radioForm === form) {
      clearTimeout(radioTimer);
      radioTimer = null;
      radioFire = null;
      radioForm = null;
    }
    if (!pending) return;
    e.preventDefault();
    if (swallow) return;
    if (form.hasAttribute("data-window-actions")) {
      afterPending(form, submitter).then(function (how) {
        if (how === "refused") refusedShown = true;
        if (how === "late" || how === "refused") reopen();
      });
      return;
    }
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
    return Promise.race([chain.then(function () { return "ok"; }), late]).then(function (how) {
      clearTimeout(timer);
      if (how === "late") { aufbauError(form.getAttribute("data-wait-error")); return "late"; }
      // FB-33 M3-2: правка ушла обычной отправкой (запасной путь) — вторая отправка оборвала бы её
      if (navigating) return "skip";
      if (lastRefused && submitter && submitter.value === "window_done") return "refused";
      if (form.isConnected) { form.requestSubmit(submitter && submitter.isConnected ? submitter : undefined); return "sent"; }
      remember(form, submitter);
      aufbauSubmitCopy(form, submitter);
      return "sent";
    });
  }

  /* FB-33 M3-2: модальное окно блока. `<dialog>` создаётся здесь, существующая панель
     [data-schema-panel] переносится в него целиком (подмена панели — `swap()` — окна не
     закрывает), на её месте в сетке — закладка для возврата. Esc и × — то же, что «Fertig»
     (решение владельца): отложенная правка уходит сразу, окно ждёт правку в пути и
     отправляет `window_done`; в подтверждении удаления — его «Abbrechen». Сервер и
     разметка без скриптов прежние. */
  var win = null;
  var mark = null;
  var closing = false;
  var ours = false;
  var NAV_WAIT = 10000;
  var BACK = "aufbauWindowBack";
  var INTENT = "aufbauWindowClose";

  function here() { return new URLSearchParams(location.search).get("seite") || "home"; }

  function stash(key, ref) {
    try {
      sessionStorage.setItem(key, JSON.stringify({ seite: here(), ref: ref, ts: Date.now() }));
    } catch (err) { /* без хранилища — без этого удобства */ }
  }

  function unstash(key) {
    var v = null;
    try {
      v = JSON.parse(sessionStorage.getItem(key) || "null");
      sessionStorage.removeItem(key);
    } catch (err) { v = null; }
    return v && v.seite === here() && Date.now() - v.ts < 30000 ? v : null;
  }

  function panelRef() {
    var ref = win && win.querySelector('[data-schema-panel] input[name="ref"]');
    return ref ? ref.value : new URLSearchParams(location.search).get("block") || "";
  }

  // ревью M3-2 (M7): закрытие сорвалось на запасной отправке правки — закрыть после перезагрузки
  function intend() { stash(INTENT, panelRef()); }

  function clearErrors() {
    if (win) win.querySelectorAll("[data-bwin-error]").forEach(function (n) { n.remove(); });
  }

  // ревью M3-2 (M4): пока «Fertig» уходит — окно занято (читатель экрана слышит «Fertig»)
  function sending(on) {
    if (!win) return;
    if (on) {
      win.setAttribute("aria-busy", "true");
      win.classList.add("ui-bwin-busy");
      var live = liveRegion();
      var b = win.querySelector('[data-schema-panel] button[value="window_done"]');
      if (live && b) { live.textContent = ""; live.textContent = b.textContent.trim(); }
    } else {
      win.removeAttribute("aria-busy");
      win.classList.remove("ui-bwin-busy");
    }
  }

  // закрытие не состоялось — окно снова отвечает на Esc и ×
  function reopen() {
    closing = false;
    sending(false);
  }

  function liveRegion() {
    return (win && win.open && win.querySelector("[data-bwin-status]")) || document.querySelector("[data-schema-live]");
  }

  // Сообщения сервера (отказ, «Nichts zurückzunehmen») при открытом окне — копией внутри окна.
  function relay() {
    var box = win && win.querySelector("[data-bwin-msgs]");
    var src = document.querySelector("[data-schema-messages]");
    if (!box || !src) return;
    box.querySelectorAll("[data-bwin-relayed]").forEach(function (n) { n.remove(); });
    var said = [];
    Array.prototype.forEach.call(src.children, function (m) {
      var p = document.createElement("p");
      var alert = m.getAttribute("role") === "alert";
      // role=alert — только ошибки; прочее читает одна живая область окна
      if (alert) p.setAttribute("role", "alert");
      else if (!langOwn(m.textContent)) said.push(m.textContent.trim());
      p.setAttribute("data-bwin-relayed", "");
      p.className = alert ? "ui-bwin-alert" : "ui-bwin-note";
      p.textContent = m.textContent.trim();
      box.appendChild(p);
    });
    var live = said.length && win.querySelector("[data-bwin-status]");
    if (live) {
      live.textContent = "";
      setTimeout(function () { live.textContent = said.join(" "); }, 100);
    }
  }

  // Новая панель (после подмены) — заголовок принимает фокус программно.
  function dress() {
    if (!win) return;
    var panel = win.querySelector("[data-schema-panel]");
    // ревью M3-2 (H1): новая панель без окна (ни «Fertig», ни подтверждения) — окно закрыть,
    // панель вернуть в сетку
    if (!panel || (!panel.querySelector('button[value="window_done"]') && !panel.querySelector("[data-schema-confirm]"))) {
      closeWindow();
      return;
    }
    // FB-33 M5c-5: панель в окне — схема одной колонкой (правило app.css по флагу; снимает closeWindow)
    var grid = document.querySelector("[data-site-schema]");
    if (grid) grid.setAttribute("data-schema-solo", "");
    // a11y M2: в окне панель — не второй landmark с тем же именем
    if (panel.hasAttribute("aria-labelledby")) {
      panel.setAttribute("data-bwin-lb", panel.getAttribute("aria-labelledby"));
      panel.removeAttribute("aria-labelledby");
    }
    panel.setAttribute("role", "group");
    var h = win.querySelector("#schema-panel-title");
    if (h) h.setAttribute("tabindex", "-1");
    tabs();
    document.dispatchEvent(new CustomEvent("aufbau:panel"));
  }

  /* Вкладки окна по APG (только со скриптами; без них — ссылки `?tab=`): tablist/tab/
     tabpanel, выбранная вкладка в порядке Tab, остальные — стрелками, Home/End; выбор —
     сразу (автоактивация). Адрес помнит вкладку (F5 — та же), формы панели несут её
     скрытым полем `tab` (после правки сервер открывает ту же). */
  function tabLinks() {
    return win ? Array.prototype.slice.call(win.querySelectorAll("[data-window-tabs] [data-window-tab-link]")) : [];
  }

  function tabs() {
    var nav = win && win.querySelector("[data-window-tabs]");
    var list = nav && nav.querySelector("ul");
    if (!list) return;
    list.setAttribute("role", "tablist");
    if (nav.getAttribute("aria-label")) {
      list.setAttribute("aria-label", nav.getAttribute("aria-label"));
      nav.removeAttribute("aria-label");
    }
    nav.setAttribute("role", "none");
    var active = "";
    tabLinks().forEach(function (a) {
      var key = a.getAttribute("data-window-tab-link");
      var panel = document.getElementById("schema-tab-" + key);
      a.parentNode.setAttribute("role", "presentation");
      if (a.tagName === "BUTTON") {
        // FB-33 M3-5a: без скриптов кнопка вкладки отправляет форму вкладки (zu_tab); в окне
        // вкладки переключаются на месте — кнопка ничего не отправляет (type явно, иначе
        // submit по умолчанию), форма и имя — в data-, их вернёт closeWindow
        if (a.hasAttribute("form")) a.setAttribute("data-bw-form", a.getAttribute("form"));
        a.type = "button";
        a.removeAttribute("form");
        a.removeAttribute("name");
        a.removeAttribute("formnovalidate");
        a.removeAttribute("aria-describedby");
      }
      a.setAttribute("role", "tab");
      a.id = "schema-tabbtn-" + key;
      a.removeAttribute("aria-current");
      if (panel) {
        a.setAttribute("aria-controls", panel.id);
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", a.id);
        panel.setAttribute("tabindex", "0");
        if (!panel.hidden && !active) active = key;
      }
    });
    if (active) choose(active, false);
  }

  // FB-33 M3-5a: панель вернулась из окна в сетку — кнопки вкладок снова отправляют форму
  function untab(panel) {
    panel.querySelectorAll("[data-window-tabs] button[data-bw-form]").forEach(function (b) {
      b.type = "submit";
      b.setAttribute("form", b.getAttribute("data-bw-form"));
      b.name = "zu_tab";
      b.setAttribute("formnovalidate", "");
      b.setAttribute("aria-describedby", "bw-nav-apply");
      ["role", "aria-selected", "aria-controls", "tabindex", "id"].forEach(function (k) { b.removeAttribute(k); });
    });
  }

  /* FB-33 M3-5a (a11y): живая область вкладки «Felder» — что сделала кнопка вопроса (точные
     тексты из data-said) и сброшенный перевод (начало текста — data-prefix); в окне общая
     живая область их не повторяет. */
  function felderStatus() {
    var box = document.querySelector("[data-schema-panel] [data-form-status]");
    if (!box) return null;
    var said = (box.getAttribute("data-said") || "").split("|").filter(Boolean);
    return { box: box, said: said, prefix: (box.getAttribute("data-prefix") || "").trim() };
  }

  function langOwn(text) {
    var fs = felderStatus();
    var t = String(text || "").trim();
    return !!(fs && t && (fs.said.indexOf(t) >= 0 || (fs.prefix && t.indexOf(fs.prefix) === 0)));
  }

  function langNote() {
    var fs = felderStatus();
    if (!fs) return;
    var said = [];
    document.querySelectorAll("[data-schema-messages] > *").forEach(function (m) {
      if (m.getAttribute("role") !== "alert" && langOwn(m.textContent)) said.push(m.textContent.trim());
    });
    fs.box.textContent = "";
    if (said.length) setTimeout(function () { fs.box.textContent = said.join(" "); }, 100);
  }

  function choose(key, remember) {
    tabLinks().forEach(function (a) {
      var on = a.getAttribute("data-window-tab-link") === key;
      a.setAttribute("aria-selected", on ? "true" : "false");
      a.setAttribute("tabindex", on ? "0" : "-1");
      var panel = document.getElementById(a.getAttribute("aria-controls") || "");
      if (panel) panel.hidden = !on;
    });
    win.querySelectorAll("[data-schema-panel] form").forEach(function (form) {
      var field = form.querySelector('input[type="hidden"][name="tab"]');
      if (!field) {
        field = document.createElement("input");
        field.type = "hidden";
        field.name = "tab";
        form.appendChild(field);
      }
      field.value = key;
    });
    if (remember && window.history && history.replaceState) {
      var u = new URL(location.href);
      u.searchParams.set("tab", key);  // welche, wopen, ansicht остаются в адресе
      u.hash = "schema-tab-" + key;
      try {
        history.replaceState(history.state, "", u.pathname + u.search + u.hash);
      } catch (err) { /* адрес не обновился — вкладка всё равно выбрана */ }
    }
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest('dialog.ui-bwin [role="tab"]') : null;
    if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    choose(a.getAttribute("data-window-tab-link"), true);
    a.focus();
  });
  document.addEventListener("keydown", function (e) {
    var a = e.target.closest ? e.target.closest('dialog.ui-bwin [role="tab"]') : null;
    if (!a || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var all = tabLinks();
    var i = all.indexOf(a);
    var next = null;
    if (e.key === "ArrowRight") next = all[(i + 1) % all.length];
    else if (e.key === "ArrowLeft") next = all[(i - 1 + all.length) % all.length];
    else if (e.key === "Home") next = all[0];
    else if (e.key === "End") next = all[all.length - 1];
    if (!next) return;
    e.preventDefault();
    choose(next.getAttribute("data-window-tab-link"), true);
    next.focus();
  });

  // Куда вернуть фокус после перезагрузки, которой окно закрывается.
  function remember(form, submitter) {
    var op = submitter && submitter.value;
    if (op !== "window_done" && op !== "revert") return false;
    var ref = form.querySelector('input[name="ref"]');
    if (ref) stash(BACK, ref.value);
    return true;
  }
  document.addEventListener("submit", function (e) {
    // ревью M3-2 (M5): «Fertig»/«Abbrechen» нажаты в окне — Esc и × второго POST не шлют
    if (remember(e.target, e.submitter) && win && win.contains(e.target)) {
      closing = true;
      sending(true);
      if (!pending) guard();  // при правке в пути ждёт afterPending (свой срок)
    }
  }, true);

  // Отправка ушла, а страница всё ещё здесь (сеть оборвала переход) — сказать об этом в
  // окне и снова разрешить закрытие.
  var guardTimer = null;
  function guard() {
    clearTimeout(guardTimer);
    guardTimer = setTimeout(function () {
      navigating = false;
      reopen();
      aufbauError();
    }, NAV_WAIT);
  }
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) { clearTimeout(guardTimer); navigating = false; reopen(); }
  });

  function done() {
    if (!win || closing) return;
    var panel = win.querySelector("[data-schema-panel]");
    var confirmBox = panel && panel.querySelector("[data-schema-confirm]");
    if (confirmBox) {
      // подтверждение удаления: Esc — его «Abbrechen», назад в окно блока
      var cancel = confirmBox.querySelector("a[href]");
      if (cancel) { closing = true; guard(); location.assign(cancel.href); }
      return;
    }
    var form = panel && panel.querySelector("[data-window-actions]");
    var btn = form && form.querySelector('button[value="window_done"]');
    if (!btn) {
      // окна без кнопок (мобильная «Fertig» — та же операция)
      btn = panel && panel.querySelector('button[value="window_done"]');
      form = btn && btn.form;
    }
    if (!btn || !form) {
      // ревью M3-2 (H1): закрывать нечем — ссылка «Fertig» или вернуть панель на место
      var link = panel && panel.querySelector("a[data-schema-done][href]");
      if (link) { closing = true; guard(); location.assign(link.href); return; }
      closeWindow();
      aufbauError();
      return;
    }
    if (lastRefused && refusedShown) { lastRefused = false; refusedShown = false; }
    closing = true;
    // правка поля уходит по change при уходе из него; отложенный переключатель — сейчас
    var at = document.activeElement;
    if (at && panel.contains(at) && typeof at.blur === "function") at.blur();
    if (radioTimer) { clearTimeout(radioTimer); if (radioFire) radioFire(); }
    if (navigating) { intend(); guard(); return; }
    if (pending) {
      afterPending(form, btn).then(function (how) {
        if (how === "refused") refusedShown = true;
        if (how === "late" || how === "refused") reopen();
        else if (how === "sent") guard();
      });
      return;
    }
    // ревью M3-2 (H3): последний ответ — отказ; он виден в окне, перезагрузка его стёрла бы
    if (lastRefused) { refusedShown = true; reopen(); return; }
    form.requestSubmit(btn);
  }

  // FB-33 M5c-3 (ревью M7): окно только что вставленного блока — фокус на первое видимое поле,
  // нет поля — на заголовок окна, нет и его — на «Fertig»
  function firstField() {
    var fields = win.querySelectorAll('[data-schema-panel] :is(input:not([type="hidden"]), select, textarea)');
    return Array.prototype.find.call(fields, function (f) {
      return !f.disabled && f.getClientRects().length > 0 && !f.closest("[hidden],[inert]");
    }) || null;
  }

  function focusIn() {
    if (win.querySelector("[data-schema-inserted]")) {
      var first = firstField() || win.querySelector("#schema-panel-title") ||
        win.querySelector('[data-schema-panel] button[value="window_done"]');
      if (first) {
        first.focus();
        if (document.readyState !== "complete") {
          window.addEventListener("load", function () {
            var at = document.activeElement;
            if (win && at !== first && (!at || at === document.body || at.id === "schema-panel")) first.focus();
          }, { once: true });
        }
        return;
      }
    }
    var hash = location.hash;
    var tab = null;
    if (hash.indexOf("#schema-tab-") === 0) {
      tab = document.getElementById("schema-tabbtn-" + hash.slice(12)) || document.getElementById(hash.slice(1));
    }
    if (tab && !tab.hidden && win.contains(tab)) { tab.focus(); return; }
    var h = win.querySelector("#schema-panel-title");
    if (h) h.focus();
  }

  function openWindow(panel) {
    if (win || !panel || !panel.parentNode) return false;
    var drawer = document.getElementById("sf-drawer");
    try {
      if (drawer && drawer.open && window.sfDrawer) window.sfDrawer.close(true);
    } catch (err) { if (window.console) console.error("aufbau: Schublade", err); }
    win = document.createElement("dialog");
    win.className = "ui-bwin";
    win.setAttribute("aria-modal", "true");
    win.setAttribute("aria-labelledby", "schema-panel-title");
    // × — подпись из разметки панели (sr-only у «Fertig»), новых текстов нет
    var x = document.createElement("button");
    x.type = "button";
    x.className = "ui-bwin-close";
    x.setAttribute("data-bwin-close", "");
    var said = panel.querySelector("[data-schema-done] .sr-only");
    var label = said ? said.textContent.replace(/^[\s\u2013-]+/, "") : "";
    var doneBtn = panel.querySelector('button[value="window_done"]');
    x.setAttribute("aria-label", label || (doneBtn ? doneBtn.textContent.trim() : ""));
    x.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg>';
    x.addEventListener("click", done);
    var msgs = document.createElement("div");
    msgs.className = "ui-bwin-msgs";
    msgs.setAttribute("data-bwin-msgs", "");
    var status = document.createElement("p");
    status.setAttribute("role", "status");
    status.className = "ui-bwin-status";
    status.setAttribute("data-bwin-status", "");
    var headLive = document.querySelector("[data-schema-live]");
    status.setAttribute("data-done", headLive ? headLive.getAttribute("data-done") || "" : "");
    msgs.appendChild(status);
    // FB-33 M5c-3 (a11y B3): после вставки статус — описание окна при открытии (живая область
    // после перезагрузки сама не звучит); `neu` из адреса снимается — F5 не повторяет его
    var inserted = panel.querySelector("[data-schema-inserted]");
    if (inserted) {
      status.id = "schema-bwin-status";
      status.textContent = inserted.textContent.trim();
      win.setAttribute("aria-describedby", status.id);
      try {
        var u = new URL(location.href);
        u.searchParams.delete("neu");
        // и якорь #schema-panel: браузер ставит фокус по нему ПОСЛЕ скрипта (грабля M5b-2)
        history.replaceState(history.state, "", u.pathname + u.search);
      } catch (err) { if (window.console) console.debug("aufbau: Adresse", err); }
    }
    mark = document.createComment("schema-panel");
    panel.parentNode.insertBefore(mark, panel);
    win.appendChild(x);
    win.appendChild(msgs);
    win.appendChild(panel);
    document.body.appendChild(win);
    win.addEventListener("cancel", function (e) {
      e.preventDefault();
      // открытое меню «⋯» Esc закрывает само, окно остаётся
      var more = win.querySelector("details[data-schema-more][open]");
      if (more) {
        more.open = false;
        var s = more.querySelector("summary");
        if (s) s.focus();
        return;
      }
      done();
    });
    var self = win;
    var lastFocus = null;
    self.addEventListener("focusin", function (e) { lastFocus = e.target; });
    self.addEventListener("close", function (e) {
      // ревью C3–C4: окно закрыто скриптом или подменено — схема снова в две колонки
      // ревью e2e: флаг нового окна (уже открытого, пока шло событие) не снимать
      if (e.target === self && !win) unsolo();
      // закрыл не скрипт (CloseWatcher, «назад» на Android) — окно остаётся, как Esc
      if (e.target !== self || ours || win !== self) return;
      try {
        self.showModal();
      } catch (err) {
        closeWindow();
        return;
      }
      if (lastFocus && self.contains(lastFocus)) lastFocus.focus();  // a11y L10
      done();
    });
    document.documentElement.classList.add("ui-bwin-lock");
    try {
      win.showModal();
    } catch (err) {
      // ревью M3-2 (H2): окно не открылось — панель остаётся колонкой, как без скриптов
      if (window.console) console.error("aufbau: Fenster", err);
      closeWindow();
      return false;
    }
    dress();
    if (!win) return false;
    langNote();
    relay();
    focusIn();
    document.dispatchEvent(new CustomEvent("aufbau:window-open"));  // FB-33 M3-7: «Vorschau»
    // ревью M3-2 (M7): перед перезагрузкой окно закрывали — закрываем его теперь (если без ошибки)
    var intent = unstash(INTENT);
    var refusedNow = document.querySelector('[data-schema-messages] [role="alert"]');
    if (intent && intent.ref === panelRef() && !refusedNow) done();
    return true;
  }

  function unsolo() {
    var grid = document.querySelector("[data-site-schema]");
    if (grid) grid.removeAttribute("data-schema-solo");
  }

  function closeWindow() {
    if (!win) return;
    var panel = win.querySelector("[data-schema-panel]");
    ours = true;
    try {
      if (win.open) win.close();
    } finally {
      ours = false;
    }
    if (panel) {
      // a11y M2: в сетке — снова landmark панели
      panel.removeAttribute("role");
      if (panel.hasAttribute("data-bwin-lb")) {
        panel.setAttribute("aria-labelledby", panel.getAttribute("data-bwin-lb"));
        panel.removeAttribute("data-bwin-lb");
      }
    }
    if (panel) untab(panel);
    if (panel && mark && mark.parentNode) mark.parentNode.insertBefore(panel, mark);
    if (mark && mark.parentNode) mark.parentNode.removeChild(mark);
    win.remove();
    win = null;
    unsolo();
    document.dispatchEvent(new CustomEvent("aufbau:window-close"));  // FB-33 M3-7: кадр убрать
    mark = null;
    closing = false;
    lastRefused = false;
    document.documentElement.classList.remove("ui-bwin-lock");
  }

  window.aufbauWindow = { open: openWindow, close: closeWindow };

  hideApply();
  if (aufbauWindowWanted()) openWindow(document.querySelector("[data-schema-panel]"));
  if (!win) { langNote(); unsolo(); }  // окно зовёт langNote само (openWindow)
})();

/* FB-33 M5c-5 (a11y A3): реальная высота липкой полосы черновика (перенос подписи, крупный
   шрифт, safe-area) — в `--schema-draft-h` на <html>: по ней scroll-padding и нижний отступ
   страницы (app.css). Полосу подменяет автосохранение — следим за шапкой. */
(function () {
  "use strict";
  var head = document.querySelector("[data-schema-head]");
  if (!head) return;
  var root = document.documentElement;
  // ревью C3–C4 (a11y, WCAG 1.4.10): полоса с таб-баром выше 35 % экрана (крупный шрифт,
  // 320×568) — в потоке шапки (`data-schema-draft-flow`); таб-бар мерим, а не считаем 5.25rem
  var CAP = 0.35;
  function measure() {
    var bar = head.querySelector("[data-schema-draftbar]");
    root.removeAttribute("data-schema-draft-flow");
    root.style.removeProperty("--schema-draft-h");
    root.style.removeProperty("--schema-draft-at");
    if (!bar || getComputedStyle(bar).position !== "fixed") return;
    var tab = document.querySelector("nav[data-tabbar]");
    var tabBox = tab && tab.getClientRects().length ? tab.getBoundingClientRect() : null;
    var at = tabBox ? Math.max(0, Math.ceil(window.innerHeight - tabBox.top)) : 0;
    var h = Math.ceil(bar.getBoundingClientRect().height);
    if (h + at > window.innerHeight * CAP) {
      root.setAttribute("data-schema-draft-flow", "");
      return;
    }
    root.style.setProperty("--schema-draft-h", h + "px");
    if (tabBox) root.style.setProperty("--schema-draft-at", at + "px");
  }
  // ревью e2e: высота полосы меняется и без resize окна (перенос подписи, шрифт) — следим за
  // самой полосой; её подменяет автосохранение — наблюдатель переезжает на новую
  var ro = window.ResizeObserver ? new ResizeObserver(function () { measure(); }) : null;
  var watched = null;
  function watch() {
    var bar = head.querySelector("[data-schema-draftbar]");
    if (!ro || bar === watched) return;
    if (watched) ro.unobserve(watched);
    watched = bar;
    if (bar) ro.observe(bar);
  }
  measure();
  watch();
  window.addEventListener("resize", measure);
  if (window.MutationObserver) {
    new MutationObserver(function () { measure(); watch(); }).observe(head, { childList: true, subtree: true });
  }
})();

/* FB-33 M5c-2 (a11y A2): после перестановки из «⋯» строки (и броска ⠿) — фокус на «⋯» этой
   строки (у скрытой — на её «Einblenden»: тот же id), через ~300 мс текст «ist jetzt Nummer n»
   в пустую живую область (готовый текст после перезагрузки сам не прозвучит). */
window.aufbauMoved = function (ref, text) {
  // нет «⋯» (строка ушла) — ⚙ строки, нет и её — заголовок схемы (фокус не теряется в body)
  var target = (ref && document.getElementById("schema-more-" + ref)) ||
    (ref && Array.prototype.find.call(document.querySelectorAll("[data-schema-gear]"), function (a) {
      return a.getAttribute("data-schema-gear") === ref;
    })) || document.getElementById("schema-title");
  if (target) {
    if (target.id === "schema-title") target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: false });
  }
  // ревью M5c (silent HIGH): озвучивается только готовый текст сервера — не «Übernommen.»
  // по умолчанию (отказ иначе звучал бы успехом). Ревью e2e: один таймер, живая область —
  // перечитать к срабатыванию
  clearTimeout(window.aufbauMoved.timer);
  var live = document.querySelector("[data-schema-live]");
  if (!live || !text) return;
  live.textContent = "";
  window.aufbauMoved.timer = setTimeout(function () {
    var now = document.querySelector("[data-schema-live]");
    if (now) now.textContent = text;
  }, 300);
};
(function () {
  "use strict";
  var ref = new URLSearchParams(location.search).get("bewegt");
  if (!ref || location.hash !== "#schema-more-" + encodeURIComponent(ref)) return;
  var said = document.querySelector("[data-schema-moved]");
  // браузер ставит фокус по якорю после скрипта — якорь снимаем, фокус ставим сами; и
  // `bewegt` из адреса (F5 не повторяет сообщение, ревью L1)
  try {
    var u = new URL(location.href);
    u.searchParams.delete("bewegt");
    history.replaceState(history.state, "", u.pathname + u.search);
  } catch (err) { if (window.console) console.debug("aufbau: Adresse", err); }
  window.aufbauMoved(ref, said ? said.textContent.trim() : "");
})();

/* FB-33 M5c-2 (a11y B1): «⋯» строк — открыт один; щелчок мимо и уход фокуса закрывают (Esc —
   в шаблоне); «＋ Block» под строкой и в конце — тоже один открытый. */
document.addEventListener("toggle", function (e) {
  var d = e.target;
  if (!d || !d.matches || !d.open) return;
  var group = d.matches("details[data-schema-more]") ? "details[data-schema-more][open]"
    : d.matches("details[data-schema-add]") ? "details[data-schema-add][open]" : "";
  if (!group) return;
  document.querySelectorAll(group).forEach(function (o) { if (o !== d) o.open = false; });
}, true);
document.addEventListener("focusout", function (e) {
  var d = e.target && e.target.closest ? e.target.closest("details[data-schema-more][open]") : null;
  if (d && e.relatedTarget && !d.contains(e.relatedTarget)) d.open = false;
});
document.addEventListener("click", function (e) {
  if (!e.target.closest) return;
  document.querySelectorAll("details[data-schema-more][open]").forEach(function (d) {
    if (!d.contains(e.target)) d.open = false;
  });
});

/* FB-29.5b (макет A): строку схемы можно перетащить мышью — она встаёт перед строкой, на
   которую её бросили, или после неё. Поверх кнопок «Nach oben / Nach unten»: с клавиатуры,
   на телефоне и без скриптов перестановка — ими. */
(function () {
  "use strict";
  if (!window.fetch || !window.DOMParser || !window.FormData) return;
  var dragged = null;

  function item(target) {
    // FB-30.8: свободное место ряда — тоже цель броска; FB-33 M3-6: закреплённая строка (🔒,
    // без ручки) — цель броска «до/после» неё, но сама не перетаскивается
    return target && target.closest ? target.closest("[data-schema-drag],[data-schema-slot],[data-schema-pinned]") : null;
  }

  // FB-33 M5c-2: ⠿ и перетаскивание — только на широком экране (на телефоне — «⋯»); ширину
  // спрашиваем в момент вызова, при сужении окна ручки снимаются. Видимость — только классом.
  var wide = window.matchMedia ? window.matchMedia("(min-width: 48rem)") : null;
  function arm() {
    var on = !wide || wide.matches;
    // ревью e2e: MutationObserver зовёт часто — если все строки уже в нужном состоянии, выход
    if (!document.querySelector(on ? "[data-schema-drag]:not([draggable])" : "[data-schema-drag][draggable]")) return;
    document.querySelectorAll("[data-schema-drag]").forEach(function (li) {
      var grip = li.querySelector(".schema-grip");
      if (on) {
        li.setAttribute("draggable", "true");
        li.style.cursor = "grab";
        if (grip) { grip.classList.remove("hidden"); grip.style.touchAction = "none"; }
      } else {
        li.removeAttribute("draggable");
        li.style.cursor = "";
        if (grip) grip.classList.add("hidden");
      }
    });
  }
  if (wide) {
    if (wide.addEventListener) wide.addEventListener("change", arm);
    else if (wide.addListener) wide.addListener(arm);
  }

  function clear() {
    document.querySelectorAll("[data-schema-drop]").forEach(function (li) {
      li.removeAttribute("data-schema-drop");
      li.style.boxShadow = "";
    });
  }

  function side(li, e) {
    var box = li.getBoundingClientRect();
    // FB-33 M3-6 (ревью): у закреплённой строки, перед которой блок встать не может, — только «после»
    var only = li.getAttribute("data-schema-drop-only");
    // ряд бывает и вертикальным (вид «Telefon», узкий экран) — смотрим на действующую ось
    var inRow = li.parentElement && li.parentElement.children.length > 1 &&
      getComputedStyle(li.parentElement).flexDirection.indexOf("row") === 0;
    var after = only ? only === "after" : inRow ? e.clientX > box.left + box.width / 2 : e.clientY > box.top + box.height / 2;
    return { after: after, inRow: inRow };
  }

  document.addEventListener("dragstart", function (e) {
    var li = item(e.target);
    if (!li || !li.hasAttribute("data-schema-drag")) return;  // место в ряду не перетаскивают
    dragged = li.getAttribute("data-schema-drag");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.clearData();  // ревью a11y: не адрес ссылки ⚙, а ref строки
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
    data.set("zeile", "1");  // FB-33 M5c-2: бросок — действие строки, окно не открывается
    data.set("value", slot ? slot : where + ":" + (li.getAttribute("data-schema-drag") || li.getAttribute("data-schema-pinned")));
    if (new URLSearchParams(location.search).get("ansicht") === "telefon") data.set("ansicht", "telefon");
    fetch(location.pathname, { method: "POST", body: data, credentials: "same-origin" })
      .then(function (resp) {
        if (!resp.ok) throw new Error("status " + resp.status);
        // ревью M5c (silent): ответ ушёл со страницы (вход, другой экран) — это сбой, не успех
        var url = new URL(resp.url || location.href, location.href);
        if (url.pathname !== location.pathname) throw new Error("ответ с " + url.pathname);
        return resp.text().then(function (html) {
          return { html: html, moved: url.searchParams.get("bewegt") === ref };
        });
      })
      .then(function (r) {
        var doc = new DOMParser().parseFromString(r.html, "text/html");
        var swapped = 0;
        ["[data-schema-status]", "[data-schema-messages]", "[data-schema-map]", "[data-schema-panel]"].forEach(function (sel) {
          var now = document.querySelector(sel), next = doc.querySelector(sel);
          if (now && next) { now.replaceWith(document.importNode(next, true)); swapped += 1; }
        });
        if (!swapped) throw new Error("в ответе нет схемы");
        document.querySelectorAll('[data-schema-fields] button[value="update"],[data-schema-list] button[value="update"]').forEach(function (b) { b.style.display = "none"; });
        document.querySelectorAll("[data-window-hint]").forEach(function (p) { p.hidden = true; });
        arm();
        // FB-33 M5c-2 (a11y A2): фокус — на «⋯» перенесённой строки, затем — её новый номер;
        // отказ (в адресе нет `bewegt`) — фокус туда же, слышен отказ сервера (role=alert)
        var said = document.querySelector("[data-schema-moved]");
        if (r.moved) {
          window.aufbauMoved(ref, said ? said.textContent.trim() : "");
        } else {
          window.aufbauMoved(ref, "");
          if (!document.querySelector('[data-schema-messages] [role="alert"]')) aufbauError();
        }
      })
      .catch(function (err) {  // ревью 2: перетаскивание не удалось — видно
        if (window.console) console.error("aufbau: Verschieben", err);
        aufbauError();
      })
      .then(function () { document.documentElement.setAttribute("data-schema-busy", "0"); });
  }
  // после правки из панели схема перерисовывается — перевооружаем строки
  new MutationObserver(arm).observe(document.body, { childList: true, subtree: true });
  arm();
})();
