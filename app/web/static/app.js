const elements = {
  status: document.getElementById("status"),
  statusText: document.getElementById("status-text"),
  lastUpdate: document.getElementById("last-update"),
  inverterHost: document.getElementById("inverter-host"),
  inverterSelect: document.getElementById("inverter-select"),
  discoverButton: document.getElementById("discover-button"),
  addInverterButton: document.getElementById("add-inverter-button"),
  loadPower: document.getElementById("load-power"),
  pvPower: document.getElementById("pv-power"),
  batteryPower: document.getElementById("battery-power"),
  batteryPercent: document.getElementById("battery-percent"),
  batteryEstimate: document.getElementById("battery-estimate"),
  gridPower: document.getElementById("grid-power"),
  inverterPower: document.getElementById("inverter-power"),
  totalGridPower: document.getElementById("total-grid-power"),
  gridVa: document.getElementById("grid-va"),
  inverterVa: document.getElementById("inverter-va"),
  latency: document.getElementById("latency"),
  themeToggle: document.getElementById("theme-toggle"),
  settingsOpen: document.getElementById("settings-open"),
  settingsClose: document.getElementById("settings-close"),
  settingsModal: document.getElementById("settings-modal"),
  settingsForm: document.getElementById("settings-form"),
  settingsStatus: document.getElementById("settings-status"),
  deleteInverter: document.getElementById("delete-inverter"),
  wizard: document.getElementById("wizard"),
  wizardScan: document.getElementById("wizard-scan"),
  wizardManual: document.getElementById("wizard-manual"),
  wizardStatus: document.getElementById("wizard-status"),
  wizardCandidates: document.getElementById("wizard-candidates"),
  wizardForm: document.getElementById("wizard-form"),
  dashboard: document.getElementById("dashboard"),
};

const samples = [];
const maxAgeMs = 10 * 60 * 1000;
let socket;
let reconnectTimer;
let discoveryPollTimer = null;
let batteryCapacityKwh = 10.0;
let inverters = [];
let selectedInverterId = null;
let appSettings = {};
let drivers = [];

function currentInverter() {
  return inverters.find((item) => item.id === selectedInverterId) || null;
}

function initTheme() {
  const stored = localStorage.getItem("theme");
  if (stored) document.documentElement.setAttribute("data-theme", stored);
  updateThemeButton();
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  let next;
  if (current === "dark") next = "light";
  else if (current === "light") next = "dark";
  else next = systemDark ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  updateThemeButton();
}

function updateThemeButton() {
  const theme = document.documentElement.getAttribute("data-theme");
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = theme === "dark" || (!theme && systemDark);
  elements.themeToggle.textContent = isDark ? "☀" : "◑";
  elements.themeToggle.setAttribute("aria-label", isDark ? "Light mode" : "Dark mode");
}

async function loadDrivers() {
  const res = await fetch("/api/drivers");
  if (!res.ok) return;
  drivers = await res.json();
  const select = document.getElementById("wizard-driver");
  select.innerHTML = "";
  for (const driver of drivers) {
    select.appendChild(new Option(`${driver.name} (${driver.id})`, driver.id));
  }
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  if (!res.ok) return;
  appSettings = await res.json();
}

async function loadInverters() {
  const res = await fetch("/api/inverters");
  if (!res.ok) throw new Error("Could not load inverters");
  inverters = await res.json();
  renderInverterSelect();
  if (!inverters.length) {
    showWizard(true);
    return;
  }
  showWizard(false);
  if (!selectedInverterId || !inverters.some((item) => item.id === selectedInverterId)) {
    selectedInverterId = inverters[0].id;
  }
  elements.inverterSelect.value = String(selectedInverterId);
  applySelectedInverter();
}

function renderInverterSelect() {
  const select = elements.inverterSelect;
  select.innerHTML = "";
  for (const inverter of inverters) {
    select.appendChild(new Option(inverter.name, String(inverter.id)));
  }
}

function applySelectedInverter() {
  const inverter = currentInverter();
  if (!inverter) {
    elements.inverterHost.textContent = "--";
    return;
  }
  elements.inverterHost.textContent = `${inverter.host}:${inverter.port}`;
  batteryCapacityKwh = inverter.battery_capacity_kwh ?? 10.0;
  samples.length = 0;
  if (activeRange === "live") preloadLiveSamples();
  else loadHistory(activeRange);
}

function showWizard(visible) {
  elements.wizard.hidden = !visible;
  elements.dashboard.style.display = visible ? "none" : "";
}

