const THEME_KEY = "theme";
const DARK = "dark";
const LIGHT = "light";

function getSystemPreference() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? DARK : LIGHT;
}

function getStoredTheme() {
  return localStorage.getItem(THEME_KEY);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  // Update meta theme-color
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.content = theme === DARK ? "#0f1117" : "#0066CC";
  }
}

export function initTheme() {
  const stored = getStoredTheme();
  const theme = stored || getSystemPreference();
  applyTheme(theme);

  // Listen for system preference changes
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    if (!getStoredTheme()) {
      applyTheme(e.matches ? DARK : LIGHT);
    }
  });
}

export function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || LIGHT;
  const next = current === DARK ? LIGHT : DARK;
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
  return next;
}

export function currentTheme() {
  return document.documentElement.getAttribute("data-theme") || LIGHT;
}
