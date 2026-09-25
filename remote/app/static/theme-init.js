try {
  document.documentElement.dataset.theme = localStorage.getItem("firmware-theme") || "dark";
} catch (_) {
  document.documentElement.dataset.theme = "dark";
}