function fillWizardForm(candidate) {
  elements.wizardForm.hidden = false;
  document.getElementById("wizard-name").value = candidate
    ? `${candidate.driver_id} @ ${candidate.host}`
    : "Inverter";
  if (candidate?.driver_id) document.getElementById("wizard-driver").value = candidate.driver_id;
  document.getElementById("wizard-host").value = candidate?.host || "";
  document.getElementById("wizard-port").value = String(candidate?.port || 502);
}

async function runDiscovery(statusEl, candidatesEl) {
  statusEl.textContent = "Scanning local network…";
  candidatesEl.innerHTML = "";
  elements.discoverButton.disabled = true;
  elements.wizardScan.disabled = true;
  try {
    const response = await fetch("/api/discover", { method: "POST" });
    if (!response.ok) throw new Error("Could not start discovery");
    await pollDiscovery(statusEl, candidatesEl);
  } catch (error) {
    statusEl.textContent = error.message || "Scan failed";
  } finally {
    elements.discoverButton.disabled = false;
    elements.wizardScan.disabled = false;
  }
}

async function pollDiscovery(statusEl, candidatesEl) {
  for (let i = 0; i < 40; i += 1) {
    const response = await fetch("/api/discovery");
    if (!response.ok) throw new Error("Could not read discovery status");
    const payload = await response.json();
    const result = payload.result;
    if (payload.in_progress) {
      statusEl.textContent = result?.message || "Scanning…";
      await new Promise((resolve) => {
        discoveryPollTimer = setTimeout(resolve, 1500);
      });
      continue;
    }
    if (!result || result.status === "not_found") {
      statusEl.textContent = "No inverter found. Add one manually.";
      return;
    }
    if (result.status === "error") {
      statusEl.textContent = result.message || "Scan failed";
      return;
    }
    statusEl.textContent = result.message || "Found candidates";
    renderCandidates(candidatesEl, result.candidates || []);
    return;
  }
  statusEl.textContent = "Scan timed out";
}

function renderCandidates(container, candidates) {
  container.innerHTML = "";
  for (const candidate of candidates) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "candidate-button";
    button.textContent = `${candidate.driver_id} · ${candidate.host}:${candidate.port} · ${candidate.latency_ms} ms`;
    button.addEventListener("click", () => fillWizardForm(candidate));
    container.appendChild(button);
  }
}

async function submitWizard(event) {
  event.preventDefault();
  const body = {
    name: document.getElementById("wizard-name").value.trim(),
    driver_id: document.getElementById("wizard-driver").value,
    host: document.getElementById("wizard-host").value.trim(),
    port: Number(document.getElementById("wizard-port").value || 502),
    unit_id: Number(document.getElementById("wizard-unit").value || 1),
    battery_capacity_kwh: document.getElementById("wizard-battery").value
      ? Number(document.getElementById("wizard-battery").value)
      : null,
    enabled: true,
  };
  elements.wizardStatus.textContent = "Saving…";
  const response = await fetch("/api/inverters", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    elements.wizardStatus.textContent = detail.detail || "Could not save inverter";
    return;
  }
  const created = await response.json();
  selectedInverterId = created.id;
  await loadInverters();
}

function openSettings() {
  const inverter = currentInverter();
  if (!inverter) {
    showWizard(true);
    return;
  }
  document.getElementById("set-name").value = inverter.name;
  document.getElementById("set-host").value = inverter.host;
  document.getElementById("set-port").value = String(inverter.port);
  document.getElementById("set-poll").value = String(Math.round(inverter.poll_interval_s));
  document.getElementById("set-battery").value = inverter.battery_capacity_kwh ?? "";
  document.getElementById("set-recorder").value = appSettings.recorder_interval_seconds ?? 300;
  document.getElementById("set-retention").value = appSettings.retention_days ?? 365;
  document.getElementById("set-downsample").value = appSettings.downsample_after_days ?? 30;
  document.getElementById("set-timezone").value = appSettings.timezone ?? "UTC";
  elements.settingsStatus.textContent = "";
  elements.settingsModal.hidden = false;
}

function closeSettings() {
  elements.settingsModal.hidden = true;
}

