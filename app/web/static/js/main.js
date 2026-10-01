import { esc } from "./format.js";
import { initI18n, t } from "./i18n.js";
import { icon } from "./icons.js";
import { connectLive, preloadSamples } from "./live.js";
import {
  loadDrivers,
  loadInverters,
  loadSettings,
  on,
  refreshActiveAlerts,
  selectInverter,
  state,
} from "./state.js";
import { applyTheme } from "./theme.js";
import { renderAlerts } from "./views/alerts.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderHistory } from "./views/history.js";
import { renderSettings } from "./views/settings.js";
import { renderSetup } from "./views/setup.js";

const NAV = [
  { route: "dashboard", href: "#/", icon: "home" },
  { route: "history", href: "#/history", icon: "chart" },
  { route: "alerts", href: "#/alerts", icon: "bell" },
  { route: "settings", href: "#/settings", icon: "sliders" },
];

const VIEWS = {
  dashboard: renderDashboard,
  history: renderHistory,
  alerts: renderAlerts,
  settings: renderSettings,
  setup: renderSetup,
};

const view = document.getElementById("view");
let cleanup = null;
let currentRoute = null;

function parseRoute() {
  const [name = "", param = null] = window.location.hash.replace(/^#\/?/, "").split("/");
  return { name: name || "dashboard", param };
}

function renderNav(active) {
  const badge = state.activeAlerts.length;
  const items = NAV.map(
    (item) => `
      <a href="${item.href}" class="nav-item ${item.route === active ? "active" : ""}" ${item.route === active ? 'aria-current="page"' : ""}>
        <span class="nav-icon">${icon(item.icon)}${item.route === "alerts" && badge ? `<span class="badge">${badge}</span>` : ""}</span>
        <span class="nav-label">${esc(t(`nav.${item.route}`))}</span>
      </a>`
  ).join("");
  document.getElementById("nav").innerHTML = items;
  document.getElementById("tabbar").innerHTML = items;
}

function renderConnection() {
  const { status, message } = state.connection;
  const label = t(`connection.${status}`);
  for (const el of document.querySelectorAll("[data-connection]")) {
    el.dataset.status = status;
    el.title = message || label;
    el.innerHTML = `<span class="dot"></span><span class="conn-label">${esc(label)}</span>`;
  }
}

function renderInverterPicker() {
  const picker = document.getElementById("inverter-picker");
  picker.hidden = state.inverters.length < 2;
  picker.innerHTML = state.inverters
    .map((inv) => `<option value="${inv.id}" ${inv.id === state.selectedId ? "selected" : ""}>${esc(inv.name)}</option>`)
    .join("");
  picker.setAttribute("aria-label", t("common.inverter"));
}

function route() {
  const { name, param } = parseRoute();
  if (!state.inverters.length && name !== "setup" && name !== "settings") {
    window.location.replace("#/setup");
    return;
  }
  if (name === "setup" && state.inverters.length) {
    window.location.replace("#/");
    return;
  }
  const render = VIEWS[name] || VIEWS.dashboard;
  const routeName = VIEWS[name] ? name : "dashboard";
  cleanup?.();
  currentRoute = routeName;
  document.body.dataset.route = routeName;
  document.getElementById("page-title").textContent = routeName === "setup" ? "Grid Monitor" : t(`nav.${routeName}`);
  document.title = routeName === "dashboard" ? "Grid Monitor" : `${t(`nav.${routeName}`)} · Grid Monitor`;
  renderNav(routeName);
  cleanup = render(view, param) || null;
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function renderChrome() {
  renderConnection();
  renderInverterPicker();
  renderNav(currentRoute);
}

async function boot() {
  applyTheme();
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme());
  await initI18n();
  await Promise.all([loadDrivers(), loadSettings(), loadInverters()]);
  state.version = await fetch("/health")
    .then((res) => res.json())
    .then((health) => health.version)
    .catch(() => null);

  document.getElementById("inverter-picker").addEventListener("change", (event) => {
    selectInverter(Number(event.target.value));
  });
  on("connection", renderConnection);
  on("alerts", () => renderNav(currentRoute));
  on("inverters", () => {
    renderInverterPicker();
    preloadSamples();
  });
  on("inverter", () => {
    renderInverterPicker();
    preloadSamples();
  });
  on("language", () => {
    renderChrome();
    route();
  });
  window.addEventListener("hashchange", route);

  renderChrome();
  route();
  document.body.classList.remove("booting");

  connectLive();
  preloadSamples();
  refreshActiveAlerts();
  setInterval(refreshActiveAlerts, 30 * 1000);
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

boot().catch((error) => {
  view.innerHTML = `<div class="empty">${icon("alert", "icon empty-icon")}<strong>Grid Monitor</strong><p>${esc(error.message)}</p></div>`;
  document.body.classList.remove("booting");
});
