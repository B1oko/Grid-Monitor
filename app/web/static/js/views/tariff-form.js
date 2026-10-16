import { api } from "../api.js";
import { esc } from "../format.js";
import { t } from "../i18n.js";
import { icon } from "../icons.js";
import { state } from "../state.js";
import { field, readForm, toast } from "../ui.js";

const ENERGY_PRICE = "min=0 max=10 step=any required";

export function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

// A new tariff starts from a copy of the latest one, or from typical Spanish
// taxes and the contracted power set for the overload alert.
function defaults(latest) {
  if (latest) return { ...latest, valid_from: today() };
  const contracted = Number(state.settings.alert_overload_limit_w || 0) / 1000 || "";
  return {
    valid_from: today(),
    contracted_power_p1_kw: contracted,
    contracted_power_p2_kw: contracted,
    export_price: 0,
    fixed_daily: 0,
    electricity_tax_pct: 5.11,
    vat_pct: 21,
  };
}

export function tariffFormHtml(tariff = null, latest = null) {
  const values = tariff || defaults(latest);
  const v = (key) => values[key] ?? "";
  const price = (key, suffix, attrs = ENERGY_PRICE, hint = "") =>
    field({ label: t(`tariff.${key}`), name: key, value: v(key), suffix, attrs, hint });
  return `
    <form class="form tariff-form" novalidate>
      <div class="form-grid">
        ${field({ label: t("tariff.valid_from"), name: "valid_from", type: "date", dataType: "text", value: v("valid_from"), hint: t("tariff.valid_from_hint"), attrs: "required" })}
      </div>
      <h4 class="form-subtitle">${esc(t("tariff.energy_title"))}</h4>
      <p class="muted small">${esc(t("tariff.energy_hint"))}</p>
      <div class="form-grid">
        ${price("energy_price_p1", "€/kWh")}
        ${price("energy_price_p2", "€/kWh")}
        ${price("energy_price_p3", "€/kWh")}
      </div>
      <h4 class="form-subtitle">${esc(t("tariff.power_title"))}</h4>
      <p class="muted small">${esc(t("tariff.power_hint"))}</p>
      <div class="form-grid">
        ${price("contracted_power_p1_kw", "kW", "min=0 max=100 step=any required")}
        ${price("power_price_p1", "€/kW")}
        ${price("contracted_power_p2_kw", "kW", "min=0 max=100 step=any required")}
        ${price("power_price_p2", "€/kW")}
      </div>
      <h4 class="form-subtitle">${esc(t("tariff.other_title"))}</h4>
      <div class="form-grid">
        ${price("export_price", "€/kWh", ENERGY_PRICE, t("tariff.export_price_hint"))}
        ${price("fixed_daily", `€/${t("tariff.per_day")}`, "min=0 max=100 step=any required", t("tariff.fixed_daily_hint"))}
        ${price("electricity_tax_pct", "%", "min=0 max=100 step=any required")}
        ${price("vat_pct", "%", "min=0 max=100 step=any required")}
      </div>
      <div class="form-actions">
        <button type="submit" class="btn btn-primary">${icon("check")}${esc(t(tariff ? "common.save" : "tariff.add"))}</button>
        <button type="button" class="btn btn-ghost" data-action="cancel">${esc(t("common.cancel"))}</button>
      </div>
    </form>`;
}

export function bindTariffForm(form, { tariff = null, onSaved, onCancel }) {
  form.querySelector('[data-action="cancel"]').addEventListener("click", () => onCancel?.());
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const values = readForm(form);
      if (tariff) await api.put(`/api/tariffs/${tariff.id}`, values);
      else await api.post("/api/tariffs", values);
      toast(t("tariff.saved"));
      await onSaved?.();
    } catch (error) {
      toast(t("common.save_failed", { detail: error.message }), "error");
      submit.disabled = false;
    }
  });
}
