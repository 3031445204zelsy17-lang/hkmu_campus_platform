const API_BASE = "/api/v1";
const TIMEOUT_MS = 10_000;
const MAX_RETRIES = 1;

let _token = localStorage.getItem("token");
let _refreshToken = localStorage.getItem("refresh_token");

function _getCsrfCookie() {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function getToken() {
  return _token;
}

export function getRefreshToken() {
  return _refreshToken;
}

export function setToken(token) {
  _token = token;
  if (token) {
    localStorage.setItem("token", token);
  } else {
    localStorage.removeItem("token");
  }
}

export function setRefreshToken(token) {
  _refreshToken = token;
  if (token) {
    localStorage.setItem("refresh_token", token);
  } else {
    localStorage.removeItem("refresh_token");
  }
}

export function isLoggedIn() {
  return !!_token;
}

async function _tryRefresh() {
  if (!_refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: _refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    setToken(data.access_token);
    if (data.refresh_token) setRefreshToken(data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

async function request(method, path, body = null, attempt = 0) {
  const headers = { "Content-Type": "application/json" };
  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`;
  }
  // Attach CSRF token for mutating requests
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    const csrf = _getCsrfCookie();
    if (csrf) {
      headers["X-CSRF-Token"] = csrf;
    }
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
      // Try refresh token once
      if (attempt === 0 && _refreshToken) {
        const refreshed = await _tryRefresh();
        if (refreshed) {
          return request(method, path, body, attempt + 1);
        }
      }
      setToken(null);
      setRefreshToken(null);
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
