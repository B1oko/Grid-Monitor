import { api } from "../api.js";
import { PowerChart } from "../charts.js";
import { esc } from "../format.js";
import { getLanguage, t } from "../i18n.js";
import { on, state } from "../state.js";
import { emptyState } from "../ui.js";

const RANGES = {
  live: null,
  today: () => {
    const from = new Date();
    from.setHours(0, 0, 0, 0);
    return { from, to: new Date(), resolution: "minute" };
  },
  yesterday: () => {
    const from = new Date();
    from.setDate(from.getDate() - 1);
    from.setHours(0, 0, 0, 0);
    const to = new Date(from);
    to.setHours(23, 59, 59, 999);
    return { from, to, resolution: "hour" };
  },
  "7d": () => {
    const to = new Date();
    const from = new Date(to);
    from.setDate(from.getDate() - 7);
    return { from, to, resolution: "hour" };
  },
  "30d": () => {
    const to = new Date();
    const from = new Date(to);
    from.setDate(from.getDate() - 30);
    return { from, to, resolution: "day" };
  },
  month: () => {
    const now = new Date();
    return { from: new Date(now.getFullYear(), now.getMonth(), 1), to: now, resolution: "day" };
  },
  year: () => {
    const now = new Date();
    return { from: new Date(now.getFullYear(), 0, 1), to: now, resolution: "month" };
  },
};

let activeRange = "live";

function label(ts, resolution) {
  const date = new Date(ts);
  const lang = getLanguage();
  if (resolution === "minute") return date.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
  if (resolution === "hour") {
    return date.toLocaleString(lang, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  if (resolution === "day") return date.toLocaleDateString(lang, { day: "2-digit", month: "2-digit" });
  return date.toLocaleDateString(lang, { month: "short", year: "numeric" });
}

export function renderHistory(root) {
  root.innerHTML = `
    <div class="page history">
      <div class="segmented scroll-x" role="tablist" aria-label="${esc(t("history.range"))}">
        ${Object.keys(RANGES)
          .map(
            (key) =>
              `<button type="button" role="tab" data-range="${key}" class="${key === activeRange ? "active" : ""}">
                ${key === "live" ? '<span class="live-dot"></span>' : ""}${esc(t(`history.ranges.${key}`))}
              </button>`
          )
          .join("")}
      </div>
      <section class="card chart-card">
        <div class="chart-wrap">
          <canvas></canvas>
          <div class="chart-empty" hidden></div>
        </div>
      </section>
    </div>`;

  const chart = new PowerChart(root.querySelector("canvas"));
  const empty = root.querySelector(".chart-empty");
  let loadToken = 0;

  function showEmpty(title, text = "") {
    chart.destroy();
    empty.innerHTML = emptyState("chart", title, text);
    empty.hidden = false;
  }

  function drawLive() {
    if (activeRange !== "live") return;
    if (state.samples.length < 2) {
      showEmpty(t("history.waiting"));
      return;
    }
    empty.hidden = true;
    chart.show(
      state.samples,
      state.samples.map((row) => label(row.t, "minute")),
      { live: true }
    );
  }

  async function loadRange(range) {
    const token = ++loadToken;
    if (range === "live") {
      drawLive();
      return;
    }
    if (!state.selectedId) return;
    const { from, to, resolution } = RANGES[range]();
    const params = new URLSearchParams({
      inverter_id: String(state.selectedId),
      from: from.toISOString(),
      to: to.toISOString(),
      resolution,
    });
    try {
      const rows = await api.get(`/api/history?${params}`);
      if (token !== loadToken) return;
      if (!rows.length) {
        showEmpty(t("history.no_data"));
        return;
      }
      empty.hidden = true;
      const bar = resolution === "day" || resolution === "month";
      chart.show(rows, rows.map((row) => label(row.ts, resolution)), { bar });
    } catch (error) {
      if (token === loadToken) showEmpty(t("history.load_failed"), error.message);
    }
  }

  root.querySelectorAll("[data-range]").forEach((button) =>
    button.addEventListener("click", () => {
      activeRange = button.dataset.range;
      root.querySelectorAll("[data-range]").forEach((b) => b.classList.toggle("active", b === button));
      loadRange(activeRange);
    })
  );

  loadRange(activeRange);
  const onTheme = () => chart.refreshTheme();
  window.addEventListener("themechange", onTheme);
  const offs = [
    on("sample", drawLive),
    on("samples", drawLive),
    on("inverter", () => loadRange(activeRange)),
  ];
  return () => {
    offs.forEach((off) => off());
    window.removeEventListener("themechange", onTheme);
    chart.destroy();
  };
}
