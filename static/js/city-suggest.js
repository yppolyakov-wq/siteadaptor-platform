/* FB-19b: подсказки поля «Stadt» по ВСЕМ муниципалитетам Германии.
 * Поле: <input data-city-suggest="<url gemeinden_de.json>" list="…">. Список грузится один
 * раз при первом вводе; подсказки — сначала названия, начинающиеся с введённого, затем
 * содержащие его; внутри — по убыванию населения (так упорядочен файл). Без JS остаётся
 * короткий datalist с сервера. Делегирование на document — поле может прийти fetch-свопом. */
(function () {
  if (window.__saCitySuggest) return;
  window.__saCitySuggest = true;
  var LIMIT = 20;
  var cache = {};
  function fold(s) {
    return (s || "").toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe")
      .replace(/ü/g, "ue").replace(/ß/g, "ss").replace(/\s+/g, " ").trim();
  }
  function load(url) {
    if (!cache[url]) {
      cache[url] = fetch(url, { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : { items: [] }; })
        .then(function (d) {
          return (d.items || []).map(function (x) { return [x[0], fold(x[0])]; });
        })
        .catch(function () { return []; });
    }
    return cache[url];
  }
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (!el.matches || !el.matches("input[data-city-suggest]")) return;
    var dl = document.getElementById(el.getAttribute("list") || "");
    if (!dl) return;
    if (dl.__orig === undefined) dl.__orig = dl.innerHTML;
    var q = fold(el.value);
    if (q.length < 2) { dl.innerHTML = dl.__orig; return; }
    load(el.getAttribute("data-city-suggest")).then(function (all) {
      if (fold(el.value) !== q || !all.length) return;
      var head = [], rest = [];
      for (var i = 0; i < all.length && head.length < LIMIT; i++) {
        var pos = all[i][1].indexOf(q);
        if (pos === 0) head.push(all[i][0]);
        else if (pos > 0 && rest.length < LIMIT) rest.push(all[i][0]);
      }
      dl.innerHTML = "";
      head.concat(rest).slice(0, LIMIT).forEach(function (name) {
        var o = document.createElement("option");
        o.value = name;
        dl.appendChild(o);
      });
    });
  });
})();
