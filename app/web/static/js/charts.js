import { formatNumber, getLanguage, t } from "./i18n.js";

// Colors come from the CSS tokens shared with the dashboard, so light/dark and
// the energy-flow diagram stay in sync. The set is validated for color-vision
// deficiency in both themes; change all four together.
const POWER_SERIES = [
  { key: "pv_power_w", label: "series.solar", color: "--solar", fill: true },
  { key: "load_power_w", label: "series.home", color: "--load" },
  { key: "battery_power_w", label: "series.battery", color: "--battery", signed: ["discharging", "charging"] },
  { key: "grid_power_w", label: "series.grid", color: "--grid", signed: ["importing", "exporting"] },
];

// Legend order, shared with the power chart.
const ENTITIES = ["series.solar", "series.home", "series.battery", "series.grid"];

// Sources stack above zero, uses below. Battery and grid keep one color for
// both directions; the side of the axis tells them apart.
const ENERGY_SERIES = [
  { key: "solar_kwh", label: "series.solar", entity: "series.solar", color: "--solar", sign: 1 },
  { key: "grid_import_kwh", label: "series.grid_import", entity: "series.grid", color: "--grid", sign: 1 },
  { key: "battery_discharge_kwh", label: "series.battery_discharge", entity: "series.battery", color: "--battery", sign: 1 },
  { key: "home_kwh", label: "series.home", entity: "series.home", color: "--load", sign: -1 },
  { key: "grid_export_kwh", label: "series.grid_export", entity: "series.grid", color: "--grid", sign: -1 },
  { key: "battery_charge_kwh", label: "series.battery_charge", entity: "series.battery", color: "--battery", sign: -1 },
];

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function rgba(color, alpha) {
  const n = parseInt(color.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

function palette() {
  return { ink: token("--ink"), muted: token("--muted"), line: token("--line"), panel: token("--panel") };
}

function tooltipBase(c) {
  return {
    backgroundColor: c.panel,
    borderColor: c.line,
    borderWidth: 1,
    titleColor: c.muted,
    bodyColor: c.ink,
    padding: 10,
    boxPadding: 4,
    usePointStyle: true,
  };
}

function legendBase(c) {
  return {
    position: "bottom",
    labels: {
      color: c.muted,
      boxWidth: 8,
      boxHeight: 8,
      padding: 14,
      usePointStyle: true,
      font: { size: 12 },
      // Solid swatches even for series drawn as a translucent area.
      generateLabels: (chart) =>
        window.Chart.defaults.plugins.legend.labels
          .generateLabels(chart)
          .map((item) => ({ ...item, fillStyle: item.strokeStyle })),
    },
  };
}

function valueAxis(c, format) {
  return {
    ticks: { color: c.muted, font: { size: 11 }, callback: format },
    grid: { color: (ctx) => (ctx.tick.value === 0 ? c.muted : c.line) },
    border: { display: false },
  };
}

// ---------- Time axis ----------

// Tick positions on local-time boundaries (minutes, hours or midnights), so the
// axis reads 00:00, 03:00... or one tick per day regardless of sample times.
function timeTicks(min, max, width) {
  const span = max - min;
  const narrow = width < 520;
  let unit;
  let step;
  if (span <= 30 * MINUTE) [unit, step] = ["minute", narrow ? 5 : 2];
  else if (span <= 3 * HOUR) [unit, step] = ["minute", narrow ? 30 : 15];
  else if (span <= 2 * DAY) [unit, step] = ["hour", narrow ? 6 : 3];
  else [unit, step] = ["day", narrow && span > 8 * DAY ? 2 : 1];

  const d = new Date(min);
  if (unit === "minute") {
    d.setSeconds(0, 0);
    d.setMinutes(Math.ceil(d.getMinutes() / step) * step);
  } else if (unit === "hour") {
    d.setMinutes(0, 0, 0);
    d.setHours(Math.ceil(d.getHours() / step) * step);
  } else {
    d.setHours(0, 0, 0, 0);
    if (d.getTime() < min) d.setDate(d.getDate() + 1);
  }
  const ticks = [];
  while (d.getTime() <= max && ticks.length < 100) {
    if (d.getTime() >= min) ticks.push(d.getTime());
    if (unit === "minute") d.setMinutes(d.getMinutes() + step);
    else if (unit === "hour") d.setHours(d.getHours() + step);
    else d.setDate(d.getDate() + step);
  }
  return { ticks, unit };
}

function tickLabel(value, unit) {
  const lang = getLanguage();
  const date = new Date(value);
  if (unit === "day") return date.toLocaleDateString(lang, { weekday: "short", day: "numeric" });
  return date.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
}

function pointTitle(value, span) {
  const lang = getLanguage();
  const date = new Date(value);
  if (span <= DAY + HOUR) {
    return date.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleString(lang, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function timeAxis(c, min, max) {
  let unit = "hour";
  return {
    type: "linear",
    min,
    max,
    afterBuildTicks: (scale) => {
      const built = timeTicks(scale.min, scale.max, scale.maxWidth || scale.width || 800);
      unit = built.unit;
      scale.ticks = built.ticks.map((value) => ({ value }));
    },
    ticks: {
      color: c.muted,
      maxRotation: 0,
      autoSkip: false,
      font: { size: 11 },
      callback: (value) => tickLabel(value, unit),
    },
    grid: { color: c.line, drawTicks: false },
    border: { display: false },
  };
}

// Break the line where samples are missing (app stopped, inverter offline)
// instead of drawing a straight segment across the gap.
export function withGaps(rows) {
  if (rows.length < 3) return rows;
  const diffs = rows
    .slice(1)
    .map((row, i) => row.t - rows[i].t)
    .sort((a, b) => a - b);
  const limit = Math.max(diffs[Math.floor(diffs.length / 2)] * 3, 15 * MINUTE);
  const out = [rows[0]];
  for (let i = 1; i < rows.length; i++) {
    if (rows[i].t - rows[i - 1].t > limit) out.push({ t: (rows[i].t + rows[i - 1].t) / 2, gap: true });
    out.push(rows[i]);
  }
  return out;
}

function points(rows, key, round = true) {
  return rows.map((row) => {
    const value = row.gap ? null : row[key];
    return { x: row.t, y: value == null ? null : round ? Math.round(value) : value };
  });
}

// ---------- Charts ----------

class BaseChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.chart = null;
    this.last = null;
    // Set while redrawing the same range with fresh data, to skip the animation.
    this.quiet = false;
  }

  render(config) {
    this.destroy();
    if (this.quiet) config.options.animation = false;
    this.chart = new window.Chart(this.canvas, config);
  }

  refreshTheme() {
    if (this.chart && this.last) this.show(...this.last);
  }

  destroy() {
    this.chart?.destroy();
    this.chart = null;
  }
}

// Power over time: solar, home, battery and grid in W on one axis.
export class PowerChart extends BaseChart {
  show(rows, { min, max, live = false } = {}) {
    this.last = [rows, { min, max, live }];
    const c = palette();
    const data = withGaps(rows);
    const datasets = POWER_SERIES.map((s) => {
      const color = token(s.color);
      return {
        label: t(s.label),
        data: points(data, s.key),
        borderColor: color,
        backgroundColor: s.fill ? rgba(color, 0.14) : color,
        fill: s.fill ? "origin" : false,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBorderWidth: 2,
        pointHoverBorderColor: c.panel,
        cubicInterpolationMode: "monotone",
        spanGaps: false,
        directions: s.signed,
      };
    });

    if (this.chart && live) {
      this.chart.data.datasets.forEach((ds, i) => {
        ds.data = datasets[i].data;
      });
      this.chart.options.scales.x.min = min;
      this.chart.options.scales.x.max = max;
      this.chart.update("none");
      return;
    }

    const span = max - min;
    this.render({
      type: "line",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: live ? false : { duration: 300 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: legendBase(c),
          tooltip: {
            ...tooltipBase(c),
            callbacks: {
              title: (items) => (items.length ? pointTitle(items[0].parsed.x, span) : ""),
              label: (ctx) => {
                const value = ctx.parsed.y;
                if (value == null) return null;
                const signed = ctx.dataset.directions;
                const direction =
                  signed && Math.abs(value) >= 5 ? ` · ${t(`history.direction.${signed[value > 0 ? 0 : 1]}`)}` : "";
                return ` ${ctx.dataset.label}: ${formatNumber(signed ? Math.abs(value) : value)} W${direction}`;
              },
            },
          },
        },
        scales: {
          x: timeAxis(c, min, max),
          y: valueAxis(c, (v) => `${formatNumber(v)} W`),
        },
      },
    });
  }
}

// Battery level as its own small chart instead of a second y-axis.
export class SocChart extends BaseChart {
  show(rows, { min, max, live = false } = {}) {
    this.last = [rows, { min, max, live }];
    const c = palette();
    const color = token("--battery");
    const data = points(withGaps(rows), "battery_soc_pct", false);

    if (this.chart && live) {
      this.chart.data.datasets[0].data = data;
      this.chart.options.scales.x.min = min;
      this.chart.options.scales.x.max = max;
      this.chart.update("none");
      return;
    }

    const span = max - min;
    this.render({
      type: "line",
      data: {
        datasets: [
          {
            label: t("series.battery_soc"),
            data,
            borderColor: color,
            backgroundColor: rgba(color, 0.12),
            fill: "origin",
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            cubicInterpolationMode: "monotone",
            spanGaps: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: live ? false : { duration: 300 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            ...tooltipBase(c),
            callbacks: {
              title: (items) => (items.length ? pointTitle(items[0].parsed.x, span) : ""),
              label: (ctx) => (ctx.parsed.y == null ? null : ` ${formatNumber(ctx.parsed.y)} %`),
            },
          },
        },
        scales: {
          x: { ...timeAxis(c, min, max), ticks: { display: false } },
          y: {
            ...valueAxis(c, (v) => `${v} %`),
            min: 0,
            max: 100,
            afterBuildTicks: (scale) => {
              scale.ticks = [0, 50, 100].map((value) => ({ value }));
            },
          },
        },
      },
    });
  }
}

// Energy per day or month (kWh): sources above zero, uses below.
export class EnergyChart extends BaseChart {
  show(periods, { titles }) {
    this.last = [periods, { titles }];
    const c = palette();
    const datasets = ENERGY_SERIES.map((s) => {
      const color = token(s.color);
      return {
        label: t(s.label),
        data: periods.map((p) => (p.row?.[s.key] == null ? null : s.sign * p.row[s.key])),
        backgroundColor: color,
        borderColor: c.panel,
        borderWidth: 1,
        borderRadius: 3,
        borderSkipped: false,
        maxBarThickness: 28,
        entity: s.entity,
      };
    });

    const toggle = (entity) => {
      const items = this.chart.data.datasets.map((ds, i) => [ds, i]).filter(([ds]) => ds.entity === entity);
      const hidden = items.every(([, i]) => !this.chart.isDatasetVisible(i));
      items.forEach(([, i]) => this.chart.setDatasetVisibility(i, hidden));
      this.chart.update();
    };

    const legend = legendBase(c);
    legend.labels.generateLabels = (chart) => {
      return ENTITIES.map((entity) => {
        const i = chart.data.datasets.findIndex((ds) => ds.entity === entity);
        const ds = chart.data.datasets[i];
        return {
          text: t(entity),
          fillStyle: ds.backgroundColor,
          strokeStyle: ds.backgroundColor,
          fontColor: c.muted,
          pointStyle: "rectRounded",
          hidden: !chart.isDatasetVisible(i),
          datasetIndex: i,
          entity,
        };
      });
    };
    legend.onClick = (_event, item) => toggle(item.entity);

    this.render({
      type: "bar",
      data: { labels: periods.map((p) => p.label), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend,
          tooltip: {
            ...tooltipBase(c),
            filter: (item) => item.parsed.y != null && Math.abs(item.parsed.y) >= 0.05,
            callbacks: {
              title: (items) => (items.length ? titles[items[0].dataIndex] : ""),
              label: (ctx) => ` ${ctx.dataset.label}: ${formatNumber(Math.abs(ctx.parsed.y), 1)} kWh`,
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            ticks: { color: c.muted, maxRotation: 0, autoSkip: true, font: { size: 11 } },
            grid: { display: false },
            border: { display: false },
          },
          y: { stacked: true, ...valueAxis(c, (v) => `${formatNumber(Math.abs(v))} kWh`) },
        },
      },
    });
  }
}