async function saveSettings(event) {
  event.preventDefault();
  const inverter = currentInverter();
  if (!inverter) return;
  elements.settingsStatus.textContent = "Saving…";
  const inverterRes = await fetch(`/api/inverters/${inverter.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: document.getElementById("set-name").value.trim(),
      host: document.getElementById("set-host").value.trim(),
      port: Number(document.getElementById("set-port").value),
      poll_interval_s: Number(document.getElementById("set-poll").value),
      battery_capacity_kwh: document.getElementById("set-battery").value
        ? Number(document.getElementById("set-battery").value)
        : null,
    }),
  });
  const settingsRes = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      recorder_interval_seconds: Number(document.getElementById("set-recorder").value),
      retention_days: Number(document.getElementById("set-retention").value),
      downsample_after_days: Number(document.getElementById("set-downsample").value),
      timezone: document.getElementById("set-timezone").value.trim() || "UTC",
    }),
  });
  if (!inverterRes.ok || !settingsRes.ok) {
    elements.settingsStatus.textContent = "Could not save settings";
    return;
  }
  await loadSettings();
  await loadInverters();
  elements.settingsStatus.textContent = "Saved";
  setTimeout(closeSettings, 600);
}

async function deleteSelectedInverter() {
  const inverter = currentInverter();
  if (!inverter) return;
  if (!window.confirm(`Remove ${inverter.name}? History for this inverter will be deleted.`)) return;
  const response = await fetch(`/api/inverters/${inverter.id}`, { method: "DELETE" });
  if (!response.ok) {
    elements.settingsStatus.textContent = "Could not delete inverter";
    return;
  }
  selectedInverterId = null;
  closeSettings();
  await loadInverters();
}

function formatDuration(hours) {
  if (!isFinite(hours) || hours > 99) return ">99h";
  const h = Math.floor(hours);
  const m = Math.round((hours - h) * 60);
  if (h === 0) return `${m}min`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}min`;
}

function getDischargeDuration(soc, powerW) {
  if (powerW <= 10 || soc <= 0) return null;
  const remainKwh = (soc / 100) * batteryCapacityKwh;
  return remainKwh / (powerW / 1000);
}

function updateBatteryEstimate(data) {
  const power = Number(data.battery_power_w || 0);
  const soc = Number(data.battery_soc_pct || 0);
  const el = elements.batteryEstimate;
  if (Math.abs(power) < 10) {
    el.textContent = "Idle";
    el.className = "battery-estimate";
    return;
  }
  if (power > 0) {
    const hours = getDischargeDuration(soc, power);
    el.textContent = `Discharging · ${formatDuration(hours)}`;
    el.className = "battery-estimate discharging";
  } else {
    const emptyKwh = ((100 - soc) / 100) * batteryCapacityKwh;
    const hours = emptyKwh / (Math.abs(power) / 1000);
    el.textContent = `Charging · ${formatDuration(hours)}`;
    el.className = "battery-estimate charging";
  }
}

function setFlowActive(id, active, power) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("active", active);
  if (active && power > 0) {
    const dur = Math.max(0.4, 2.8 - (power / 3000) * 2.4);
    el.style.animationDuration = `${dur.toFixed(2)}s`;
  }
}

