import { isLoggedIn } from "./api.js";
import { t } from "./utils/i18n.js";
import { showToast } from "./components/toast.js";

const routes = {};
const routeOptions = {};
let _currentPath = null;

export function register(path, handler, options = {}) {
  routes[path] = handler;
  routeOptions[path] = options;
}

export function navigate(path) {
  window.location.hash = path;
}

export function start() {
  window.addEventListener("hashchange", _resolve);
  _resolve();
}

export function forceResolve() {
  _currentPath = null;
  _resolve();
}

function _resolve() {
  const hash = window.location.hash || "#/";
  const path = hash.slice(1).split("?")[0];

  if (path === _currentPath) return;
  _currentPath = path;

  // exact match first
  if (routes[path]) {
    if (_guard(path)) {
      routes[path]();
    }
    return;
  }

  // pattern match: /posts/123 → /posts/:id
  for (const pattern of Object.keys(routes)) {
    const param = _match(pattern, path);
    if (param !== null) {
      if (_guard(pattern)) {
        routes[pattern](param);
      }
      return;
    }
  }

  // 404 fallback
  const app = document.getElementById("app-content");
  app.innerHTML = `
    <div class="flex flex-col items-center justify-center py-24 text-center">
      <h1 class="text-6xl font-bold text-gray-300 mb-4">404</h1>
      <p class="text-gray-500 mb-6">${t("error.page_not_found")}</p>
      <a href="#/" class="text-blue-500 hover:underline">${t("error.back_home")}</a>
    </div>
  `;
}

function _guard(pattern) {
  const opts = routeOptions[pattern];
  if (opts?.auth && !isLoggedIn()) {
    showToast(t("auth.login_required"), "warning");
    _currentPath = null;
    navigate("/");
    return false;
  }
  return true;
}

function _match(pattern, path) {
  const pParts = pattern.split("/");
  const pathParts = path.split("/");
  if (pParts.length !== pathParts.length) return null;

  let param = null;
  for (let i = 0; i < pParts.length; i++) {
    if (pParts[i].startsWith(":")) {
      param = pathParts[i];
    } else if (pParts[i] !== pathParts[i]) {
      return null;
    }
  }
  return param;
}
