import { api } from "../api.js";
import { CostChart } from "../charts.js";
import { esc, formatMoney } from "../format.js";
import { formatNumber, getLanguage, t } from "../i18n.js";
import { icon } from "../icons.js";
import { on, state } from "../state.js";
import { emptyState } from "../ui.js";

const REFRESH_MS = 5 * 60 * 1000;
const PERIODS = ["p1", "p2", "p3"];

// 0 is the billing period that contains today, -1 the one before, and so on.
let offset = 0;

function billingPeriod(now, billingDay, shift) {
  const day = Math.min(Math.max(Number(billingDay) || 1, 1), 28);
  let month = now.getMonth() + shift;
  if (now.getDate() < day) month -= 1;
  return {
    from: new Date(now.getFullYear(), month, day),
    to: new Date(now.getFullYear(), month + 1, day),
  };
}

function periodLabel({ from, to }) {
  const last = new Date(to.getFullYear(), to.getMonth(), to.getDate() - 1);
  const format = new Intl.DateTimeFormat(getLanguage(), { day: "numeric", month: "short", year: "numeric" });
  return format.formatRange ? format.formatRange(from, last) : `${format.format(from)} – ${format.format(last)}`;
}

function kwh(value) {
  return `${formatNumber(value, value >= 100 ? 0 : 1)} kWh`;
}

function billRows(totals) {
  const rows = [
    ["power", totals.power_eur],
    ["energy", totals.energy_eur],
    ["compensation", -totals.compensation_eur],
    ["fixed", totals.fixed_eur],
    ["electricity_tax", totals.electricity_tax_eur],
    ["vat", totals.vat_eur],
  ];
  return `
    <dl class="facts bill">
      ${rows.map(([key, value]) => `<div><dt>${esc(t(`costs.bill.${key}`))}</dt><dd>${esc(formatMoney(value))}</dd></div>`).join("")}
      <div class="bill-total"><dt>${esc(t("costs.bill.total"))}</dt><dd>${esc(formatMoney(totals.total_eur))}</dd></div>
    </dl>`;
}

function periodRows(periods) {
  const total = PERIODS.reduce((sum, key) => sum + periods[key].import_kwh, 0);
  return `
    <ul class="period-list">
      ${PERIODS.map((key) => {
        const share = total > 0 ? Math.round((periods[key].import_kwh / total) * 100) : 0;
        return `
          <li>
            <div class="row-between">
              <span><strong>${esc(t(`costs.periods.${key}`))}</strong> <small class="muted">${esc(t(`costs.periods.${key}_hours`))}</small></span>
              <span class="tabular">${esc(kwh(periods[key].import_kwh))} · ${esc(formatMoney(periods[key].energy_eur))}</span>
            </div>
            <div class="meter"><div class="meter-fill period-${key}" style="width:${share}%"></div></div>
          </li>`;
      }).join("")}
    </ul>
    <p class="muted small">${esc(t("costs.periods.caption"))}</p>`;
}

