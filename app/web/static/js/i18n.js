// Translations for the web UI. Catalogs live in app/i18n/locales/<lang>.json and
// are shared with the backend. Placeholder formatting rules must match
// app/i18n/__init__.py: *_w -> power, *_min -> duration, *_deg -> angle.

const STORAGE_KEY = "language";
const DEFAULT_LANGUAGE = "en";

let language = DEFAULT_LANGUAGE;
let languages = [];
let fallback = {};
let messages = {};

function flatten(value, prefix = "", out = {}) {
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object") flatten(child, path, out);
    else out[path] = String(child);
  }
  return out;
}

async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function initI18n() {
  languages = await fetchJson("/i18n/languages.json");
  fallback = flatten(await fetchJson(`/i18n/${DEFAULT_LANGUAGE}.json`));
  await applyLanguage(getLanguagePreference());
}

export function getLanguage() {
  return language;
}

export function getLanguages() {
  return languages;
}

export function getLanguagePreference() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "auto";
  } catch {
    return "auto";
  }
}

export async function setLanguagePreference(preference) {
  try {
    localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Private mode: the choice lasts for this session only.
  }
  await applyLanguage(preference);
}

function resolveLanguage(preference) {
  const codes = languages.map((item) => item.code);
  if (preference !== "auto" && codes.includes(preference)) return preference;
  for (const tag of navigator.languages || [navigator.language]) {
    const code = String(tag).toLowerCase().split("-")[0];
    if (codes.includes(code)) return code;
  }
  return DEFAULT_LANGUAGE;
}

async function applyLanguage(preference) {
  const next = resolveLanguage(preference);
  messages = next === DEFAULT_LANGUAGE ? fallback : flatten(await fetchJson(`/i18n/${next}.json`));
  language = next;
  document.documentElement.lang = next;
}

export function t(key, params = {}) {
  const template = messages[key] ?? fallback[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    name in params ? formatParam(name, params[name]) : match
  );
}

export function formatNumber(value, decimals = 0) {
  const fixed = Math.abs(Number(value)).toFixed(decimals);
  const [intPart, fraction] = fixed.split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, t("meta.thousands_separator"));
  const sign = Number(value) < 0 && Number(fixed) !== 0 ? "-" : "";
  return sign + grouped + (fraction ? t("meta.decimal_separator") + fraction : "");
}

export function formatDurationMinutes(minutes) {
  const total = Math.max(0, Math.round(Number(minutes)));
  if (total < 60) return `${total} min`;
  return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")} min`;
}

function formatParam(name, value) {
  if (value === null || value === undefined) return "--";
  if (name.endsWith("_w")) return `${formatNumber(value)} W`;
  if (name.endsWith("_min")) return formatDurationMinutes(value);
  if (name.endsWith("_deg")) return `${Math.round(Number(value))}°`;
  return String(value);
}
