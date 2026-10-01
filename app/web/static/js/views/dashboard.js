import { esc, formatHours, formatPercent, formatPower, formatTime } from "../format.js";
import { t } from "../i18n.js";
import { icon } from "../icons.js";
import { currentInverter, on, state } from "../state.js";

const flowSvg = () => `
  <svg class="flow-diagram" viewBox="0 0 460 390" aria-hidden="true">
    <line class="flow-track" x1="117" y1="120" x2="230" y2="185"/>
    <line class="flow-track" x1="343" y1="120" x2="230" y2="185"/>
    <line class="flow-track" x1="230" y1="315" x2="230" y2="185"/>
    <line class="flow-anim flow-color-solar" data-flow="solar" x1="117" y1="120" x2="230" y2="185"/>
    <line class="flow-anim flow-color-grid" data-flow="grid-import" x1="343" y1="120" x2="230" y2="185"/>
    <line class="flow-anim flow-color-grid" data-flow="grid-export" x1="230" y1="185" x2="343" y2="120"/>
    <line class="flow-anim flow-color-battery" data-flow="bat-discharge" x1="230" y1="315" x2="230" y2="185"/>
    <line class="flow-anim flow-color-battery" data-flow="bat-charge" x1="230" y1="185" x2="230" y2="315"/>
    <circle class="flow-node node-solar" cx="117" cy="120" r="46"/>
    <text class="flow-icon" x="117" y="108">☀️</text>
    <text class="flow-watts" x="117" y="131" data-v="flow-pv">-- W</text>
    <text class="flow-label" x="117" y="184">${esc(t("dashboard.solar"))}</text>
    <circle class="flow-node node-grid" cx="343" cy="120" r="46"/>
    <text class="flow-icon" x="343" y="108">⚡</text>
    <text class="flow-watts" x="343" y="131" data-v="flow-grid">-- W</text>
    <text class="flow-label" x="343" y="184">${esc(t("dashboard.grid"))}</text>
    <circle class="flow-node node-home" cx="230" cy="185" r="46"/>
    <text class="flow-icon" x="230" y="173">🏠</text>
    <text class="flow-watts" x="230" y="196" data-v="flow-load">-- W</text>
    <text class="flow-label" x="230" y="249">${esc(t("dashboard.home"))}</text>
    <circle class="flow-node node-battery" cx="230" cy="315" r="46"/>
    <text class="flow-icon" x="230" y="300">🔋</text>
    <text class="flow-watts" x="230" y="321" data-v="flow-bat">-- W</text>
    <text class="flow-soc" x="230" y="338" data-v="flow-soc">-- %</text>
    <text class="flow-label" x="230" y="380">${esc(t("dashboard.battery"))}</text>
  </svg>`;

const tile = (kind, iconName, label, extra = "") => `
  <article class="tile tile-${kind}">
    <div class="tile-head"><span class="tile-icon">${icon(iconName)}</span><span>${esc(label)}</span></div>
    <strong class="tile-value" data-v="${kind}">-- W</strong>
    <span class="tile-sub" data-v="${kind}-sub">&nbsp;</span>
    ${extra}
  </article>`;

const meter = (kind) =>
  `<div class="meter" data-v="${kind}-meter-wrap"><span class="meter-fill" data-v="${kind}-meter"></span></div>`;

function alertBanner(alerts) {
  if (!alerts.length) return "";
  return alerts
    .map(
      (alert) => `
      <a class="banner" href="#/alerts">
        ${icon("alert")}
        <span><strong>${esc(t(`alerts.${alert.kind}.name`))}</strong>
        <span>${esc(alert.params ? t(`alerts.${alert.kind}.fire.body`, alert.params) : alert.message)}</span></span>
        ${icon("chevronRight", "icon banner-go")}
      </a>`
    )
    .join("");
}

