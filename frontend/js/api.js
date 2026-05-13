const API_BASE = "/api/v1";
const TIMEOUT_MS = 10_000;
const MAX_RETRIES = 1;

let _token = localStorage.getItem("token");

export function getToken() {
  return _token;
}

export function setToken(token) {
  _token = token;
  if (token) {
    localStorage.setItem("token", token);
  } else {
    localStorage.removeItem("token");
  }
}

export function isLoggedIn() {
  return !!_token;
}

async function request(method, path, body = null, attempt = 0) {
  const headers = { "Content-Type": "application/json" };
  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const opts = { method, headers, signal: controller.signal };
  if (body) {
    opts.body = JSON.stringify(body);
  }

  try {
    const res = await fetch(`${API_BASE}${path}`, opts);

    if (res.status === 401) {
      setToken(null);
      window.dispatchEvent(new CustomEvent("auth:logout"));
      throw new Error("Unauthorized");
    }

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || res.statusText);
    }

    if (res.status === 204) return null;
    return res.json();
  } catch (err) {
    // Retry once on network errors (not HTTP errors)
    if (attempt < MAX_RETRIES && (err.name === "AbortError" || err.name === "TypeError")) {
      await new Promise((r) => setTimeout(r, 1000));
      return request(method, path, body, attempt + 1);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  del: (path) => request("DELETE", path),
};
