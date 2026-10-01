import { formatNumber, t } from "./i18n.js";
import { isDark } from "./theme.js";

const SERIES = [
  { key: "pv_power_w", label: "series.solar", color: "#d49c24", axis: "yW" },
  { key: "load_power_w", label: "series.home", color: "#2f6f73", axis: "yW" },
  { key: "battery_power_w", label: "series.battery", color: "#5f8f45", axis: "yW" },
  { key: "grid_power_w", label: "series.grid", color: "#b65d4c", axis: "yW" },
  { key: "battery_soc_pct", label: "series.battery_soc", color: "#8864c8", axis: "yPct" },
];

function rgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

function palette() {
  const dark = isDark();
  return {
    ink: dark ? "#e4ede6" : "#18211d",
    muted: dark ? "#8aa08e" : "#66706a",
    line: dark ? "#263027" : "#e3e8e1",
    tooltip: dark ? "#182019" : "#ffffff",
  };
}

function datasets(rows, isBar) {
  return SERIES.map(({ key, label, color, axis }) => {
    const soc = axis === "yPct";
    return {
      label: t(label),
      data: rows.map((row) => (row[key] == null ? null : soc ? row[key] : Math.round(row[key]))),
      type: isBar && soc ? "line" : undefined,
      yAxisID: axis,
      borderColor: color,
      backgroundColor: soc ? "transparent" : isBar ? rgba(color, 0.8) : rgba(color, 0.12),
      fill: !isBar && !soc,
      borderDash: soc ? [5, 5] : undefined,
      tension: 0.35,
      borderWidth: soc ? 1.5 : 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      borderRadius: isBar ? 4 : 0,
    };
  });
}

function options(isBar, live) {
  const c = palette();
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: live ? false : { duration: 350 },
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: c.muted, boxWidth: 10, padding: 14, usePointStyle: true, font: { size: 12 } },
      },
      tooltip: {
        backgroundColor: c.tooltip,
        borderColor: c.line,
        borderWidth: 1,
        titleColor: c.muted,
        bodyColor: c.ink,
        padding: 10,
        callbacks: {
          label: (ctx) => {
            if (ctx.parsed.y == null) return null;
            const unit = ctx.dataset.yAxisID === "yPct" ? "%" : "W";
            return ` ${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)} ${unit}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: c.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: isBar ? 12 : 7, font: { size: 11 } },
        grid: { display: false },
      },
      yW: {
        position: "left",
        ticks: { color: c.muted, font: { size: 11 }, callback: (v) => `${formatNumber(v)} W` },
        grid: { color: c.line },
        border: { display: false },
      },
      yPct: {
        position: "right",
        min: 0,
        max: 100,
        ticks: { color: c.muted, font: { size: 11 }, stepSize: 25, callback: (v) => `${v} %` },
        grid: { drawOnChartArea: false },
        border: { display: false },
      },
    },
  };
}

export class PowerChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.chart = null;
    this.mode = null;
  }

  show(rows, labels, { bar = false, live = false } = {}) {
    const mode = `${bar ? "bar" : "line"}-${live ? "live" : "history"}`;
    if (this.chart && this.mode === mode && live) {
      this.chart.data.labels = labels;
      datasets(rows, bar).forEach((ds, i) => {
        this.chart.data.datasets[i].data = ds.data;
      });
      this.chart.update("none");
      return;
    }
    this.destroy();
    this.chart = new window.Chart(this.canvas, {
      type: bar ? "bar" : "line",
      data: { labels, datasets: datasets(rows, bar) },
      options: options(bar, live),
    });
    this.mode = mode;
  }

  refreshTheme() {
    if (!this.chart) return;
    const fresh = options(this.mode.startsWith("bar"), this.mode.endsWith("live"));
    this.chart.options.plugins = fresh.plugins;
    this.chart.options.scales = fresh.scales;
    this.chart.update("none");
  }

  destroy() {
    this.chart?.destroy();
    this.chart = null;
    this.mode = null;
  }
}
