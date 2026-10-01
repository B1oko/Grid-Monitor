import { api } from "./api.js";
import { t } from "./i18n.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Runs a LAN scan and reports progress through onStatus(text) and the final
// candidate list through the returned promise.
export async function discoverInverters(onStatus) {
  onStatus(t("discovery.scanning"));
  await api.post("/api/discover");
  for (let i = 0; i < 60; i += 1) {
    const payload = await api.get("/api/discovery");
    const result = payload.result;
    if (payload.in_progress) {
      onStatus(t("discovery.scanning"));
      await sleep(1500);
      continue;
    }
    if (!result || result.status === "not_found") {
      onStatus(t("discovery.not_found"));
      return [];
    }
    if (result.status === "error") {
      onStatus(t("discovery.error", { detail: result.message || "" }));
      return [];
    }
    const candidates = result.candidates || [];
    onStatus(t("discovery.found", { count: candidates.length }));
    return candidates;
  }
  onStatus(t("discovery.timeout"));
  return [];
}
