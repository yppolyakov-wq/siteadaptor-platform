/* KA-12 E10.6: общий JS хрома кабинета. Каждый бывший <script> — в своём try/catch: ошибка
   одного блока не останавливает остальные (как было с отдельными тегами; ревью 661dbfed).
   Раньше всё это было инлайн в tenant/_base_dashboard.html
   и партиалах core/_*). Один кэшируемый файл; подключается в конце body. */
// ---- tenant/_base_dashboard.html ----
// M22b realtime: живой бейдж непрочитанных сообщений в навигации.
try { (function () {
  // X0: бейджей теперь может быть несколько (якорь Marketing + подпункт
  // «Nachrichten») — один fetch обновляет все.
  var badges = document.querySelectorAll("[data-inbox-badge]");
  if (!badges.length) return;
  function refresh() {
    fetch(badges[0].getAttribute("data-url"), { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        badges.forEach(function (badge) {
          if (d.count > 0) { badge.textContent = d.count; badge.classList.remove("hidden"); }
          else { badge.classList.add("hidden"); }
        });
      }).catch(function () {});
  }
  refresh();
  // KA-12 E10: в скрытой вкладке не опрашиваем — догоняем при возврате на неё.
  setInterval(function () { if (!document.hidden) refresh(); }, 20000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
})(); } catch (e) { console.error(e); }
try { (function () {
  var sb = document.getElementById("sidebar");
  var ov = document.getElementById("sidebar-overlay");
  // KA-12 E9.4a (WCAG 2.1.2/2.4.3): мобильное меню ведёт себя как диалог — фокус внутрь
  // при открытии, Tab не уходит за затемнение, Esc закрывает, фокус возвращается на
  // кнопку; закрытое мобильное меню — inert (его ссылки не в Tab-порядке). На md+ меню
  // всегда на экране и всегда доступно.
  var mq = window.matchMedia("(max-width: 767.98px)");
  var sbOpener = null, sbIsOpen = false;
  var sbOpeners = [document.getElementById("sidebar-open"), document.getElementById("tabbar-menu")];
  function sbFocusables() {
    return Array.prototype.filter.call(
      sb.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled])'),
      function (el) { return el.offsetParent !== null; });
  }
  // Ревью a11y E9.4a: Tab-ловушки мало — виртуальный курсор диктора уходил за затемнение.
  // Пока мобильное меню открыто, всё, что за ним (колонка страницы, таб-бар, «к содержимому»),
  // — inert; навигационный landmark у <aside> сохраняется (role=dialog его бы стёр).
  var sbBehind = [document.getElementById("cab-col"), document.querySelector("[data-tabbar]"),
                  document.getElementById("skip-main")];
  function sbSync() {
    var modal = mq.matches && sbIsOpen;
    sb.inert = mq.matches && !sbIsOpen;
    sbBehind.forEach(function (el) { if (el) el.inert = modal; });
    sbOpeners.forEach(function (b) { if (b) b.setAttribute("aria-expanded", sbIsOpen ? "true" : "false"); });
  }
  function open(e) {
    sbOpener = (e && e.currentTarget) || document.activeElement;
    sbIsOpen = true;
    sb.classList.remove("-translate-x-full"); ov.classList.remove("hidden");
    sbSync();
    var f = sbFocusables()[0]; if (f) f.focus();
  }
  function close(noFocus) {
    if (!sbIsOpen) return;
    sbIsOpen = false;
    sb.classList.add("-translate-x-full"); ov.classList.add("hidden");
    sbSync();
    if (noFocus !== true && sbOpener && sbOpener.focus) sbOpener.focus();
  }
  // На document, а не на <aside>: клик по пустому месту меню уводит фокус в body —
  // Esc и Tab должны работать и тогда (ревью a11y E9.4a).
  document.addEventListener("keydown", function (e) {
    if (!sbIsOpen || !mq.matches) return;
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key !== "Tab") return;
    var f = sbFocusables(); if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (!sb.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  // Поворот/ресайз за 768px: меню на десктопе не модальное — закрываем «открытое» состояние,
  // иначе при возврате на мобильный оно оставалось бы открытым с устаревшим aria-expanded.
  if (mq.addEventListener) mq.addEventListener("change", function () {
    if (!mq.matches && sbIsOpen) close(true); else sbSync();
  });
  sbSync();
  var so = document.getElementById("sidebar-open");  // T-8.30: в Mini App шапки нет
  if (so) so.addEventListener("click", open);
  document.getElementById("sidebar-close").addEventListener("click", close);
  ov.addEventListener("click", close);
  // SH-17: одна кнопка-тумблер — свернуть в полосу иконок / развернуть обратно.
  document.getElementById("sidebar-collapse").addEventListener("click", function () {
    var min = document.body.classList.toggle("sb-min");
    localStorage.setItem("sb_min", min ? "1" : "0");
  });
  var tb = document.getElementById("tabbar-menu");
  if (tb) tb.addEventListener("click", open);

  // R7-1: раздел сайдбара — тумблер подменю (клик по самой строке раздела).
  // В свёрнутой полосе (sb-min) подменю скрыто CSS, поэтому клик по иконке
  // СНАЧАЛА разворачивает сайдбар — иначе жест был бы «мёртвым».
  function setSection(key, openIt) {
    var box = document.querySelector('[data-nav-children="' + key + '"]');
    var btn = document.querySelector('[data-nav-toggle="' + key + '"]');
    if (!box || !btn) return;
    box.classList.toggle("hidden", !openIt);
    btn.setAttribute("aria-expanded", openIt ? "true" : "false");
    var ch = btn.querySelector("[data-nav-chevron]");
    if (ch) ch.classList.toggle("rotate-90", openIt);
  }
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-nav-toggle]");
    if (btn) {
      var key = btn.getAttribute("data-nav-toggle");
      if (document.body.classList.contains("sb-min")) {
        document.body.classList.remove("sb-min");
        localStorage.setItem("sb_min", "0");
        setSection(key, true);
        return;
      }
      var box = document.querySelector('[data-nav-children="' + key + '"]');
      setSection(key, box ? box.classList.contains("hidden") : true);
      return;
    }
    // Мобильный таб-бар: раздел с подменю выезжает сайдбаром с раскрытым разделом.
    var tab = ev.target.closest("[data-tabbar-section]");
    if (tab) {
      setSection(tab.getAttribute("data-tabbar-section"), true);
      open();
    }
  });

  // Быстрый фильтр пунктов меню (нативный поиск по разделам).
  var filter = document.getElementById("nav-filter");
  if (filter) {
    var empty = document.getElementById("nav-empty");
    filter.addEventListener("input", function () {
      var q = filter.value.trim().toLowerCase();
      var anyShown = false;
      // W7b/W-CL: плоские .nav-link компакт-сайдбара — фильтруем напрямую.
      document.querySelectorAll("#dash-nav .nav-link").forEach(function (a) {
        var hit = !q || (a.getAttribute("data-label") || "").toLowerCase().indexOf(q) > -1;
        a.classList.toggle("hidden", !hit);
        if (hit) anyShown = true;
      });
      // SM-4: при поиске раскрываем блоки с совпавшими подпунктами (иначе
      // найденный пункт остался бы внутри свёрнутого слайдера); пустой запрос
      // возвращает свёртку по shown-состоянию активного раздела.
      document.querySelectorAll("#dash-nav [data-nav-children]").forEach(function (box) {
        var key = box.getAttribute("data-nav-children");
        var btn = document.querySelector('[data-nav-toggle="' + key + '"]');
        if (q) {
          var hasHit = !!box.querySelector(".nav-link:not(.hidden)");
          box.classList.toggle("hidden", !hasHit);
        } else {
          var active = btn && btn.getAttribute("aria-expanded") === "true";
          box.classList.toggle("hidden", !active);
        }
      });
      // KA-12 E8.4: подзаголовок группы прячем, если под ним не осталось пунктов.
      document.querySelectorAll("#dash-nav [data-nav-subhead]").forEach(function (h) {
        var next = h.nextElementSibling, hasLink = false;
        while (next && !next.hasAttribute("data-nav-subhead")) {
          if (next.classList.contains("nav-link") && !next.classList.contains("hidden")) hasLink = true;
          next = next.nextElementSibling;
        }
        h.classList.toggle("hidden", !!q && !hasLink);
      });
      if (empty) empty.classList.toggle("hidden", anyShown);
    });
  }

  // W8-4: палитра Ctrl/Cmd+K — прыжок в раздел/настройку.
  var pal = document.getElementById("navpal");
  var palQ = document.getElementById("navpal-q");
  var palOpener = null;
  function palOpen() {
    if (!pal) return;
    palOpener = document.activeElement;
    pal.classList.remove("hidden");
    if (palQ) { palQ.value = ""; palFilter(); palRenderData([]); palQ.focus(); }
  }
  function palClose() {
    if (!pal || pal.classList.contains("hidden")) return;
    pal.classList.add("hidden");
    if (palOpener && palOpener.focus) palOpener.focus();
  }
  // KA-12 E9.4a (WCAG 4.1.3): число найденного объявляется живой областью.
  var palStatus = document.getElementById("navpal-status");
  function palVisibleLinks() {
    var out = [];
    if (palData && !palData.classList.contains("hidden")) out = out.concat(Array.prototype.slice.call(palData.querySelectorAll("a")));
    return out.concat(Array.prototype.slice.call(pal.querySelectorAll(".navpal-item:not(.hidden)")));
  }
  function palAnnounce() {
    if (!palStatus) return;
    var n = palVisibleLinks().length;
    palStatus.textContent = n ? (palStatus.getAttribute("data-many") || "").replace("{n}", n)
                              : (palStatus.getAttribute("data-none") || "");
  }
  function palFilter() {
    var q = (palQ && palQ.value || "").trim().toLowerCase();
    var any = false;
    pal.querySelectorAll(".navpal-item").forEach(function (a) {
      var hit = !q || (a.getAttribute("data-pal") || "").indexOf(q) > -1;
      a.classList.toggle("hidden", !hit);
      if (hit) any = true;
    });
    palSyncEmpty(any);
    if (!q && palStatus) palStatus.textContent = "";
  }
  // Ревью 2026-08-19: «Nothing found.» считалось ТОЛЬКО по пунктам меню, а
  // строки данных (X8) в счёт не шли — при находке «заказ фрау Мюллер» палитра
  // одновременно показывала результат и надпись «ничего не найдено».
  function palMenuHit() {
    return !!pal.querySelector(".navpal-item:not(.hidden)");
  }
  function palSyncEmpty(menuHit) {
    var pe = document.getElementById("navpal-empty");
    if (!pe) return;
    var dataHit = !!(palData && !palData.classList.contains("hidden") && palData.querySelector("a"));
    pe.classList.toggle("hidden", (menuHit === undefined ? palMenuHit() : menuHit) || dataHit);
  }
  // X8: поиск по ДАННЫМ — секция «Gefunden» над пунктами меню. Debounce 250 мс,
  // предыдущий запрос отменяется; сеть упала → остаётся навигационный поиск.
  var palData = document.getElementById("navpal-data");
  var palTimer = null, palAbort = null;
  function palEsc(t) { var d = document.createElement("div"); d.textContent = t == null ? "" : t; return d.innerHTML; }
  function palRenderData(sections) {
    if (!palData) return;
    if (!sections || !sections.length) {
      palData.classList.add("hidden"); palData.innerHTML = ""; palSyncEmpty(); return;
    }
    var html = "";
    sections.forEach(function (sec) {
      html += '<p class="px-4 pt-2 pb-1 text-[11px] uppercase tracking-wide text-gray-400">' + palEsc(sec.label) + "</p>";
      sec.items.forEach(function (it) {
        // the server sends ready, already-encoded local paths; encodeURI() on top
        // double-encoded "%" (STU-19g: «€» in a helper link arrived as "%E2%82%AC")
        var u = String(it.url || "");
        if (u.charAt(0) !== "/" || u.charAt(1) === "/" || u.charAt(1) === "\\") return;
        html += '<a href="' + palEsc(u).replace(/"/g, "&quot;") + '" class="flex items-center justify-between gap-3 px-4 py-2 text-sm hover:bg-indigo-50 focus-visible:bg-indigo-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500">' +
                '<span class="truncate">' + palEsc(it.label) + "</span>" +
                '<span class="text-xs text-gray-400 shrink-0 truncate">' + palEsc(it.sub) + "</span></a>";
      });
    });
    palData.innerHTML = html;
    palData.classList.remove("hidden");
    palSyncEmpty();
  }
  function palSearchData() {
    if (!palData) return;
    var q = (palQ && palQ.value || "").trim();
    if (palTimer) clearTimeout(palTimer);
    // Ревью a11y E9.4a: число объявляется ОДИН раз — когда поиск по данным завершился
    // (или для коротких запросов — сразу), а не на каждую клавишу.
    if (q.length < 2) { palRenderData([]); if (q) palAnnounce(); return; }
    palTimer = setTimeout(function () {
      if (palAbort) palAbort.abort();
      palAbort = ("AbortController" in window) ? new AbortController() : null;
      fetch(palData.getAttribute("data-url") + "?q=" + encodeURIComponent(q),
            palAbort ? { signal: palAbort.signal } : undefined)
        .then(function (r) { return r.ok ? r.json() : { sections: [] }; })
        .then(function (d) { palRenderData(d.sections); palAnnounce(); })
        .catch(function (err) {
          // сеть упала — навигационный поиск остаётся и объявляется; отмену (новый ввод) молчим
          if (!err || err.name !== "AbortError") palAnnounce();
        });
    }, 250);
  }
  var palBtn = document.getElementById("navpal-open");
  if (palBtn) palBtn.addEventListener("click", palOpen);
  if (pal) {
    pal.addEventListener("click", function (e) { if (e.target === pal) palClose(); });
    if (palQ) {
      palQ.addEventListener("input", function () { palFilter(); palSearchData(); });
      palQ.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          // Ревью 2026-08-19: Enter брал только пункты меню — найденная сделка
          // по нему не открывалась вовсе. Данные показаны первыми → они и цель.
          var first = (palData && !palData.classList.contains("hidden") && palData.querySelector("a"))
                   || pal.querySelector(".navpal-item:not(.hidden)");
          if (first) window.location.href = first.getAttribute("href");
        }
      });
    }
    // KA-12 E9.4a (WCAG 2.1.1/2.1.2): ↑/↓ по найденному, Tab по кругу внутри диалога.
    pal.addEventListener("keydown", function (e) {
      if (pal.classList.contains("hidden")) return;
      var links = palVisibleLinks();
      var all = [palQ].concat(links);
      var i = all.indexOf(document.activeElement);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!links.length) return;
        e.preventDefault();
        var step = e.key === "ArrowDown" ? 1 : -1;
        all[(i + step + all.length) % all.length].focus();
      } else if (e.key === "Tab") {
        e.preventDefault();
        all[(i + (e.shiftKey ? -1 : 1) + all.length) % all.length].focus();
      }
    });
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); palOpen(); }
      else if (e.key === "Escape" && !pal.classList.contains("hidden")) palClose();
    });
  }
})(); } catch (e) { console.error(e); }
// ---- core/_confirm_tap.html ----
try { (function () {
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-confirm-tap]");
    if (!btn) return;
    if (btn.hasAttribute("data-confirm-armed")) return;
    e.preventDefault();
    e.stopPropagation();
    btn.setAttribute("data-confirm-armed", "");
    btn.dataset.confirmLabel = btn.textContent;
    btn.textContent = btn.getAttribute("data-confirm-tap");
    setTimeout(function () {
      if (!btn.isConnected || !btn.hasAttribute("data-confirm-armed")) return;
      btn.removeAttribute("data-confirm-armed");
      btn.textContent = btn.dataset.confirmLabel;
    }, 4000);
  }, true);
})(); } catch (e) { console.error(e); }
// ---- core/_danger_confirm.html ----
try { (function () {
  "use strict";
  if (window.sfDangerConfirm) return;
  var dlg = document.getElementById("danger-confirm");
  var pending = null;

  function finish(ok) {
    if (dlg && dlg.open) dlg.close();
    var cb = pending;
    pending = null;
    if (cb) cb(ok);
  }

  // opts {title, desc, yes, no} — свой текст для неденежных вопросов (UX-D D1.3:
  // «Eingaben verwerfen?» не должно звучать как «Ja, ausführen»); по умолчанию — прежний.
  var defaults = dlg ? {
    title: dlg.querySelector("#danger-confirm-title").textContent,
    desc: dlg.querySelector("#danger-confirm-desc").innerHTML,
    yes: dlg.querySelector("[data-danger-yes]").textContent,
    no: dlg.querySelector("[data-danger-no]").textContent
  } : null;
  window.sfDangerConfirm = function (label, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      if (!dlg || typeof dlg.showModal !== "function") {
        resolve(window.confirm(opts.title || label));
        return;
      }
      pending = resolve;
      var desc = dlg.querySelector("#danger-confirm-desc");
      desc.innerHTML = defaults.desc;
      dlg.querySelector("#danger-confirm-title").textContent = opts.title || defaults.title;
      dlg.querySelector("[data-danger-yes]").textContent = opts.yes || defaults.yes;
      dlg.querySelector("[data-danger-no]").textContent = opts.no || defaults.no;
      if (opts.desc) desc.textContent = opts.desc;
      else dlg.querySelector("[data-danger-label]").textContent = label || "";
      dlg.showModal();
      dlg.querySelector("[data-danger-no]").focus();  // безопасный выбор — по умолчанию
    });
  };

  if (dlg) {
    dlg.querySelector("[data-danger-yes]").addEventListener("click", function () { finish(true); });
    dlg.querySelector("[data-danger-no]").addEventListener("click", function () { finish(false); });
    dlg.addEventListener("cancel", function () { finish(false); });
  }

  document.addEventListener("submit", function (e) {
    var form = e.target;
    var btn = e.submitter;
    if (!btn || btn.getAttribute("data-danger") !== "1") return;
    if (form.dataset.dangerConfirmed === "1") {
      delete form.dataset.dangerConfirmed;
      return;
    }
    e.preventDefault();
    e.stopImmediatePropagation();
    window.sfDangerConfirm(btn.textContent.trim()).then(function (ok) {
      if (!ok) return;
      form.dataset.dangerConfirmed = "1";
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(btn);
        // submit-событие идёт синхронно; если браузер его не дал (невалидное поле) —
        // флаг не должен пропустить следующий опасный клик без подтверждения
        delete form.dataset.dangerConfirmed;
      } else {
        var keep = document.createElement("input");
        keep.type = "hidden";
        keep.name = btn.name;
        keep.value = btn.value;
        form.appendChild(keep);
        form.submit();
      }
    });
  }, true);
})(); } catch (e) { console.error(e); }
// ---- core/_drawer.html ----
// UX-D D1: шторка кабинета (контракт — docs/references/patterns/drawer.md).
// a[data-drawer] → GET с заголовком X-Sf-Drawer (+ ?box=1) → вставляется ТОЛЬКО ответ с
// меткой X-Sf-Fragment; формы [data-drawer-form] → POST с X-Sf-Drawer → JSON
// (apps/core/drawer.drawer_aware) или фрагмент с ошибками формы. Редиректы не
// следуются (redirect: "manual"): истёкшая сессия = обычный переход, а не вход в шторке.
// Любой сбой → обычная навигация (ссылка/форма работают и без JS).
try { (function () {
  "use strict";
  if (window.sfDrawer) return;
  var dlg = document.getElementById("sf-drawer");
  if (!dlg || typeof dlg.showModal !== "function") return;
  var body = dlg.querySelector("[data-drawer-body]");
  var flash = dlg.querySelector("[data-drawer-flash]");
  var alertBox = dlg.querySelector("[data-drawer-alert]");
  var heading = dlg.querySelector("[data-drawer-heading]");
  var errText = dlg.getAttribute("data-drawer-error") || "Error";
  var unclearText = dlg.getAttribute("data-drawer-unclear") || errText;
  var fallbackTitle = dlg.getAttribute("data-drawer-fallback-title") || "";
  var DRAWER_PARAMS = ["box", "drawer", "buchung"];
  var src = null;        // адрес текущего фрагмента
  var pagePath = null;   // путь объекта (для ?drawer= и истории)
  var pushed = false;    // мы добавили запись в историю
  var opener = null;
  var openerKey = null;
  var seq = 0;
  var refreshSeq = 0;
  var downOnBackdrop = false;
  var busy = false;           // одна отправка из шторки за раз (деньги: оплата + отмена)
  var afterClose = [];        // сообщения для тоста после закрытия (под модальным окном не видны)
  var pendingSay = [];        // сообщения фрагмента до showModal (скрытый диалог их бы потерял)
  var CARRY = "sfDrawerCarry";
  var dirty = false;          // в форме шторки есть несохранённый ввод
  var discardText = dlg.getAttribute("data-drawer-discard") || "";

  function pageUrl() {
    var u = new URL(location.href);
    DRAWER_PARAMS.forEach(function (k) { u.searchParams.delete(k); });
    return u.pathname + u.search;
  }

  // Безопасность (ревью D1): только страницы кабинета этого сайта.
  function cabinetUrl(href) {
    try {
      var u = new URL(href, location.href);
      if (u.origin !== location.origin) return null;
      if (!/^\/(dashboard|promotions|crm|catalog|imports|finance|inventory)\//.test(u.pathname)) return null;
      return u;
    } catch (e) { return null; }
  }

  function fragmentUrl(u) {
    var f = new URL(u.pathname + u.search, location.href);
    f.searchParams.set("box", "1");
    if (!f.searchParams.has("next")) f.searchParams.set("next", pageUrl());
    return f.pathname + f.search;
  }

  // Живая область тоста создаётся ПУСТОЙ заранее: область, рождённая вместе с текстом,
  // читалками часто не объявляется (ECC a11y-ревью D1).
  var toastBox = document.getElementById("sf-toast");
  if (!toastBox) {
    toastBox = document.createElement("div");
    toastBox.id = "sf-toast";
    toastBox.setAttribute("role", "status");
    toastBox.className = "fixed bottom-24 md:bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2";
    document.body.appendChild(toastBox);
  }

  function toast(items) {
    if (dlg.open) { afterClose = afterClose.concat(items || []); return; }  // покажем после закрытия
    requestAnimationFrame(function () {
      (items || []).forEach(function (m) {
        var p = document.createElement("p");
        var tone = m.level === "error" ? "bg-red-700 text-white" : (m.level === "warning" ? "bg-amber-100 text-amber-950 ring-1 ring-amber-300" : "bg-gray-900 text-white");
        p.className = "rounded-xl px-4 py-2 text-sm shadow-lg " + tone;
        p.textContent = m.text;
        toastBox.appendChild(p);
        setTimeout(function () { p.remove(); }, m.level === "success" || m.level === "info" ? 6000 : 12000);
      });
    });
  }

  // Сообщения, которые должны пережить перезагрузку страницы (область не обновилась).
  function carry(items) {
    try { if (items && items.length) sessionStorage.setItem(CARRY, JSON.stringify(items)); } catch (e) { /* приватный режим */ }
  }
  try {
    var carried = JSON.parse(sessionStorage.getItem(CARRY) || "[]");
    sessionStorage.removeItem(CARRY);
    if (carried.length) toast(carried);
  } catch (e) { /* нет sessionStorage */ }

  function say(items) {
    flash.textContent = "";
    alertBox.textContent = "";
    // успех/предупреждение — polite, ошибка — assertive; текст в следующем кадре:
    // синхронную замену «очистить и вставить то же» читалки пропускают.
    requestAnimationFrame(function () {
      (items || []).forEach(function (m) {
        var err = m.level === "error";
        var p = document.createElement("p");
        p.className = "rounded-xl px-3 py-2 " + (err ? "bg-red-50 text-red-800" : (m.level === "warning" ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-900"));
        var g = document.createElement("span");
        g.setAttribute("aria-hidden", "true");
        g.textContent = err ? "⚠ " : (m.level === "warning" ? "! " : "✓ ");
        p.appendChild(g);
        p.appendChild(document.createTextNode(m.text));
        (err ? alertBox : flash).appendChild(p);
      });
    });
  }

  function headerMessages(r) {
    try { return JSON.parse(r.headers.get("X-Sf-Messages") || "[]"); } catch (e) { return []; }
  }

  // Высота липкого подвала → отступ прокрутки тела: фокус не прячется под кнопками
  // (WCAG 2.4.11; на телефоне кнопки статуса переносятся в 2–3 ряда).
  var footObserver = window.ResizeObserver ? new ResizeObserver(function (entries) {
    entries.forEach(function (en) { body.style.setProperty("--drawer-foot-h", Math.ceil(en.target.getBoundingClientRect().height) + "px"); });
  }) : null;
  function watchFoot() {
    if (!footObserver) return;
    footObserver.disconnect();
    var foot = body.querySelector(".ui-drawer-foot");
    if (foot) footObserver.observe(foot); else body.style.removeProperty("--drawer-foot-h");
  }

  function fill(html, keep) {
    // перезагрузка после действия: раскрытые <details> и прокрутка остаются
    var opened = keep ? Array.prototype.map.call(body.querySelectorAll("details[open]"), function (d) {
      var s = d.querySelector("summary"); return s ? s.textContent.trim() : "";
    }) : [];
    var top = keep ? body.scrollTop : 0;
    body.innerHTML = html;
    dirty = false;
    if (opened.length) {
      Array.prototype.forEach.call(body.querySelectorAll("details"), function (d) {
        var s = d.querySelector("summary");
        if (s && opened.indexOf(s.textContent.trim()) !== -1) d.open = true;
      });
    }
    body.scrollTop = top;
    watchFoot();
    var t = body.querySelector("[data-drawer-title]");
    heading.textContent = (t && t.getAttribute("data-drawer-title")) || fallbackTitle;
    document.dispatchEvent(new CustomEvent("sf:drawer-loaded", { detail: { body: body } }));
  }

  // GET фрагмента. Результат: "ok" | "gone" (404 — объекта больше нет) | "away" (не
  // фрагмент: сессия истекла, нет прав, пакет — нужна обычная навигация) | "stale".
  function load(url, keep) {
    var mine = ++seq;
    body.setAttribute("aria-busy", "true");
    return fetch(url, { credentials: "same-origin", redirect: "manual", headers: { "X-Sf-Drawer": "1" } })
      .then(function (r) {
        if (mine !== seq) return "stale";
        body.removeAttribute("aria-busy");
        if (r.status === 404) return "gone";
        if (r.type === "opaqueredirect" || !r.ok || r.headers.get("X-Sf-Fragment") !== "1") return "away";
        return r.text().then(function (html) {
          if (mine !== seq) return "stale";
          fill(html, keep);
          var m = headerMessages(r);
          if (dlg.open) { if (m.length) say(m); } else pendingSay = m;
          return "ok";
        });
      }, function (err) {
        body.removeAttribute("aria-busy");
        throw err;
      });
  }

  function setUrlParam(path, push) {
    var u = new URL(location.href);
    if (path) u.searchParams.set("drawer", path); else u.searchParams.delete("drawer");
    u.searchParams.delete("buchung");
    var state = { sfDrawer: path || null };
    if (push) history.pushState(state, "", u.pathname + u.search + u.hash);
    else history.replaceState(state, "", u.pathname + u.search + u.hash);
  }

  function open(href, trigger, opts) {
    opts = opts || {};
    var u = cabinetUrl(href);
    if (!u) return Promise.resolve(false);
    var url = fragmentUrl(u);
    if (!dlg.open) {  // ссылка внутри шторки не перезаписывает того, кто её открыл
      opener = trigger || document.activeElement;
      openerKey = opener && opener.getAttribute ? (opener.getAttribute("data-drawer-key") || "") : "";
    }
    say([]);
    return load(url).then(function (res) {
      if (res === "stale") return false;
      if (res !== "ok") {
        if (!opts.quiet) location.href = u.pathname + u.search;
        return false;
      }
      src = url;
      pagePath = u.pathname;
      if (!dlg.open) {
        dlg.showModal();
        if (opts.fromUrl) { pushed = false; setUrlParam(pagePath, false); }
        else { pushed = true; setUrlParam(pagePath, true); }
      } else {
        setUrlParam(pagePath, false);
      }
      var field = body.querySelector("[data-drawer-autofocus]");
      (field || heading).focus();
      if (pendingSay.length) { say(pendingSay); pendingSay = []; }
      return true;
    }).catch(function () {
      if (!opts.quiet) location.href = u.pathname + u.search;
    });
  }

  function close(force) {
    if (!dlg.open) return;
    if (dirty && !force && discardText && window.sfDangerConfirm) {
      // введённое в форме не теряется молча (Esc, ✕, подложка)
      window.sfDangerConfirm(discardText, {
        title: discardText,
        desc: dlg.getAttribute("data-drawer-discard-desc") || "",
        yes: dlg.getAttribute("data-drawer-discard-yes") || "",
        no: dlg.getAttribute("data-drawer-discard-no") || ""
      }).then(function (ok) { if (ok) { dirty = false; close(true); } });
      return;
    }
    dirty = false;
    if (pushed) { pushed = false; history.back(); return; }  // popstate закроет шторку
    setUrlParam("", false);
    dlg.close();
  }

  function visible(el) {
    return el && document.contains(el) && el.offsetParent !== null && typeof el.focus === "function";
  }

  dlg.addEventListener("cancel", function (e) { e.preventDefault(); close(); });
  function markDirty(e) {
    var f = e.target && e.target.form;
    if (f && f.hasAttribute("data-drawer-form") && body.contains(f)) dirty = true;
  }
  body.addEventListener("input", markDirty);
  body.addEventListener("change", markDirty);
  dlg.addEventListener("close", function () {
    seq++;
    body.innerHTML = "";
    src = null;
    pagePath = null;
    var back = opener;
    if (!visible(back) && openerKey && window.CSS && CSS.escape) {
      back = document.querySelector('[data-drawer-key="' + CSS.escape(openerKey) + '"]');
    }
    if (!visible(back)) {  // плашки больше нет (бронь перенесли/удалили)
      back = document.querySelector("main h1") || document.querySelector("[data-drawer-refresh]");
      if (back && !back.hasAttribute("tabindex")) back.setAttribute("tabindex", "-1");
    }
    if (back) back.focus();
    opener = null;
    var queued = afterClose;
    afterClose = [];
    if (queued.length) toast(queued);
  });
  window.addEventListener("popstate", function () {
    var path = new URL(location.href).searchParams.get("drawer");
    if (!path && dlg.open) { pushed = false; dlg.close(); }  // «назад» на телефоне закрывает шторку
    else if (path && !dlg.open) open(path, null, { quiet: true, fromUrl: true });
  });
  dlg.addEventListener("mousedown", function (e) { downOnBackdrop = e.target === dlg; });
  dlg.addEventListener("click", function (e) {
    if (e.target === dlg && downOnBackdrop) close();  // клик по подложке целиком
    if (e.target.closest("[data-drawer-close]")) close();
  });

  window.sfRefreshRegions = function (keepMsgs) {
    var regions = document.querySelectorAll("[data-drawer-refresh]");
    if (!regions.length) return Promise.resolve();
    var mine = ++refreshSeq;
    var y = window.scrollY;
    return fetch(pageUrl(), { credentials: "same-origin", redirect: "manual", headers: { "X-Sf-Refresh": "1" } })
      .then(function (r) {
        if (r.type === "opaqueredirect" || !r.ok) throw new Error(String(r.status));
        return r.text();
      })
      .then(function (html) {
        if (mine !== refreshSeq) return;  // пришёл более свежий ответ
        var doc = new DOMParser().parseFromString(html, "text/html");
        var missing = false;
        regions.forEach(function (el) {
          var fresh = el.id && doc.getElementById(el.id);
          if (!fresh) { missing = true; return; }
          var scroll = {};
          el.querySelectorAll("[data-scroll-key]").forEach(function (n) { scroll[n.getAttribute("data-scroll-key")] = n.scrollLeft; });
          el.innerHTML = fresh.innerHTML;
          el.querySelectorAll("[data-scroll-key]").forEach(function (n) {
            var k = n.getAttribute("data-scroll-key");
            if (scroll[k] !== undefined) n.scrollLeft = scroll[k];
          });
          document.dispatchEvent(new CustomEvent("sf:region-updated", { detail: { el: el } }));
        });
        if (missing) { carry(keepMsgs); location.reload(); return; }
        window.scrollTo(0, y);
      })
      .catch(function () { if (mine === refreshSeq) { carry(keepMsgs); location.reload(); } });
  };

  window.sfDrawer = {
    open: open,
    close: close,
    reload: function () { return src ? load(src, true) : Promise.resolve("stale"); },
    toast: toast,
  };

  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-drawer]");
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (!cabinetUrl(a.getAttribute("href"))) return;  // чужой адрес — обычная ссылка
    e.preventDefault();
    open(a.getAttribute("href"), a);
  });

  function unlock(btn) { if (btn) { btn.disabled = false; btn.removeAttribute("aria-disabled"); } }

  function firstInvalid() {
    return body.querySelector("[aria-invalid='true'], .errorlist + input, .errorlist + select, .errorlist + textarea");
  }

  // Шторку перезагружаем после КАЖДОГО ответа на действие (часть изменений могла
  // записаться и при ошибке). Сбой перезагрузки не превращается в «неясно» для
  // действия, которое сервер подтвердил: его сообщения показываются всегда.
  function reloadAfter(msgs, okFocus) {
    var url = src;
    if (!url || !dlg.open) { toast(msgs); return Promise.resolve(); }  // шторку закрыли на лету
    return load(url, true).catch(function () { return "error"; }).then(function (state) {
      if (state === "ok") {
        heading.focus();  // кнопка, на которой был фокус, пересоздана
        say(msgs);
        return;
      }
      if (state === "stale") { toast(msgs); return; }  // открыт уже другой объект
      // gone / away / error: объект исчез или шторка больше не может его показать
      close();
      toast(msgs);
      if (state !== "gone") window.sfRefreshRegions(msgs);
    });
  }

  function unclear(btn) {
    unlock(btn);
    var msgs = [{ level: "warning", text: unclearText }];
    window.sfRefreshRegions(msgs);
    return reloadAfter(msgs);
  }

  // Фаза всплытия + defaultPrevented: подтверждение опасных шагов (_danger_confirm,
  // capture) и сжатие фото успевают первыми.
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || !form.closest || !form.closest("[data-drawer-body]") || !form.hasAttribute("data-drawer-form")) return;
    e.preventDefault();
    if (busy) return;  // без двойной отправки — и той же формы, и соседней (деньги)
    busy = true;
    var btn = e.submitter;
    var data = new FormData(form);
    if (btn && btn.name) data.append(btn.name, btn.value);
    form.setAttribute("aria-busy", "true");
    if (btn) { btn.disabled = true; btn.setAttribute("aria-disabled", "true"); }
    var after = form.getAttribute("data-drawer-after") || "reload";
    function done() { busy = false; form.removeAttribute("aria-busy"); }
    fetch(form.getAttribute("action") || pageUrl(), {
      method: "POST", body: data, credentials: "same-origin", redirect: "manual",
      headers: { "X-Sf-Drawer": "1" }
    })
      .then(function (r) {
        done();
        if (r.type === "opaqueredirect") { location.reload(); return; }  // сессия истекла
        var type = r.headers.get("Content-Type") || "";
        if (r.headers.get("X-Sf-Fragment") === "1") {  // форма с ошибками — введённое цело
          return r.text().then(function (html) {
            fill(html, true);
            var f = firstInvalid();
            if (f) f.focus(); else { alertBox.setAttribute("tabindex", "-1"); alertBox.focus(); }
            say(headerMessages(r));
          });
        }
        if (type.indexOf("application/json") !== -1 && r.ok) {
          return r.json().then(function (res) {
            var msgs = res.messages || [];
            if (res.navigate && res.location) { location.href = res.location; return; }  // сообщения покажет та страница
            window.sfRefreshRegions(msgs);
            if (res.open) {  // показать созданный объект, сообщение — в нём
              return open(res.open, null, {}).then(function (shown) { if (shown) say(msgs); else toast(msgs); });
            }
            var calm = msgs.every(function (m) { return m.level !== "error" && m.level !== "warning"; });
            dirty = false;  // сервер принял — введённое сохранено
            if (res.ok && calm && after === "close") { close(true); toast(msgs); return; }
            return reloadAfter(msgs.length ? msgs : (res.ok ? [] : [{ level: "error", text: errText }]));
          });
        }
        if (r.status >= 500) return unclear(btn);  // сбой ПОСЛЕ записи возможен — не «ничего не было»
        // 403/404/409 вьюхи (сообщения — в заголовке) или 403 middleware пакета (JSON)
        return r.text().then(function (text) {
          unlock(btn);
          var msgs = headerMessages(r);
          if (!msgs.length) {
            var plain = text && text.length < 200 && text.indexOf("<") === -1 && text.charAt(0) !== "{";
            msgs = [{ level: "error", text: plain ? text : errText }];
          }
          return reloadAfter(msgs);
        });
      })
      .catch(function () {
        // Сеть оборвалась после отправки: действие могло пройти (деньги!) — не «повторите»,
        // а свежее состояние и честное «статус неясен».
        done();
        return unclear(btn);
      });
  });

  // Автооткрытие: ?drawer=<путь> (ссылка, F5, «вперёд») или маркер страницы
  // (редирект после действия без JS: ?buchung=…).
  var fromParam = new URL(location.href).searchParams.get("drawer");
  var auto = document.querySelector("[data-drawer-autoopen]");
  var first = fromParam || (auto && auto.getAttribute("data-drawer-autoopen"));
  if (first) open(first, null, { quiet: true, fromUrl: true });
})(); } catch (e) { console.error(e); }
// ---- stays/_walkin_form.html ----
// UX-D D1.3: walk-in форма (страница stay-new и шторка «Neue Buchung») — номера и тарифы
// другой категории скрыты; сервер всё равно проверяет. Скриптов во фрагменте нет.
try { (function () {
  "use strict";
  if (window.__walkinBound) return;
  window.__walkinBound = true;
  function filter(sel, ok) {
    if (!sel) return;
    Array.prototype.forEach.call(sel.options, function (o) {
      var show = ok(o);
      o.hidden = !show;
      o.disabled = !show;
    });
    if (sel.selectedOptions[0] && sel.selectedOptions[0].disabled) sel.value = "";
  }
  function sync() {
    var unit = document.getElementById("walkin-unit");
    if (!unit) return;
    filter(document.querySelector("[data-walkin-room]"), function (o) {
      var u = o.getAttribute("data-unit");
      return !u || u === unit.value;
    });
    filter(document.querySelector("[data-walkin-rate]"), function (o) {
      var ids = o.getAttribute("data-units");
      return !ids || ids.split(",").indexOf(unit.value) >= 0;
    });
  }
  document.addEventListener("change", function (e) {
    if (e.target && e.target.id === "walkin-unit") sync();
  });
  document.addEventListener("sf:drawer-loaded", sync);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sync);
  else sync();
})(); } catch (e) { console.error(e); }
// ---- booking/service_page.html ----
// UX-D D2.4: скрытое `tab` формы = выбранная вкладка в момент отправки — Save
// возвращает на ту же вкладку (без JS остаётся вкладка, с которой страница открылась).
try { (function () {
  "use strict";
  document.addEventListener("submit", function (e) {
    var form = e.target;
    // UX-D D4.6: та же механика у страницы номера ([data-room-page] / [data-room-tab]).
    var page = form && form.closest && form.closest("[data-svc-page], [data-room-page]");
    var field = page && form.querySelector("[data-svc-tab], [data-room-tab]");
    if (!field) return;
    var cur = page.querySelector('[data-pf-tab][aria-selected="true"]');
    if (cur) field.value = cur.getAttribute("data-pf-tab");
  }, true);
})(); } catch (e) { console.error(e); }
// ---- stays/channels.html (copy) ----
// UX-D D4.4: «Kopieren» у поля только-для-чтения: кнопка [data-copy-target="<id>"].
// Без Clipboard API (http, старый браузер) — поле выделяется, текст копируют вручную.
try { (function () {
  "use strict";
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-copy-target]");
    if (!btn) return;
    var field = document.getElementById(btn.getAttribute("data-copy-target"));
    if (!field) return;
    // UX-D D4.6 (ревью a11y): фокус остаётся на кнопке, результат — в живой области
    // [data-copy-status] рядом (если есть), иначе читалка не услышит «Kopiert».
    var label = btn.textContent, done = btn.getAttribute("data-copied") || label;
    var status = btn.parentNode && btn.parentNode.querySelector("[data-copy-status]");
    function ok() {
      btn.textContent = done;
      if (status) status.textContent = done;
      setTimeout(function () {
        btn.textContent = label;
        if (status) status.textContent = "";
      }, 1500);
    }
    // Без Clipboard API (http) — поле в фокусе и выделено: копируют вручную (Ctrl+C).
    function manual() { field.focus(); field.select(); }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(field.value).then(ok, manual);
    } else {
      manual();
    }
  });
})(); } catch (e) { console.error(e); }
// ---- core/_sheet_js.html ----
try { (function () {
  "use strict";
  if (window.__sheetBound) return;
  window.__sheetBound = true;
  document.addEventListener("click", function (e) {
    var backdrop = e.target.closest("[data-sheet-backdrop]");
    if (!backdrop) return;
    var details = backdrop.closest("details");
    if (details) details.open = false;
  });
})(); } catch (e) { console.error(e); }
// ---- core/_photo_shrink.html ----
try { (function () {
  var LIMIT = 4.5 * 1024 * 1024, SIDE = 2560, pending = new WeakMap();
  if (!window.createImageBitmap || !window.DataTransfer) return;
  function shrink(file) {
    if (!/^image\/(jpeg|png|webp|heic|heif)$/i.test(file.type) || file.size <= LIMIT) return Promise.resolve(file);
    return createImageBitmap(file).then(function (bmp) {
      var k = Math.min(1, SIDE / Math.max(bmp.width, bmp.height));
      var c = document.createElement("canvas");
      c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
      function encode(q) {
        return new Promise(function (ok) { c.toBlob(ok, "image/jpeg", q); }).then(function (blob) {
          if (blob && blob.size > LIMIT && q > 0.5) return encode(q - 0.15);
          return blob;
        });
      }
      return encode(0.85).then(function (blob) {
        if (!blob) return file;
        var name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
        return new File([blob], name, { type: "image/jpeg", lastModified: Date.now() });
      });
    }).catch(function () { return file; });
  }
  document.addEventListener("change", function (e) {
    var input = e.target;
    if (!input.matches || !input.matches('input[type="file"]') || !input.files || !input.files.length) return;
    var files = Array.prototype.slice.call(input.files);
    if (!files.some(function (f) { return f.size > LIMIT; })) return;
    var job = Promise.all(files.map(shrink)).then(function (out) {
      var dt = new DataTransfer();
      out.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
    });
    pending.set(input.form || input, job);
    job.then(function () { pending.delete(input.form || input); });
  }, true);
  document.addEventListener("submit", function (e) {
    var job = pending.get(e.target);
    if (!job) return;
    e.preventDefault();
    var submitter = e.submitter;
    job.then(function () {
      if (e.target.requestSubmit) e.target.requestSubmit(submitter || undefined); else e.target.submit();
    });
  }, true);
})(); } catch (e) { console.error(e); }
// ---- core/_list_kb.html ----
try { (function () {
  "use strict";
  if (window.__listKbBound) return;
  window.__listKbBound = true;

  function stackLabels(root) {
    (root || document).querySelectorAll("table.ui-table-stack").forEach(function (t) {
      var heads = Array.prototype.map.call(t.querySelectorAll("thead th"), function (th) {
        return th.textContent.replace(/\s+/g, " ").trim();
      });
      t.setAttribute("role", "table");
      t.querySelectorAll("thead, tbody, tfoot").forEach(function (g) { g.setAttribute("role", "rowgroup"); });
      t.querySelectorAll("tr").forEach(function (tr) { tr.setAttribute("role", "row"); });
      t.querySelectorAll("thead th").forEach(function (th) { th.setAttribute("role", "columnheader"); });
      t.querySelectorAll("tbody tr, tfoot tr").forEach(function (tr) {
        var col = 0;
        Array.prototype.forEach.call(tr.children, function (cell) {
          if (cell.tagName === "TH") { cell.setAttribute("role", "rowheader"); }
          else { cell.setAttribute("role", "cell"); }
          var label = heads[col];
          if (label && !cell.hasAttribute("data-cell")) {
            cell.setAttribute("data-label", label);  // и после fetch-подмены — свежая
          }
          col += parseInt(cell.getAttribute("colspan") || "1", 10);
        });
      });
    });
  }

  // Строки списка = строки, в которых есть что открыть (первая ссылка/кнопка).
  // Сами строки фокус не получают (ревью a11y): стрелки и j/k переводят фокус на
  // «якорь» соседней строки, Tab ходит как обычно, Enter — нативный у ссылки.
  function anchorOf(row) {
    return row.querySelector("a[href], button:not([disabled])");
  }
  function rowsOf(list) {
    var rows = list.querySelectorAll("[data-kb-row]");
    if (!rows.length) rows = list.querySelectorAll("tbody tr");
    return Array.prototype.filter.call(rows, function (r) {
      return r.offsetParent !== null && anchorOf(r);
    });
  }
  function isField(el) {
    return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  }

  document.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var t = e.target;
    var list = t && t.closest && t.closest("[data-kb-list]");
    if (!list || isField(t) || document.querySelector("dialog[open]")) return;
    var k = e.key;
    if (k === "/") {
      var s = document.querySelector("[data-kb-search]");
      if (s) { e.preventDefault(); s.focus(); if (s.select) s.select(); }
      return;
    }
    if (["ArrowDown", "ArrowUp", "j", "k", "Home", "End"].indexOf(k) < 0) return;
    var rows = rowsOf(list);
    if (!rows.length) return;
    var cur = t.closest("[data-kb-row], tbody tr");
    var i = cur ? rows.indexOf(cur) : -1;
    var next = k === "Home" ? 0 : k === "End" ? rows.length - 1
      : (k === "ArrowDown" || k === "j") ? Math.min(i + 1, rows.length - 1) : Math.max(i - 1, 0);
    e.preventDefault();
    var a = anchorOf(rows[next]);
    a.focus();
    rows[next].scrollIntoView({ block: "nearest" });
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { stackLabels(); });
  } else {
    stackLabels();
  }
  // Списки, подменённые fetch'ем (KAT-5 / box-фрагменты), сообщают об этом событием.
  document.addEventListener("sf:region-updated", function () { stackLabels(); });
  document.addEventListener("sf:navigated", function () { stackLabels(); });
})(); } catch (e) { console.error(e); }
