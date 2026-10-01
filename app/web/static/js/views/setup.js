import { esc } from "../format.js";
import { t } from "../i18n.js";
import { loadInverters } from "../state.js";
import { bindInverterForm, inverterFormHtml } from "./inverter-form.js";

export function renderSetup(root) {
  root.innerHTML = `
    <div class="setup">
      <section class="card setup-card">
        <img src="/static/icon.svg" alt="" width="64" height="64" />
        <h1>${esc(t("setup.title"))}</h1>
        <p class="muted">${esc(t("setup.intro"))}</p>
        <p class="notice-text small">${esc(t("setup.scan_warning"))}</p>
        ${inverterFormHtml()}
      </section>
    </div>`;
  const form = root.querySelector("form");
  form.querySelector('[data-action="cancel"]').hidden = true;
  bindInverterForm(form, {
    onSaved: async () => {
      await loadInverters();
      window.location.hash = "#/";
    },
  });
  return () => {};
}
