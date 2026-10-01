import { esc } from "./format.js";
import { icon } from "./icons.js";

export function toast(message, kind = "info") {
  const host = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.innerHTML = `${icon(kind === "error" ? "alert" : "check")}<span>${esc(message)}</span>`;
  host.append(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 3200);
}

export function field({ label, name, type = "number", value = "", suffix = "", hint = "", attrs = "", dataType = "num" }) {
  return `
    <label class="field">
      <span class="field-label">${esc(label)}</span>
      <span class="input-wrap${suffix ? " has-suffix" : ""}">
        <input type="${type}" name="${name}" data-type="${dataType}" value="${esc(value)}" ${attrs} />
        ${suffix ? `<span class="suffix">${esc(suffix)}</span>` : ""}
      </span>
      ${hint ? `<span class="field-hint">${esc(hint)}</span>` : ""}
    </label>`;
}

export function switchInput(name, checked, label) {
  return `
    <label class="switch" title="${esc(label)}">
      <input type="checkbox" name="${name}" data-type="bool" ${checked ? "checked" : ""} aria-label="${esc(label)}" />
      <span class="switch-track"><span class="switch-thumb"></span></span>
    </label>`;
}

export function readForm(form) {
  const values = {};
  for (const input of form.querySelectorAll("[name]")) {
    const type = input.dataset.type;
    if (type === "bool") values[input.name] = input.checked;
    else if (type === "int") values[input.name] = input.value === "" ? null : Math.round(Number(input.value));
    else if (type === "num") values[input.name] = input.value === "" ? null : Number(input.value);
    else values[input.name] = input.value.trim();
  }
  return values;
}

export function emptyState(iconName, title, text = "") {
  return `
    <div class="empty">
      ${icon(iconName, "icon empty-icon")}
      <strong>${esc(title)}</strong>
      ${text ? `<p>${esc(text)}</p>` : ""}
    </div>`;
}