export function renderDashboard(root) {
  root.innerHTML = `
    <div class="page dashboard">
      <div class="banners" data-v="banners">${alertBanner(state.activeAlerts)}</div>
      <div class="dash-grid">
        <section class="card flow-card">
          <header class="card-head">
            <h2>${esc(t("dashboard.energy_flow"))}</h2>
            <span class="muted small" data-v="updated">${esc(t("dashboard.waiting"))}</span>
          </header>
          <div class="flow-wrap">${flowSvg()}</div>
        </section>
        <div class="tiles">
          ${tile("pv", "sun", t("dashboard.solar"))}
          ${tile("load", "home", t("dashboard.home"))}
          ${tile("bat", "battery", t("dashboard.battery"), meter("bat"))}
          ${tile("grid", "plug", t("dashboard.grid"), meter("grid"))}
        </div>
      </div>
      <section class="stat-strip">
        <div><span>${esc(t("dashboard.inverter_output"))}</span><strong data-v="inv">-- W</strong></div>
        <div><span>${esc(t("dashboard.latency"))}</span><strong data-v="latency">-- ms</strong></div>
        <div><span>${esc(t("dashboard.address"))}</span><strong data-v="address">--</strong></div>
      </section>
    </div>`;

  const $ = (key) => root.querySelector(`[data-v="${key}"]`);
  const setText = (key, text) => {
    const el = $(key);
    if (el) el.textContent = text;
  };

  function setFlow(name, active, power) {
    const el = root.querySelector(`[data-flow="${name}"]`);
    if (!el) return;
    el.classList.toggle("active", active);
    if (active) el.style.animationDuration = `${Math.max(0.4, 2.8 - (power / 3000) * 2.4).toFixed(2)}s`;
  }

  function updateAddress() {
    const inverter = currentInverter();
    setText("address", inverter ? `${inverter.host}:${inverter.port}` : "--");
  }

  function update(data) {
    if (!data) return;
    const pv = Number(data.pv_power_w || 0);
    const load = Number(data.load_power_w || 0);
    const bat = Number(data.battery_power_w || 0);
    const grid = Number(data.grid_power_w || 0);
    const soc = data.battery_soc_pct;
    const capacity = currentInverter()?.battery_capacity_kwh || null;

    setText("updated", t("dashboard.updated", { time: formatTime(data.t) }));

    setText("flow-pv", formatPower(pv));
    setText("flow-load", formatPower(load));
    setText("flow-bat", formatPower(Math.abs(bat)));
    setText("flow-grid", formatPower(Math.abs(grid)));
    setText("flow-soc", formatPercent(soc));
    setFlow("solar", pv > 5, pv);
    setFlow("grid-import", grid > 5, grid);
    setFlow("grid-export", grid < -5, -grid);
    setFlow("bat-discharge", bat > 5, bat);
    setFlow("bat-charge", bat < -5, -bat);

    setText("pv", formatPower(data.pv_power_w));
    setText("pv-sub", load > 0 ? t("dashboard.solar_share", { percent: Math.round(Math.min(1, pv / load) * 100) }) : " ");

    setText("load", formatPower(data.load_power_w));
    const own = load > 0 ? Math.max(0, Math.min(1, (load - Math.max(grid, 0)) / load)) : null;
    setText("load-sub", own == null ? " " : t("dashboard.self_sufficiency", { percent: Math.round(own * 100) }));

    setText("bat", formatPercent(soc));
    let batSub = t("dashboard.battery_idle", { power: formatPower(Math.abs(bat)) });
    if (bat > 10) {
      const hours = capacity && soc != null ? ((soc / 100) * capacity) / (bat / 1000) : null;
      batSub = hours != null
        ? t("dashboard.battery_discharging_eta", { power: formatPower(bat), time: formatHours(hours) })
        : t("dashboard.battery_discharging", { power: formatPower(bat) });
    } else if (bat < -10) {
      const hours = capacity && soc != null ? (((100 - soc) / 100) * capacity) / (-bat / 1000) : null;
      batSub = hours != null
        ? t("dashboard.battery_charging_eta", { power: formatPower(-bat), time: formatHours(hours) })
        : t("dashboard.battery_charging", { power: formatPower(-bat) });
    }
    setText("bat-sub", batSub);
    const batMeter = $("bat-meter");
    if (batMeter) batMeter.style.width = `${Math.max(0, Math.min(100, Number(soc) || 0))}%`;

    setText("grid", formatPower(Math.abs(grid)));
    const direction = grid > 5 ? "importing" : grid < -5 ? "exporting" : "idle";
    const limit = state.settings.alert_overload_enabled ? Number(state.settings.alert_overload_limit_w) : 0;
    const gridMeterWrap = $("grid-meter-wrap");
    const gridMeter = $("grid-meter");
    if (limit > 0) {
      const ratio = Math.max(0, grid) / limit;
      setText(
        "grid-sub",
        `${t(`dashboard.grid_${direction}`)} · ${t("dashboard.of_limit", { percent: Math.round(ratio * 100), limit_w: limit })}`
      );
      gridMeterWrap.hidden = false;
      gridMeter.style.width = `${Math.min(100, ratio * 100)}%`;
      gridMeter.dataset.level = ratio >= 1 ? "over" : ratio >= 0.85 ? "high" : "ok";
    } else {
      setText("grid-sub", t(`dashboard.grid_${direction}`));
      gridMeterWrap.hidden = true;
    }

    setText("inv", formatPower(data.inverter_power_w));
    setText("latency", data.latency_ms == null ? "-- ms" : `${Math.round(data.latency_ms)} ms`);
  }

  updateAddress();
  update(state.latest);

  const unsubscribe = [
    on("sample", update),
    on("inverter", () => {
      updateAddress();
      setText("updated", t("dashboard.waiting"));
    }),
    on("inverters", updateAddress),
    on("alerts", (alerts) => {
      $("banners").innerHTML = alertBanner(alerts);
    }),
    on("settings", () => update(state.latest)),
  ];
  return () => unsubscribe.forEach((off) => off());
}
