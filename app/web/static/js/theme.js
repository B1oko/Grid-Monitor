const STORAGE_KEY = "theme";

export function getThemePreference() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "system";
  } catch {
    return "system";
  }
}

export function setThemePreference(preference) {
  try {
    if (preference === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Ignore.
  }
  applyTheme(preference);
}

export function applyTheme(preference = getThemePreference()) {
  if (preference === "light" || preference === "dark") {
    document.documentElement.setAttribute("data-theme", preference);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  window.dispatchEvent(new Event("themechange"));
}

export function isDark() {
  const attr = document.documentElement.getAttribute("data-theme");
  return attr === "dark" || (!attr && window.matchMedia("(prefers-color-scheme: dark)").matches);
}