function updateFlowDiagram(data) {
  const pv = Number(data.pv_power_w || 0);
  const grid = Number(data.grid_power_w || 0);
  const bat = Number(data.battery_power_w || 0);
  const load = Number(data.load_power_w || 0);
  const soc = Number(data.battery_soc_pct || 0);

  const fmtAbs = (v) => formatPower(Math.abs(v));
  document.getElementById("flow-pv-watts").textContent = formatPower(pv);
  document.getElementById("flow-grid-watts").textContent = fmtAbs(grid);
  document.getElementById("flow-load-watts").textContent = formatPower(load);
  document.getElementById("flow-bat-watts").textContent = fmtAbs(bat);
  document.getElementById("flow-bat-soc").textContent = formatPercent(soc);

  const batTimeEl = document.getElementById("flow-bat-time");
  const dischargeHours = getDischargeDuration(soc, bat);
  if (dischargeHours !== null) {
    batTimeEl.textContent = `~ ${formatDuration(dischargeHours)}`;
    batTimeEl.classList.add("discharging");
  } else {
    batTimeEl.textContent = "";
    batTimeEl.classList.remove("discharging");
  }

  setFlowActive("flo-solar", pv > 5, pv);
  setFlowActive("flo-grid-import", grid > 5, grid);
  setFlowActive("flo-grid-export", grid < -5, Math.abs(grid));
  setFlowActive("flo-bat-discharge", bat > 5, bat);
  setFlowActive("flo-bat-charge", bat < -5, Math.abs(bat));
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function formatPower(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "-- W";
  return `${Number(value).toLocaleString("en-US")} W`;
}

function formatPercent(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "-- %";
  return `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 1 })} %`;
}

function setStatus(text, state) {
  elements.statusText.textContent = text;
  elements.status.className = `status ${state || ""}`.trim();
}

function connect() {
  clearTimeout(reconnectTimer);
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${window.location.host}/ws/live`);
  setStatus("Connecting", "");

  socket.addEventListener("open", () => {
    setStatus("Connected", "connected");
    socket.send("hello");
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.inverter_id != null && selectedInverterId != null && message.inverter_id !== selectedInverterId) {
      return;
    }
    if (message.type === "sample") {
      handleSample(message.data);
    } else if (message.type === "error") {
      setStatus("Modbus error", "error");
      elements.lastUpdate.textContent = message.data.message || "No data";
    }
  });

  socket.addEventListener("close", scheduleReconnect);
  socket.addEventListener("error", () => setStatus("Reconnecting", "error"));
}

function scheduleReconnect() {
  setStatus("Reconnecting", "error");
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, 2500);
}

function handleSample(data) {
  const now = Date.parse(data.timestamp) || Date.now();
  samples.push({ t: now, ...data });
  while (samples.length && now - samples[0].t > maxAgeMs) samples.shift();

  const extra = data.extra || {};
  elements.loadPower.textContent = formatPower(data.load_power_w);
  elements.pvPower.textContent = formatPower(data.pv_power_w);
  elements.batteryPower.textContent = formatPower(data.battery_power_w);
  elements.batteryPercent.textContent = formatPercent(data.battery_soc_pct);
  elements.gridPower.textContent = formatPower(data.grid_power_w);
  elements.inverterPower.textContent = formatPower(data.inverter_power_w);
  elements.totalGridPower.textContent = formatPower(extra.total_grid_power_w);
  elements.gridVa.textContent = `${extra.total_grid_power_va ?? "--"} VA`;
  elements.inverterVa.textContent = `${extra.inverter_power_va ?? "--"} VA`;
  elements.latency.textContent = `${data.latency_ms ?? "--"} ms`;
  elements.lastUpdate.textContent = new Date(now).toLocaleString();
  setStatus("Connected", "connected");

  updateBatteryEstimate(data);
  updateFlowDiagram(data);
  if (activeRange === "live") updateLiveChart();
}

const SERIES = [
  { label: "Solar", key: "pv_power_w", color: "#d49c24", yAxisID: "yW" },
  { label: "Home", key: "load_power_w", color: "#2f6f73", yAxisID: "yW" },
  { label: "Battery", key: "battery_power_w", color: "#5f8f45", yAxisID: "yW" },
  { label: "Grid", key: "grid_power_w", color: "#b65d4c", yAxisID: "yW" },
  { label: "Battery SoC", key: "battery_soc_pct", color: "#8864c8", yAxisID: "yPct" },
];

let chart = null;
let chartMode = null;

function getChartTheme() {
  const attr = document.documentElement.getAttribute("data-theme");
  const sysDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = attr === "dark" || (!attr && sysDark);
  return {
    ink: isDark ? "#e4ede6" : "#18211d",
    muted: isDark ? "#7d9481" : "#66706a",
    gridLine: isDark ? "#283228" : "#d9dfd8",
    tooltipBg: isDark ? "#182019" : "#ffffff",
  };
}

function buildDatasets(data, isBar) {
  return SERIES.map(({ label, key, color, yAxisID }) => {
    const isSoC = yAxisID === "yPct";
    const values = data.map((d) => {
      const raw = d[key];
      return raw != null ? (isSoC ? raw : Math.round(raw)) : null;
    });
    return {
      label,
      data: values,
      type: isBar && isSoC ? "line" : undefined,
      yAxisID,
      borderColor: color,
      backgroundColor: !isBar && !isSoC ? hexToRgba(color, 0.13)
        : isBar && !isSoC ? `${color}cc`
          : "transparent",
      fill: !isBar && !isSoC,
      borderDash: isSoC ? [5, 5] : undefined,
      tension: 0.35,
      borderWidth: isSoC ? 1.5 : 2,
      pointRadius: 0,
      pointHoverRadius: 4,
    };
  });
}

function buildChartOptions(isBar, theme) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        labels: { color: theme.muted, boxWidth: 11, padding: 16, font: { size: 13 }, usePointStyle: true },
      },
      tooltip: {
        backgroundColor: theme.tooltipBg,
        borderColor: theme.gridLine,
        borderWidth: 1,
        titleColor: theme.muted,
        bodyColor: theme.ink,
        padding: 10,
        callbacks: {
          label: (ctx) => {
            if (ctx.parsed.y == null) return null;
            const isSoC = ctx.dataset.yAxisID === "yPct";
            return isSoC
              ? ` ${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString("en-US", { maximumFractionDigits: 1 })} %`
              : ` ${ctx.dataset.label}: ${Math.round(ctx.parsed.y).toLocaleString("en-US")} W`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: theme.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: isBar ? 15 : 8, font: { size: 12 } },
        grid: { color: theme.gridLine },
      },
      yW: {
        type: "linear",
        position: "left",
        ticks: {
          color: theme.muted,
          font: { size: 12 },
          callback: (v) => `${v.toLocaleString("en-US")} W`,
        },
        grid: { color: theme.gridLine },
      },
      yPct: {
        type: "linear",
        position: "right",
        min: 0,
        max: 100,
        ticks: {
          color: theme.muted,
          font: { size: 12 },
          callback: (v) => `${v} %`,
          stepSize: 25,
        },
        grid: { drawOnChartArea: false },
      },
    },
  };
}

function createChart(type, labels, datasets, isLive) {
  if (chart) { chart.destroy(); chart = null; }
  const canvas = document.getElementById("main-chart");
  const theme = getChartTheme();
  const isBar = type === "bar";
  const options = buildChartOptions(isBar, theme);
  if (!isLive) options.animation = { duration: 400 };
  chart = new Chart(canvas, { type, data: { labels, datasets }, options });
  chartMode = `${type}-${isLive ? "live" : "hist"}`;
}

function updateChartTheme() {
  if (!chart) return;
  const theme = getChartTheme();
  const p = chart.options.plugins;
  p.legend.labels.color = theme.muted;
  p.tooltip.backgroundColor = theme.tooltipBg;
  p.tooltip.borderColor = theme.gridLine;
  p.tooltip.titleColor = theme.muted;
  p.tooltip.bodyColor = theme.ink;
  const s = chart.options.scales;
  s.x.ticks.color = theme.muted;
  s.x.grid.color = theme.gridLine;
  s.yW.ticks.color = theme.muted;
  s.yW.grid.color = theme.gridLine;
  s.yPct.ticks.color = theme.muted;
  chart.update("none");
}

function updateLiveChart() {
  if (activeRange !== "live") return;
  const emptyEl = document.getElementById("chart-empty");

  if (samples.length < 2) {
    emptyEl.textContent = "Waiting for samples…";
    emptyEl.hidden = false;
    if (chart && chartMode === "line-live") { chart.destroy(); chart = null; chartMode = null; }
    return;
  }
  emptyEl.hidden = true;

  const labels = samples.map((s) =>
    new Date(s.t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
  );
  const datasets = buildDatasets(samples, false);

  if (chartMode === "line-live" && chart) {
    chart.data.labels = labels;
    datasets.forEach((ds, i) => { chart.data.datasets[i].data = ds.data; });
    chart.update("none");
  } else {
    createChart("line", labels, datasets, true);
  }
}

async function preloadLiveSamples() {
  if (!selectedInverterId) return;
  try {
    const to = new Date();
    const from = new Date(to.getTime() - 10 * 60 * 1000);
    const params = new URLSearchParams({
      inverter_id: String(selectedInverterId),
      from: from.toISOString(),
      to: to.toISOString(),
      resolution: "minute",
    });
    const res = await fetch(`/api/history?${params}`);
    if (!res.ok) return;
    const data = await res.json();
    if (!data.length) return;

    const now = Date.now();
    samples.length = 0;
    for (const d of data) {
      const t = Date.parse(d.ts);
      if (t > now - maxAgeMs) samples.push({ t, ...d });
    }
    samples.sort((a, b) => a.t - b.t);
    updateLiveChart();
  } catch {
    // live WebSocket data will fill in
  }
}

let activeRange = "live";
let historyLoading = false;

const CHART_TITLES = {
  live: "Live power",
  today: "Power — Today",
  yesterday: "Power — Yesterday",
  "7d": "Power — Last 7 days",
  "30d": "Power — Last 30 days",
  month: "Power — This month",
  year: "Power — This year",
};

const RANGES = {
  today: () => {
    const from = new Date(); from.setHours(0, 0, 0, 0);
    return { from, to: new Date(), resolution: "minute" };
  },
  yesterday: () => {
    const from = new Date(); from.setDate(from.getDate() - 1); from.setHours(0, 0, 0, 0);
    const to = new Date(from); to.setHours(23, 59, 59, 999);
    return { from, to, resolution: "hour" };
  },
  "7d": () => {
    const to = new Date();
    const from = new Date(to); from.setDate(from.getDate() - 7);
    return { from, to, resolution: "hour" };
  },
  "30d": () => {
    const to = new Date();
    const from = new Date(to); from.setDate(from.getDate() - 30);
    return { from, to, resolution: "day" };
  },
  month: () => {
    const now = new Date();
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from, to: now, resolution: "day" };
  },
  year: () => {
    const now = new Date();
    const from = new Date(now.getFullYear(), 0, 1);
    return { from, to: now, resolution: "month" };
  },
};

function formatHistoryLabel(isoTs, resolution) {
  const d = new Date(isoTs);
  if (resolution === "minute") return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (resolution === "hour") return d.toLocaleString(undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  if (resolution === "day") return d.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" });
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

async function loadHistory(range) {
  if (historyLoading || !selectedInverterId) return;
  historyLoading = true;
  document.querySelectorAll(".range-btn").forEach((btn) => { btn.disabled = true; });
  const emptyEl = document.getElementById("chart-empty");
  emptyEl.textContent = "No data for this period";
  emptyEl.hidden = true;

  const { from, to, resolution } = RANGES[range]();
  const params = new URLSearchParams({
    inverter_id: String(selectedInverterId),
    from: from.toISOString(),
    to: to.toISOString(),
    resolution,
  });

  try {
    const res = await fetch(`/api/history?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.length) {
      if (chart) { chart.destroy(); chart = null; chartMode = null; }
      emptyEl.textContent = "No data for this period";
      emptyEl.hidden = false;
      return;
    }

    emptyEl.hidden = true;
    const isLine = resolution === "minute" || resolution === "hour";
    const labels = data.map((d) => formatHistoryLabel(d.ts, resolution));
    const datasets = buildDatasets(data, !isLine);
    createChart(isLine ? "line" : "bar", labels, datasets, false);
  } catch (err) {
    if (chart) { chart.destroy(); chart = null; chartMode = null; }
    emptyEl.textContent = `Could not load data: ${err.message}`;
    emptyEl.hidden = false;
  } finally {
    historyLoading = false;
    document.querySelectorAll(".range-btn").forEach((btn) => { btn.disabled = false; });
  }
}

