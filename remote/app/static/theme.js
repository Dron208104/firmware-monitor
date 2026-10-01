(function () {
  const root = document.documentElement;
  root.dataset.theme = "dark";
  root.style.colorScheme = "dark";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = "#0b0b0c";
})();
