import { formatNumber, getLanguage, t } from "./i18n.js";

export function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );
}

const isMissing = (value) => value === null || value === undefined || Number.isNaN(Number(value));

export function formatPower(value) {
  return isMissing(value) ? "-- W" : `${formatNumber(Math.round(Number(value)))} W`;
}

export function formatPercent(value) {
  return isMissing(value) ? "-- %" : `${formatNumber(Math.round(Number(value)))} %`;
}

export function formatHours(hours) {
  if (!Number.isFinite(hours) || hours > 99) return t("format.more_than_99h");
  const totalMinutes = Math.round(hours * 60);
  if (totalMinutes < 60) return `${totalMinutes} min`;
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return m ? `${h} h ${String(m).padStart(2, "0")} min` : `${h} h`;
}

export function formatDateTime(value) {
  return new Intl.DateTimeFormat(getLanguage(), { dateStyle: "short", timeStyle: "short" }).format(
    new Date(value)
  );
}

export function formatTime(value) {
  return new Intl.DateTimeFormat(getLanguage(), { timeStyle: "medium" }).format(new Date(value));
}
