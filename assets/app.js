// wirelab releases page: language and theme toggles only. The content is static HTML.
(function () {
  "use strict";
  var root = document.documentElement;
  var langBtn = document.getElementById("lang-btn");
  var themeBtn = document.getElementById("theme-btn");
  var L = {
    pl: { title: "Wydania wirelab", lang: "Switch to English", label: "EN", dark: "Włącz ciemny motyw", light: "Włącz jasny motyw" },
    en: { title: "wirelab releases", lang: "Przełącz na polski", label: "PL", dark: "Switch to dark theme", light: "Switch to light theme" }
  };
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function lang() { return root.lang === "en" ? "en" : "pl"; }
  function theme() {
    var set = root.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function apply() {
    var t = L[lang()];
    document.title = t.title;
    document.getElementById("lang-label").textContent = t.label;
    langBtn.setAttribute("aria-label", t.lang);
    themeBtn.setAttribute("aria-label", theme() === "dark" ? t.light : t.dark);
  }
  langBtn.addEventListener("click", function () {
    root.lang = lang() === "pl" ? "en" : "pl";
    store("wl-updates-lang", root.lang);
    apply();
  });
  themeBtn.addEventListener("click", function () {
    var next = theme() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    store("wl-updates-theme", next);
    apply();
  });
  langBtn.hidden = false;
  themeBtn.hidden = false;
  apply();
})();
