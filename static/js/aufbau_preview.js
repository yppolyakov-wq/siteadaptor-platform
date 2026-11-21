/* FB-33 M3-7: «Vorschau» в окне блока «Seitenaufbau».
 *
 * Окно (<dialog class="ui-bwin">) строит aufbau.js; этот скрипт добавляет внизу окна область
 * «Vorschau»: кадр черновика страницы (?preview=1&aufbau=<код>), прокрученный к блоку
 * ([data-sf-section="<якорь>"]). Адрес, якорь и тексты — из <template data-bw-preview> экрана
 * (сервер ничего не пишет; без скриптов шаблона нет в срезе эталонов — он после aufbau.js).
 *
 * Кадр — только посмотреть: sandbox без скриптов, форм, всплывающих окон и ухода наверх;
 * ссылки внутри не уводят кадр со страницы; tabindex=-1 — Tab по кадру не ходит, колесо его
 * прокручивает. На компьютере область раскрыта (свёрнутость помнится на вкладку), страница
 * рисуется шириной 1280 и уменьшается; на телефоне область свёрнута, кадр — шириной окна.
 * После каждой записанной правки (aufbau:saved) кадр перерисовывается с паузой — только
 * раскрытый; «aktualisiert» не объявляется (тихо).
 */
(function () {
  "use strict";

  var STORE = "aufbau-preview-closed";
  var PAUSE = 600;
  var PAGE_WIDTH = 1280;
  var AREA_ID = "bw-preview-area";
  var phone = window.matchMedia ? window.matchMedia("(max-width: 767px)") : null;
  // низкий экран (телефон боком): область по умолчанию свёрнута, как на телефоне
  var short = window.matchMedia ? window.matchMedia("(max-height: 520px)") : null;

  var box = null;
  var btn = null;
  var area = null;
  var stage = null;
  var note = null;
  var frame = null;
  var timer = null;
  var stale = false;
  var resizer = null;

  function onPhone() {
    return !!(phone && phone.matches);
  }

  function shortScreen() {
    return !!(short && short.matches);
  }

  // шаблон экрана читается при каждом использовании (не кешируется при загрузке)
  function data(name) {
    var tpl = document.querySelector("template[data-bw-preview]");
    return tpl ? tpl.getAttribute(name) : null;
  }

  function source() {
    var src = data("data-src") || "";
    if (src.charAt(0) !== "/" || src.charAt(1) === "/" || src.indexOf("\\") !== -1) return "";
    return src;
  }

  function rememberedClosed() {
    try {
      return window.sessionStorage.getItem(STORE) === "1";
    } catch (err) {
      return false;
    }
  }

  function remember(closed) {
    try {
      if (closed) window.sessionStorage.setItem(STORE, "1");
      else window.sessionStorage.removeItem(STORE);
    } catch (err) { /* приватное окно — не помним */ }
  }

  function fit() {
    if (!frame || !stage) return;
    var w = stage.clientWidth;
    var h = stage.clientHeight;
    if (!w || !h) return;
    if (onPhone()) {
      // телефон: страница шириной окна — как её увидит посетитель с телефона
      frame.style.width = w + "px";
      frame.style.height = h + "px";
      frame.style.transform = "";
      return;
    }
    var scale = w / PAGE_WIDTH;
    frame.style.width = PAGE_WIDTH + "px";
    frame.style.height = Math.ceil(h / scale) + "px";
    frame.style.transform = "scale(" + scale + ")";
  }

  function target(doc) {
    var anchor = data("data-anchor") || "";
    if (!anchor || !window.CSS || !CSS.escape) return null;
    var found = doc.querySelectorAll('[data-sf-section="' + CSS.escape(anchor) + '"]');
    for (var i = 0; i < found.length; i += 1) {
      var el = found[i];
      if (el.getClientRects().length) return el;
      // обёртка display:contents (hero, плитки) — своего прямоугольника нет, берём потомка
      var inner = el.querySelectorAll("*");
      for (var j = 0; j < inner.length; j += 1) {
        if (inner[j].getClientRects().length) return inner[j];
      }
    }
    return null;
  }

  function showBlock() {
    var doc = null;
    try {
      doc = frame && frame.contentDocument;
    } catch (err) {
      doc = null;
    }
    if (!doc || !doc.body) return;
    // ссылки кадра не уводят его со страницы (кабинет в кадре не показывается — DENY)
    doc.addEventListener("click", function (e) {
      var link = e.target && e.target.closest ? e.target.closest("a[href]") : null;
      if (link) e.preventDefault();
    }, true);
    var el = target(doc);
    var whole = data("data-page") !== null || !data("data-anchor");
    note.hidden = !!el || whole;
    var view = frame.contentWindow;
    if (!view) return;
    if (!el) { view.scrollTo({ top: 0, left: 0, behavior: "instant" }); return; }
    var top = el.getBoundingClientRect().top + view.pageYOffset;
    // липкая шапка витрины не закрывает начало блока
    var head = doc.querySelector('[data-sf-section="header"]');
    var pos = head ? view.getComputedStyle(head).position : "";
    var cover = pos === "sticky" || pos === "fixed" ? head.getBoundingClientRect().height : 0;
    view.scrollTo({ top: Math.max(0, top - cover - 16), left: 0, behavior: "instant" });
  }

  function load() {
    var src = source();
    if (!src) return;
    stale = false;
    if (!frame) {
      frame = document.createElement("iframe");
      frame.className = "ui-bwin-pv-frame";
      // только посмотреть: без скриптов, форм, всплывающих окон и ухода наверх
      frame.setAttribute("sandbox", "allow-same-origin");
      frame.setAttribute("referrerpolicy", "same-origin");
      frame.tabIndex = -1;
      frame.addEventListener("load", showBlock);
      stage.appendChild(frame);
      fit();
    }
    frame.setAttribute("src", src);
  }

  function expanded() {
    return !!btn && btn.getAttribute("aria-expanded") === "true";
  }

  function setOpen(open) {
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    area.hidden = !open;
    if (open && (!frame || stale)) load();
    else if (open) fit();
  }

  function toggle() {
    var open = !expanded();
    setOpen(open);
    if (!onPhone()) remember(!open);
  }

  function build() {
    var win = document.querySelector("dialog.ui-bwin[open]");
    if (box || !win || !source()) return;
    box = document.createElement("section");
    box.className = "ui-bwin-pv";
    box.setAttribute("data-bwin-preview", "");
    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ui-bwin-pv-toggle";
    btn.setAttribute("aria-controls", AREA_ID);
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 6l6 6-6 6"></path></svg>';
    var label = document.createElement("span");
    label.textContent = data("data-label") || "";
    btn.appendChild(label);
    btn.addEventListener("click", toggle);
    area = document.createElement("div");
    area.id = AREA_ID;
    area.className = "ui-bwin-pv-area";
    note = document.createElement("p");
    note.className = "ui-bwin-pv-missing";
    note.textContent = data("data-missing") || "";
    note.hidden = true;
    stage = document.createElement("div");
    stage.className = "ui-bwin-pv-stage";
    // картинка для глаз: читатель экрана слышит саму панель, кадр ему не нужен (a11y-ревью)
    stage.setAttribute("aria-hidden", "true");
    area.appendChild(note);
    area.appendChild(stage);
    box.appendChild(btn);
    box.appendChild(area);
    win.appendChild(box);
    if (window.ResizeObserver) {
      resizer = new ResizeObserver(fit);
      resizer.observe(stage);
    }
    setOpen(!onPhone() && !shortScreen() && !rememberedClosed());
  }

  function teardown() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (resizer) { resizer.disconnect(); resizer = null; }
    if (box && box.parentNode) box.parentNode.removeChild(box);
    box = btn = area = stage = note = frame = null;
    stale = false;
  }

  document.addEventListener("aufbau:window-open", build);
  document.addEventListener("aufbau:window-close", teardown);
  document.addEventListener("aufbau:saved", function () {
    if (!box) return;
    stale = true;
    if (!expanded()) return;  // свёрнутая область перерисуется при раскрытии
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { timer = null; if (expanded()) load(); }, PAUSE);
  });
  if (phone) {
    var follow = function () {
      if (!btn) return;
      if (onPhone()) setOpen(false);
      else fit();
    };
    if (phone.addEventListener) phone.addEventListener("change", follow);
    else if (phone.addListener) phone.addListener(follow);
  }
  // клик в кадр уводит фокус в него (окно теряет фокус) — возвращаем на кнопку «Vorschau»:
  // Esc и Tab снова работают в окне, колесо кадр крутит и без фокуса
  window.addEventListener("blur", function () {
    setTimeout(function () {
      if (frame && btn && document.activeElement === frame) btn.focus({ preventScroll: true });
    }, 0);
  });
  // aufbau.js (defer, раньше этого скрипта) мог уже открыть окно
  build();
})();
