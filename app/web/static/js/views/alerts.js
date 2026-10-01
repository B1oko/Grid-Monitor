import { api } from "../api.js";
import { esc, formatDateTime } from "../format.js";
import { formatDurationMinutes, t } from "../i18n.js";
import { icon } from "../icons.js";
import { disablePush, enablePush, pushStatus, sendTestPush } from "../push.js";
import { on, state } from "../state.js";
import { emptyState, toast } from "../ui.js";

const KIND_ICONS = { overload: "bolt", no_production: "sun", offline: "wifiOff" };

function alertBody(alert) {
  return alert.params ? t(`alerts.${alert.kind}.fire.body`, alert.params) : alert.message;
}

function alertItem(alert) {
  const active = !alert.resolved_at;
  const end = active ? Date.now() : Date.parse(alert.resolved_at);
  const minutes = (end - Date.parse(alert.started_at)) / 60000;
  const inverter = state.inverters.length > 1 && alert.params?.inverter ? `${alert.params.inverter} · ` : "";
  return `
    <li class="alert-item ${active ? "is-active" : ""}">
      <span class="alert-icon kind-${esc(alert.kind)}">${icon(KIND_ICONS[alert.kind] || "alert")}</span>
      <div class="alert-text">
        <div class="alert-title">
          <strong>${esc(t(`alerts.${alert.kind}.name`))}</strong>
          ${active ? `<span class="pill pill-danger">${esc(t("alerts.active"))}</span>` : ""}
        </div>
        <p>${esc(alertBody(alert))}</p>
        <small>${esc(inverter)}${esc(formatDateTime(alert.started_at))} · ${esc(
          active
            ? t("alerts.ongoing_for", { duration_min: minutes })
            : t("alerts.lasted", { duration_min: minutes })
        )}</small>
      </div>
    </li>`;
}

function deviceCopy(status) {
  if (status.support === "insecure") return { tone: "warn", text: t("push.status.insecure") };
  if (status.support === "unsupported") return { tone: "warn", text: t("push.status.unsupported") };
  if (status.permission === "denied") return { tone: "warn", text: t("push.status.blocked") };
  if (status.subscribed) return { tone: "ok", text: t("push.status.on") };
  return { tone: "off", text: t("push.status.off") };
}

export function renderAlerts(root) {
  root.innerHTML = `
    <div class="page alerts">
      <section class="card device-card">
        <div class="device-head">
          <span class="device-icon" data-v="device-icon">${icon("bell")}</span>
          <div>
            <h2>${esc(t("push.title"))}</h2>
            <p class="muted" data-v="device-text">…</p>
          </div>
        </div>
        <div class="button-row">
          <button type="button" class="btn btn-primary" data-v="toggle" disabled>…</button>
          <button type="button" class="btn" data-v="test" disabled>${icon("send")}${esc(t("push.send_test"))}</button>
          <a class="btn btn-ghost" href="#/settings/alerts">${icon("sliders")}${esc(t("alerts.configure"))}</a>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">${esc(t("alerts.active_title"))}</h2>
        <div data-v="active"></div>
      </section>

      <section class="section">
        <h2 class="section-title">${esc(t("alerts.history_title"))}</h2>
        <div data-v="history"><div class="skeleton"></div></div>
      </section>
    </div>`;

  const $ = (key) => root.querySelector(`[data-v="${key}"]`);
  const toggle = $("toggle");
  const test = $("test");

  async function refreshDevice() {
    const status = await pushStatus();
    const copy = deviceCopy(status);
    $("device-text").textContent = copy.text;
    $("device-icon").dataset.tone = copy.tone;
    $("device-icon").innerHTML = icon(status.subscribed ? "bell" : "bellOff");
    const usable = status.support === "ok" && status.permission !== "denied";
    toggle.disabled = !usable;
    toggle.innerHTML = status.subscribed
      ? `${icon("bellOff")}${esc(t("push.disable"))}`
      : `${icon("bell")}${esc(t("push.enable"))}`;
    toggle.classList.toggle("btn-primary", !status.subscribed);
    toggle.dataset.subscribed = status.subscribed ? "1" : "";
    test.disabled = !status.subscribed;
  }

  function renderActive(alerts) {
    $("active").innerHTML = alerts.length
      ? `<ul class="alert-list">${alerts.map(alertItem).join("")}</ul>`
      : emptyState("checkCircle", t("alerts.all_clear"), t("alerts.all_clear_text"));
  }

  async function loadHistory() {
    try {
      const alerts = await api.get("/api/alerts?limit=100");
      const past = alerts.filter((alert) => alert.resolved_at);
      $("history").innerHTML = past.length
        ? `<ul class="alert-list">${past.map(alertItem).join("")}</ul>`
        : emptyState("bell", t("alerts.no_history"));
    } catch (error) {
      $("history").innerHTML = emptyState("alert", t("alerts.load_failed"), error.message);
    }
  }

  toggle.addEventListener("click", async () => {
    toggle.disabled = true;
    try {
      if (toggle.dataset.subscribed) {
        await disablePush();
        toast(t("push.disabled_toast"));
      } else if (await enablePush()) {
        toast(t("push.enabled_toast"));
      }
    } catch (error) {
      toast(t("push.change_failed", { detail: error.message }), "error");
    }
    await refreshDevice();
  });

  test.addEventListener("click", async () => {
    test.disabled = true;
    try {
      const delivered = await sendTestPush();
      toast(delivered ? t("push.test_sent", { count: delivered }) : t("push.test_none"), delivered ? "info" : "error");
    } catch (error) {
      toast(t("push.test_failed", { detail: error.message }), "error");
    }
    test.disabled = false;
  });

  refreshDevice();
  renderActive(state.activeAlerts);
  loadHistory();
  const off = on("alerts", (alerts) => {
    renderActive(alerts);
    loadHistory();
  });
  return off;
}
