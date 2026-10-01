// Runs before first paint: applies the saved theme and language to avoid a flash.
(function () {
  var d = document.documentElement, theme = null, lang = null;
  try { theme = localStorage.getItem("wl-updates-theme"); lang = localStorage.getItem("wl-updates-lang"); } catch (e) {}
  if (theme === "light" || theme === "dark") d.setAttribute("data-theme", theme);
  var q = /[?&]lang=(pl|en)\b/.exec(location.search);
  if (q) lang = q[1];
  if (lang !== "pl" && lang !== "en") {
    var nav = (navigator.languages && navigator.languages[0]) || navigator.language || "pl";
    lang = /^pl\b/i.test(nav) ? "pl" : "en";
  }
  d.lang = lang;
})();
