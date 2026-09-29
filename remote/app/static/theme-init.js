document.documentElement.dataset.theme = "dark";
document.documentElement.style.colorScheme = "dark";
try {
  localStorage.removeItem("firmware-theme");
} catch (_) {
  // Local storage can be unavailable in private browsing mode.
}
