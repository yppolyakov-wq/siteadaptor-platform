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
    "sm:grid-cols-1", "sm:grid-cols-2", "sm:grid-cols-3",
    "lg:grid-cols-1", "lg:grid-cols-2", "lg:grid-cols-3", "lg:grid-cols-4", "lg:grid-cols-5",
    "gap-3", "gap-4", "md:gap-6", "gap-6", "md:gap-8",
  ],
  theme: { extend: {} },
  plugins: [],
};
