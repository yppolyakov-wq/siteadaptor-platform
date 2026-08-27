/** Tailwind build (P5): компилируем purged CSS вместо CDN (Core Web Vitals).
 *  Сканируем все шаблоны; darkMode:'class' — под переключатель тёмной темы. */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
  ],
  darkMode: "class",
  // M20R-1: грид-классы генерятся в Python (siteconfig.grid_class_string) и не
  // встречаются литералом в шаблонах — без safelist purge их вырежет.
  safelist: [
    "grid-cols-1", "grid-cols-2",
    // Полный набор таблиц движка: _GRID_SM 1..4 (SE-3c) и _GRID_LG 1..6 (DS-5).
    // Хвост отставал: "6 в ряд" выбиралось в конструкторе, но класса в CSS не
    // было — сетка молча падала в одну колонку (поймано стендом 2026-08-27).
    "sm:grid-cols-1", "sm:grid-cols-2", "sm:grid-cols-3", "sm:grid-cols-4",
    "lg:grid-cols-1", "lg:grid-cols-2", "lg:grid-cols-3", "lg:grid-cols-4",
    "lg:grid-cols-5", "lg:grid-cols-6",
    "gap-3", "gap-4", "md:gap-6", "gap-6", "md:gap-8",
    // Belegungsplan: цвета плашек броней задаются в Python (stays/views.py
    // bar_color) — без safelist purge их вырезал → плашки были без фона.
    "bg-green-200", "text-green-900", "bg-amber-200", "text-amber-900",
    "bg-indigo-200", "text-indigo-900", "bg-gray-200", "text-gray-600",
  ],
  theme: { extend: {} },
  plugins: [],
};
