(function () {
  const storageKey = "firmware-theme";
  const root = document.documentElement;
  const currentTheme = () => root.dataset.theme === "light" ? "light" : "dark";

  function render(theme) {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    const light = theme === "light";
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const label = button.querySelector("[data-theme-label]");
      const icon = button.querySelector(".theme-toggle__icon");
      if (label) label.textContent = light ? "Тёмная тема" : "Светлая тема";
      if (icon) icon.textContent = light ? "☾" : "☀";
      button.setAttribute("aria-label", light ? "Включить тёмную тему" : "Включить светлую тему");
      button.setAttribute("title", light ? "Включить тёмную тему" : "Включить светлую тему");
    });
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = light ? "#F3F5F7" : "#0B0B0C";
  }

  document.addEventListener("DOMContentLoaded", () => {
    render(currentTheme());
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const next = currentTheme() === "dark" ? "light" : "dark";
        try { localStorage.setItem(storageKey, next); } catch (_) { /* private mode */ }
        render(next);
      });
    });
  });
})();
