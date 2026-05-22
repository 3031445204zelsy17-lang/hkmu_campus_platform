import { api, isLoggedIn } from "../api.js";
import { get as storageGet, set as storageSet } from "./storage.js";

const VAPID_KEY_STORAGE = "push_vapid_key";

async function getVapidPublicKey() {
  const cached = storageGet(VAPID_KEY_STORAGE);
  if (cached) return cached;

  try {
    const res = await api.get("/push/vapid-key");
    storageSet(VAPID_KEY_STORAGE, res.public_key);
    return res.public_key;
  } catch {
    return null;
  }
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from(rawData.split("").map((c) => c.charCodeAt(0)));
}

export async function subscribePush() {
  if (!isLoggedIn()) return false;
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;

  const registration = await navigator.serviceWorker?.ready;
  if (!registration) return false;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;

  const vapidKey = await getVapidPublicKey();
  if (!vapidKey) return false;

  try {
    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });
    }

    await api.post("/push/subscribe", {
      subscription: subscription.toJSON(),
    });

    return true;
  } catch (err) {
    console.warn("[push] Subscription failed:", err);
    return false;
  }
}

export async function unsubscribePush() {
  if (!("serviceWorker" in navigator)) return;

  const registration = await navigator.serviceWorker?.ready;
  if (!registration) return;

  try {
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await api.post("/push/unsubscribe", {
        subscription: subscription.toJSON(),
      });
      await subscription.unsubscribe();
    }
  } catch (err) {
    console.warn("[push] Unsubscription failed:", err);
  }
}

export async function getPushPermissionState() {
  if (!("Notification" in window)) return "unsupported";
  return Notification.permission;
}
