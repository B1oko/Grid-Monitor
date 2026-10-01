import { api } from "../api.js";
import { EnergyChart, PowerChart, SocChart } from "../charts.js";
import { esc } from "../format.js";
import { formatNumber, getLanguage, t } from "../i18n.js";
import { on, state } from "../state.js";
import { emptyState } from "../ui.js";

const LIVE_WINDOW_MS = 10 * 60 * 1000;
const REFRESH_MS = 60 * 1000;

function startOfDay(date, offsetDays = 0) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offsetDays);
  return d;
}

// Power ranges show every stored sample on a time axis. Energy ranges show one
// bar per day or month, split in the browser's time zone.
const RANGES = {
  live: { kind: "live" },
  today: {
    kind: "power",
    window: (now) => ({ from: startOfDay(now), to: now, axisMax: startOfDay(now, 1) }),
    refresh: true,
  },
  yesterday: {
    kind: "power",
    window: (now) => ({ from: startOfDay(now, -1), to: startOfDay(now) }),
  },
  "7d": {
    kind: "power",
    window: (now) => ({ from: new Date(now.getTime() - 7 * 24 * 3600 * 1000), to: now }),
    refresh: true,
  },
  month: {
    kind: "energy",
    resolution: "day",
    refresh: true,
    periods: (now) => {
      const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      return Array.from({ length: days }, (_, i) => new Date(now.getFullYear(), now.getMonth(), i + 1));
    },
  },
  year: {
    kind: "energy",
    resolution: "month",
    refresh: true,
    periods: (now) => Array.from({ length: 12 }, (_, i) => new Date(now.getFullYear(), i, 1)),
  },
};

let activeRange = "live";

