const API_BASE = "/api/v1";

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

export async function request(method, path, body = null) {
  const headers = { "Content-Type": "application/json" };
  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`;
  }

  const opts = { method, headers };
  if (body) {
    opts.body = JSON.stringify(body);
  }

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
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  del: (path) => request("DELETE", path),
};
