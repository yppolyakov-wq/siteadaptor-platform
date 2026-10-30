/* KA-12 E10.6: общий JS хрома кабинета (был инлайн в tenant/_base_dashboard.html
   и партиалах core/_*). Один кэшируемый файл; подключается в конце body. */
// ---- tenant/_base_dashboard.html ----
// M22b realtime: живой бейдж непрочитанных сообщений в навигации.
(function () {
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
})();
(function () {
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
        html += '<a href="' + encodeURI(it.url) + '" class="flex items-center justify-between gap-3 px-4 py-2 text-sm hover:bg-indigo-50 focus-visible:bg-indigo-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500">' +
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
})();
// ---- core/_confirm_tap.html ----
(function () {
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
})();
// ---- core/_danger_confirm.html ----
(function () {
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

  window.sfDangerConfirm = function (label) {
    return new Promise(function (resolve) {
      if (!dlg || typeof dlg.showModal !== "function") {
        resolve(window.confirm(label));
        return;
      }
      pending = resolve;
      dlg.querySelector("[data-danger-label]").textContent = label || "";
      dlg.showModal();
      dlg.querySelector("[data-danger-no]").focus();
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
      if (typeof form.requestSubmit === "function") form.requestSubmit(btn);
      else {
        var keep = document.createElement("input");
        keep.type = "hidden";
        keep.name = btn.name;
        keep.value = btn.value;
        form.appendChild(keep);
        form.submit();
      }
    });
  }, true);
})();
// ---- core/_sheet_js.html ----
(function () {
  "use strict";
  if (window.__sheetBound) return;
  window.__sheetBound = true;
  document.addEventListener("click", function (e) {
    var backdrop = e.target.closest("[data-sheet-backdrop]");
    if (!backdrop) return;
    var details = backdrop.closest("details");
    if (details) details.open = false;
  });
})();
// ---- core/_photo_shrink.html ----
(function () {
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
})();
// ---- core/_list_kb.html ----
(function () {
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
  document.addEventListener("sf:navigated", function () { stackLabels(); });
})();
