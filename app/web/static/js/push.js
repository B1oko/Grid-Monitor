import { api } from "./api.js";
import { getLanguage } from "./i18n.js";

function base64ToBytes(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function pushSupport() {
  if (!window.isSecureContext) return "insecure";
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return "unsupported";
  }
  return "ok";
}

async function currentSubscription() {
  if (pushSupport() !== "ok") return null;
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

export async function pushStatus() {
  const support = pushSupport();
  if (support !== "ok") return { support, subscribed: false, permission: "default" };
  return {
    support,
    subscribed: Boolean(await currentSubscription()),
    permission: Notification.permission,
  };
}

async function register(subscription) {
  await api.post("/api/push/subscribe", { ...subscription.toJSON(), language: getLanguage() });
}

export async function enablePush() {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;
  const { public_key: key } = await api.get("/api/push/public-key");
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64ToBytes(key),
  });
  await register(subscription);
  return true;
}

export async function disablePush() {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api.post("/api/push/unsubscribe", { endpoint: subscription.endpoint });
  await subscription.unsubscribe();
}

export async function sendTestPush() {
  const { delivered } = await api.post("/api/push/test");
  return delivered;
}

// Notifications are rendered on the server in the language stored with the
// subscription, so tell the server when this device changes language.
export async function syncPushLanguage() {
  try {
    const subscription = await currentSubscription();
    if (subscription) await register(subscription);
  } catch {
    // Not critical.
  }
}
