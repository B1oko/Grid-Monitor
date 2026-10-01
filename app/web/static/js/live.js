import { api } from "./api.js";
import { emit, state } from "./state.js";

const MAX_AGE_MS = 10 * 60 * 1000;
let socket = null;
let reconnectTimer = null;

function setConnection(status, message = null) {
  state.connection = { status, message };
  emit("connection", state.connection);
}

function handleSample(data) {
  const t = Date.parse(data.timestamp) || Date.now();
  state.latest = { ...data, t };
  state.samples.push({ ...data, t });
  while (state.samples.length && t - state.samples[0].t > MAX_AGE_MS) state.samples.shift();
  if (state.connection.status !== "connected") setConnection("connected");
  emit("sample", state.latest);
}

export function connectLive() {
  clearTimeout(reconnectTimer);
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${window.location.host}/ws/live`);
  setConnection("connecting");

  socket.addEventListener("open", () => {
    setConnection("connected");
    socket.send("hello");
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.inverter_id != null && message.inverter_id !== state.selectedId) return;
    if (message.type === "sample") handleSample(message.data);
    else if (message.type === "error") setConnection("error", message.data?.message || null);
  });
  socket.addEventListener("close", () => {
    setConnection("reconnecting");
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectLive, 2500);
  });
}

export async function preloadSamples() {
  if (!state.selectedId) return;
  const to = new Date();
  const from = new Date(to.getTime() - MAX_AGE_MS);
  const params = new URLSearchParams({
    inverter_id: String(state.selectedId),
    from: from.toISOString(),
    to: to.toISOString(),
    resolution: "minute",
  });
  try {
    const rows = await api.get(`/api/history?${params}`);
    const now = Date.now();
    const recent = rows
      .map((row) => ({ ...row, t: Date.parse(row.ts) }))
      .filter((row) => row.t > now - MAX_AGE_MS);
    const live = state.samples.filter((row) => !recent.some((r) => r.t === row.t));
    state.samples.splice(0, state.samples.length, ...[...recent, ...live].sort((a, b) => a.t - b.t));
    emit("samples", state.samples);
  } catch {
    // Live data will fill in.
  }
}