function periodKey(date, resolution) {
  return resolution === "month"
    ? `${date.getFullYear()}-${date.getMonth()}`
    : `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function periodLabels(date, resolution) {
  const lang = getLanguage();
  if (resolution === "month") {
    return {
      label: date.toLocaleDateString(lang, { month: "short" }),
      title: date.toLocaleDateString(lang, { month: "long", year: "numeric" }),
    };
  }
  return {
    label: String(date.getDate()),
    title: date.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" }),
  };
}

function kwh(value) {
  return `${formatNumber(value, value >= 100 ? 0 : 1)} kWh`;
}

function summary(rows) {
  const sum = (key) => rows.reduce((total, row) => total + (row[key] || 0), 0);
  const home = sum("home_kwh");
  const imported = sum("grid_import_kwh");
  const self = home > 0 ? Math.round(Math.max(0, Math.min(1, 1 - imported / home)) * 100) : null;
  const items = [
    ["solar", kwh(sum("solar_kwh"))],
    ["home", kwh(home)],
    ["imported", kwh(imported)],
    ["exported", kwh(sum("grid_export_kwh"))],
    ["self_sufficiency", self == null ? "--" : `${self} %`],
  ];
  return items
    .map(([key, value]) => `<div><span>${esc(t(`history.summary.${key}`))}</span><strong>${esc(value)}</strong></div>`)
    .join("");
}

export function renderHistory(root) {
  root.innerHTML = `
    <div class="page history">
      <div class="segmented scroll-x" role="tablist" aria-label="${esc(t("history.range"))}">
        ${Object.keys(RANGES)
          .map(
            (key) =>
              `<button type="button" role="tab" data-range="${key}" class="${key === activeRange ? "active" : ""}">
                ${key === "live" ? '<span class="live-dot"></span>' : ""}${esc(t(`history.ranges.${key}`))}
              </button>`
          )
          .join("")}
      </div>
      <section class="stat-strip energy-summary" data-v="summary" hidden></section>
      <section class="card chart-card">
        <div class="chart-wrap">
          <canvas data-v="main"></canvas>
          <div class="chart-empty" hidden></div>
        </div>
        <div class="soc-block" data-v="soc" hidden>
          <div class="soc-title">${esc(t("series.battery_soc"))}</div>
          <div class="soc-wrap"><canvas></canvas></div>
        </div>
        <p class="chart-caption muted small" data-v="caption" hidden>${esc(t("history.energy_caption"))}</p>
      </section>
    </div>`;

  const $ = (key) => root.querySelector(`[data-v="${key}"]`);
  const mainCanvas = $("main");
  const socBlock = $("soc");
  const summaryEl = $("summary");
  const caption = $("caption");
  const empty = root.querySelector(".chart-empty");

  const power = new PowerChart(mainCanvas);
  const energy = new EnergyChart(mainCanvas);
  const soc = new SocChart(socBlock.querySelector("canvas"));
  let loadToken = 0;

  function clearCharts() {
    power.destroy();
    energy.destroy();
    soc.destroy();
  }

  function layout(kind) {
    summaryEl.hidden = kind !== "energy";
    caption.hidden = kind !== "energy";
    if (kind === "energy") socBlock.hidden = true;
    empty.hidden = true;
  }

  function showEmpty(title, text = "") {
    clearCharts();
    summaryEl.hidden = true;
    caption.hidden = true;
    socBlock.hidden = true;
    empty.innerHTML = emptyState("chart", title, text);
    empty.hidden = false;
  }

  function drawPower(rows, window, live = false) {
    const hasSoc = rows.some((row) => row.battery_soc_pct != null);
    layout("power");
    socBlock.hidden = !hasSoc;
    if (!live) energy.destroy();
    power.show(rows, { ...window, live });
    if (hasSoc) soc.show(rows, { ...window, live });
    else soc.destroy();
  }

  function drawLive() {
    if (activeRange !== "live") return;
    if (state.samples.length < 2) {
      showEmpty(t("history.waiting"));
      return;
    }
    const max = Date.now();
    drawPower(state.samples, { min: max - LIVE_WINDOW_MS, max }, Boolean(power.chart));
  }

  async function loadPower(range, token) {
    const now = new Date();
    const { from, to, axisMax } = range.window(now);
    const params = new URLSearchParams({
      inverter_id: String(state.selectedId),
      from: from.toISOString(),
      to: to.toISOString(),
      resolution: "minute",
    });
    const rows = await api.get(`/api/history?${params}`);
    if (token !== loadToken) return;
    if (!rows.length) {
      showEmpty(t("history.no_data"));
      return;
    }
    const samples = rows.map((row) => ({ ...row, t: Date.parse(row.ts) }));
    drawPower(samples, { min: from.getTime(), max: (axisMax || to).getTime() });
  }

  async function loadEnergy(range, token) {
    const now = new Date();
    const periods = range.periods(now);
    const params = new URLSearchParams({
      inverter_id: String(state.selectedId),
      from: periods[0].toISOString(),
      to: now.toISOString(),
      resolution: range.resolution,
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    });
    const rows = await api.get(`/api/energy?${params}`);
    if (token !== loadToken) return;
    if (!rows.length) {
      showEmpty(t("history.no_data"));
      return;
    }
    const byKey = new Map(rows.map((row) => [periodKey(new Date(row.ts), range.resolution), row]));
    const items = periods.map((date) => ({
      ...periodLabels(date, range.resolution),
      row: byKey.get(periodKey(date, range.resolution)),
    }));
    layout("energy");
    power.destroy();
    soc.destroy();
    summaryEl.innerHTML = summary(rows);
    energy.show(items, { titles: items.map((item) => item.title) });
  }

  async function loadRange(key, { quiet = false } = {}) {
    const token = ++loadToken;
    const range = RANGES[key];
    [power, energy, soc].forEach((chart) => {
      chart.quiet = quiet;
    });
    if (range.kind === "live") {
      clearCharts();
      drawLive();
      return;
    }
    if (!state.selectedId) return;
    try {
      if (range.kind === "energy") await loadEnergy(range, token);
      else await loadPower(range, token);
    } catch (error) {
      if (token === loadToken) showEmpty(t("history.load_failed"), error.message);
    }
  }

  root.querySelectorAll("[data-range]").forEach((button) =>
    button.addEventListener("click", () => {
      activeRange = button.dataset.range;
      root.querySelectorAll("[data-range]").forEach((b) => b.classList.toggle("active", b === button));
      loadRange(activeRange);
    })
  );

  loadRange(activeRange);

  // Ranges that end now pick up new samples while the page stays open.
  const timer = setInterval(() => {
    if (RANGES[activeRange].refresh && document.visibilityState === "visible") {
      loadRange(activeRange, { quiet: true });
    }
  }, REFRESH_MS);

  const onTheme = () => [power, energy, soc].forEach((chart) => chart.refreshTheme());
  window.addEventListener("themechange", onTheme);
  const offs = [
    on("sample", drawLive),
    on("samples", drawLive),
    on("inverter", () => loadRange(activeRange)),
  ];
  return () => {
    clearInterval(timer);
    offs.forEach((off) => off());
    window.removeEventListener("themechange", onTheme);
    clearCharts();
  };
}
