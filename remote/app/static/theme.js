(function () {
  const root = document.documentElement;

  function enforceDarkTheme() {
    root.dataset.theme = "dark";
    root.style.colorScheme = "dark";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = "#0B0B0C";
  }

  enforceDarkTheme();
  document.addEventListener("DOMContentLoaded", enforceDarkTheme);
})();
