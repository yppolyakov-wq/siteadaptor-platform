/* FLT-1e: фильтры городского портала — шторка «Alle Filter», поповеры, автосортировка.
 * Без этого файла всё работает: шторка — обычная форма (noscript), поповеры — <details>,
 * сортировка — кнопка «OK». Скрипт только улучшает поведение. План FLT §4, §6. */
(function () {
  "use strict";
  var drawer = document.getElementById("flt-drawer");
  var opener = null;
  var mobile = window.matchMedia("(max-width: 639px)");

  function openDrawer(section, from) {
    if (!drawer || typeof drawer.showModal !== "function") return false;
    opener = from || document.activeElement;
    drawer.showModal();
    var target = section && drawer.querySelector('[data-flt-sec="' + section + '"]');
    if (target) {
      target.scrollIntoView({ block: "start" });
      var first = target.querySelector("input, a");
      if (first) first.focus();
    }
    return true;
  }

  function closeDrawer() {
    if (drawer && drawer.open) drawer.close();
  }

  if (drawer) {
    drawer.addEventListener("close", function () {
      if (opener && typeof opener.focus === "function") opener.focus();
      opener = null;
    });
    // клик по затемнению (вне содержимого) — закрыть
    drawer.addEventListener("click", function (e) {
      if (e.target === drawer) closeDrawer();
    });
  }

  document.addEventListener("click", function (e) {
    var open = e.target.closest("[data-flt-open]");
    if (open && openDrawer("", open)) {
      e.preventDefault();
      return;
    }
    if (e.target.closest("[data-flt-close]")) {
      e.preventDefault();
      closeDrawer();
      return;
    }
    // телефон: поповер в прокручиваемой строке обрезается — пилюля ▾ открывает шторку
    var summary = e.target.closest("[data-flt-pop] > summary");
    if (summary && mobile.matches) {
      var pop = summary.parentElement;
      if (openDrawer(pop.getAttribute("data-flt-pop"), summary)) {
        e.preventDefault();
        return;
      }
    }
    // клик вне открытого поповера — закрыть его
    document.querySelectorAll("[data-flt-pop][open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });

  // один поповер за раз
  document.querySelectorAll("[data-flt-pop]").forEach(function (d) {
    d.addEventListener("toggle", function () {
      if (!d.open) return;
      document.querySelectorAll("[data-flt-pop][open]").forEach(function (o) {
        if (o !== d) o.removeAttribute("open");
      });
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll("[data-flt-pop][open]").forEach(function (d) {
      d.removeAttribute("open");
      var s = d.querySelector("summary");
      if (s) s.focus();
    });
  });

  // пустые поля не тащим в адрес («preis_von=&datum=») — короче ссылка, те же результаты
  document.querySelectorAll("[data-flt] form").forEach(function (form) {
    form.addEventListener("submit", function () {
      form.querySelectorAll("input[name], select[name]").forEach(function (el) {
        if (el.value === "" && (el.type !== "radio" || el.checked)) el.disabled = true;
      });
    });
  });
  // «Назад» из выдачи возвращает страницу из bfcache — поля снова активны
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("[data-flt] form [disabled]").forEach(function (el) {
      el.disabled = false;
    });
  });

  // сортировка: смена значения — сразу применить, кнопка «OK» не нужна
  document.querySelectorAll("[data-flt-sort]").forEach(function (form) {
    var btn = form.querySelector("[data-flt-sort-submit]");
    if (btn) btn.hidden = true;
    var sel = form.querySelector("select");
    if (sel) {
      sel.addEventListener("change", function () {
        form.submit();
      });
    }
  });
})();
