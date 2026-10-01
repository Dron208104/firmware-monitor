(function () {
  document.documentElement.dataset.theme = "dark";
  document.documentElement.style.colorScheme = "dark";
  try { localStorage.removeItem("firmware-theme"); } catch (_) {}
})();
