import { api } from "./api.js";

export const state = {
  drivers: [],
  inverters: [],
  settings: {},
  selectedId: null,
  latest: null,
  samples: [],
  connection: { status: "connecting", message: null },
  activeAlerts: [],
  version: null,
};

const listeners = new Map();

export function on(event, handler) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(handler);
  return () => listeners.get(event)?.delete(handler);
}

export function emit(event, payload) {
  for (const handler of listeners.get(event) || []) handler(payload);
}

export function currentInverter() {
  return state.inverters.find((item) => item.id === state.selectedId) || null;
}

export function selectInverter(id) {
  if (id === state.selectedId) return;
  state.selectedId = id;
  state.latest = null;
  state.samples.length = 0;
  try {
    localStorage.setItem("inverter", String(id));
  } catch {
    // Ignore.
  }
  emit("inverter", currentInverter());
}

export async function loadDrivers() {
  state.drivers = await api.get("/api/drivers");
}

export async function loadSettings() {
  state.settings = await api.get("/api/settings");
  emit("settings", state.settings);
}

export async function saveSettings(values) {
  state.settings = await api.put("/api/settings", values);
  emit("settings", state.settings);
  return state.settings;
}

export async function loadInverters() {
  state.inverters = await api.get("/api/inverters");
  if (!state.inverters.some((item) => item.id === state.selectedId)) {
    let stored = null;
    try {
      stored = Number(localStorage.getItem("inverter"));
    } catch {
      // Ignore.
    }
    const preferred = state.inverters.find((item) => item.id === stored) || state.inverters[0];
    state.selectedId = preferred ? preferred.id : null;
    state.latest = null;
    state.samples.length = 0;
  }
  emit("inverters", state.inverters);
}

export async function refreshActiveAlerts() {
  try {
    state.activeAlerts = await api.get("/api/alerts?active=true&limit=20");
    emit("alerts", state.activeAlerts);
  } catch {
    // Offline or restarting: keep the previous list.
  }
}