export function renderCosts(root) {
  root.innerHTML = `
    <div class="page costs">
      <div class="period-nav">
        <button type="button" class="icon-btn" data-action="prev" aria-label="${esc(t("costs.previous"))}">${icon("chevronLeft")}</button>
        <strong data-v="label"></strong>
        <button type="button" class="icon-btn" data-action="next" aria-label="${esc(t("costs.next"))}">${icon("chevronRight")}</button>
      </div>
      <div data-v="body"><div class="skeleton"></div></div>
    </div>`;

  const $ = (key) => root.querySelector(`[data-v="${key}"]`);
  const body = $("body");
  const prev = root.querySelector('[data-action="prev"]');
  const next = root.querySelector('[data-action="next"]');
  let chart = null;
  let loadToken = 0;

  function renderResult(result, quiet) {
    chart?.destroy();
    chart = null;
    if (!result.has_tariff) {
      body.innerHTML = `
        ${emptyState("euro", t("costs.no_tariff"), t("costs.no_tariff_text"))}
        <div class="center"><a class="btn btn-primary" href="#/settings/tariff">${icon("sliders")}${esc(t("costs.set_tariff"))}</a></div>`;
      return;
    }
    const { totals, projected } = result;
    const current = offset === 0;
    const lang = getLanguage();
    const days = result.days.map((day) => {
      const date = new Date(`${day.date}T00:00:00`);
      return {
        label: String(date.getDate()),
        title: date.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" }),
        row: day,
      };
    });

    body.innerHTML = `
      ${result.missing_tariff_days ? `<a class="notice" href="#/settings/tariff">${icon("alert")}<span>${esc(t("costs.missing_tariff", { count: result.missing_tariff_days }))}</span>${icon("chevronRight")}</a>` : ""}
      <section class="card cost-hero">
        <span class="muted">${esc(t(current ? "costs.so_far" : "costs.period_total"))}</span>
        <strong class="cost-total">${esc(formatMoney(totals.total_eur))}</strong>
        ${current && projected ? `<p class="muted">${esc(t("costs.projected", { amount_eur: projected.total_eur }))}</p>` : ""}
      </section>
      <section class="stat-strip cost-strip">
        <div><span>${esc(t("costs.imported"))}</span><strong>${esc(kwh(totals.import_kwh))}</strong></div>
        <div><span>${esc(t("costs.exported"))}</span><strong>${esc(kwh(totals.export_kwh))}</strong></div>
        <div><span>${esc(t("costs.savings"))}</span><strong>${esc(formatMoney(totals.savings_eur))}</strong></div>
      </section>
      ${totals.surplus_lost_eur >= 0.01 ? `<div class="notice">${icon("sun")}<span>${esc(t("costs.surplus_lost", { amount_eur: totals.surplus_lost_eur }))}</span></div>` : ""}
      <div class="cost-grid">
        <section class="card">
          <h2>${esc(t("costs.bill_title"))}</h2>
          ${billRows(totals)}
          <p class="muted small">${esc(t("costs.without_solar", { amount_eur: result.without_solar.total_eur }))}</p>
        </section>
        <section class="card">
          <h2>${esc(t("costs.periods_title"))}</h2>
          ${periodRows(result.periods)}
        </section>
      </div>
      <section class="card chart-card">
        <h2 class="chart-title">${esc(t("costs.daily_title"))}</h2>
        <div class="chart-wrap cost-chart"><canvas></canvas></div>
        <p class="chart-caption muted small">${esc(t("costs.daily_caption"))}</p>
      </section>
      <p class="muted small">${esc(t("costs.disclaimer"))}</p>`;

    chart = new CostChart(body.querySelector("canvas"));
    chart.quiet = quiet;
    chart.show(days, { titles: days.map((day) => day.title) });
  }

  async function load({ quiet = false } = {}) {
    const token = ++loadToken;
    const period = billingPeriod(new Date(), state.settings.billing_day, offset);
    $("label").textContent = periodLabel(period);
    next.disabled = offset >= 0;
    if (!state.selectedId) return;
    if (!quiet) body.innerHTML = '<div class="skeleton"></div>';
    const params = new URLSearchParams({
      inverter_id: String(state.selectedId),
      from: period.from.toISOString(),
      to: period.to.toISOString(),
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    });
    try {
      const result = await api.get(`/api/costs?${params}`);
      if (token !== loadToken) return;
      renderResult(result, quiet);
    } catch (error) {
      if (token === loadToken) body.innerHTML = emptyState("alert", t("costs.load_failed"), error.message);
    }
  }

  prev.addEventListener("click", () => {
    offset -= 1;
    load();
  });
  next.addEventListener("click", () => {
    offset = Math.min(0, offset + 1);
    load();
  });

  load();
  const timer = setInterval(() => {
    if (offset === 0 && document.visibilityState === "visible") load({ quiet: true });
  }, REFRESH_MS);
  const onTheme = () => chart?.refreshTheme();
  window.addEventListener("themechange", onTheme);
  const offs = [on("inverter", () => load()), on("settings", () => load())];
  return () => {
    clearInterval(timer);
    offs.forEach((off) => off());
    window.removeEventListener("themechange", onTheme);
    chart?.destroy();
  };
}