function selectRange(range) {
  activeRange = range;
  document.querySelectorAll(".range-btn").forEach((btn) =>
    btn.classList.toggle("active", btn.dataset.range === range)
  );
  document.getElementById("chart-title").textContent = CHART_TITLES[range] ?? "Power";
  document.getElementById("chart-empty").hidden = true;

  if (range === "live") {
    if (samples.length >= 2) updateLiveChart();
    else preloadLiveSamples();
  } else {
    loadHistory(range);
  }
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { });
}

window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  updateThemeButton();
  updateChartTheme();
});
elements.themeToggle.addEventListener("click", () => {
  toggleTheme();
  updateChartTheme();
});
elements.discoverButton.addEventListener("click", () => {
  showWizard(true);
  runDiscovery(elements.wizardStatus, elements.wizardCandidates);
});
elements.addInverterButton.addEventListener("click", () => {
  showWizard(true);
  fillWizardForm(null);
});
elements.inverterSelect.addEventListener("change", () => {
  selectedInverterId = Number(elements.inverterSelect.value);
  applySelectedInverter();
});
elements.wizardScan.addEventListener("click", () => {
  runDiscovery(elements.wizardStatus, elements.wizardCandidates);
});
elements.wizardManual.addEventListener("click", () => fillWizardForm(null));
elements.wizardForm.addEventListener("submit", submitWizard);
elements.settingsOpen.addEventListener("click", openSettings);
elements.settingsClose.addEventListener("click", closeSettings);
elements.settingsForm.addEventListener("submit", saveSettings);
elements.deleteInverter.addEventListener("click", deleteSelectedInverter);

document.querySelectorAll(".range-btn").forEach((btn) =>
  btn.addEventListener("click", () => selectRange(btn.dataset.range))
);

initTheme();
(async () => {
  await loadDrivers();
  await loadSettings();
  await loadInverters();
  connect();
})();
