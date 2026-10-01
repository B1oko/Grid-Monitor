const CACHE = "grid-monitor-v4";
const PRECACHE = [
  "/",
  "/manifest.json",
  "/static/icon.svg",
  "/static/css/app.css",
  "/static/vendor/chart.umd.min.js",
  "/static/js/main.js",
  "/static/js/api.js",
  "/static/js/charts.js",
  "/static/js/discovery.js",
  "/static/js/format.js",
  "/static/js/i18n.js",
  "/static/js/icons.js",
  "/static/js/live.js",
  "/static/js/push.js",
  "/static/js/state.js",
  "/static/js/theme.js",
  "/static/js/ui.js",
  "/static/js/views/alerts.js",
  "/static/js/views/dashboard.js",
  "/static/js/views/history.js",
  "/static/js/views/inverter-form.js",
  "/static/js/views/settings.js",
  "/static/js/views/setup.js",
  "/i18n/languages.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network first, so a new release is picked up immediately; the cache is only
// a fallback when the server cannot be reached.
self.addEventListener("fetch", (e) => {
  const { pathname } = new URL(e.request.url);
  if (e.request.method !== "GET" || pathname.startsWith("/ws/") || pathname.startsWith("/api/")) return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const clone = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

self.addEventListener("push", (e) => {
  let data = {};
  try {
    data = e.data ? e.data.json() : {};
  } catch {
    data = { body: e.data ? e.data.text() : "" };
  }
  e.waitUntil(
    self.registration.showNotification(data.title || "Grid Monitor", {
      body: data.body || "",
      tag: data.tag || undefined,
      renotify: Boolean(data.tag),
      icon: "/static/icon.svg",
      badge: "/static/icon.svg",
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "/", self.location.origin).href;
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ("focus" in client) {
          return client.focus().then((focused) => ("navigate" in focused ? focused.navigate(url) : focused));
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
